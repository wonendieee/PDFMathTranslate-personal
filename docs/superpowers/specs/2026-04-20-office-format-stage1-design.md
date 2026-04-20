# Office 格式翻译支持（阶段 1）设计规范

**Status:** Draft
**Date:** 2026-04-20
**Scope:** 阶段 1 —— Word/Excel 正文与表格单元格纯文本翻译，保真回填
**Stage Target:** 首个可用版本（MVP），后续阶段（页眉/公式/SmartArt/OCR）各自单独写 spec

---

## 1. 背景与目标

### 1.1 背景

当前项目 `PDFMathTranslate-personal`（包名 `pdf2zh_next`）仅支持 PDF 翻译，核心依赖 `babeldoc` 的 PDF 管线。早期已在 `pdf2zh_next/format/` 下搭出"多格式抽象层"雏形（`DocumentFormat` 枚举、`FormatHandler` 抽象类、`word.py` 初始实现），但采用"统一转 PDF 再翻译"的思路，存在以下根本问题：

1. Word 通过 pypandoc → xelatex → PDF 强依赖 TeX Live 工具链，且输出只能是 PDF，**无法保留 docx 的可编辑性/样式**
2. Excel 未开工；`DocumentFormat` 无 XLSX/XLS
3. `FormatHandler.convert_to_pdf()` 接口设计错误：所有格式都被强制转 PDF，违背"保真回填"需求
4. 缺乏"翻译结果回填到原格式"或"任意目标格式输出"的能力

### 1.2 目标

阶段 1 交付**可用的 Word/Excel 翻译能力**：输入 `.docx` 输出 `.docx`、输入 `.xlsx` 输出 `.xlsx`，保留原排版/样式/公式/图片，仅替换文本内容。

**非目标**（后续阶段处理）：
- 页眉页脚、脚注、文本框、批注的翻译
- Word 数学公式（OMML）与 LaTeX 翻译
- SmartArt、嵌入对象、图片 OCR
- PDF ↔ DOCX ↔ XLSX 之间的任意互转
- `.doc`（旧版二进制格式）的完整支持 —— 仅保留检测识别，翻译走"告知用户先另存为 .docx"

---

## 2. 架构

### 2.1 核心原则

1. **PDF 管线零改动**：现有 `babeldoc` 子进程翻译逻辑、进度事件、IPC、缓存机制完全保留
2. **多管线并行**：每种格式由独立的 `FormatHandler` 负责，通过事件流统一对上层暴露
3. **翻译引擎复用**：Word/Excel 管线直接调用 `engines.get_translator(settings)`（原 `translator/` 子包），不重复实现
4. **不过早抽象**：`office/` 只服务于 Office 格式（docx/xlsx），PDF 不共用，避免 YAGNI

### 2.2 包名与目录调整（一次性改名）

顶层包 `pdf2zh_next/` 重命名为 `translator/`，其中：
- `pdf2zh_next/translator/` 子包（翻译引擎）→ `translator/engines/`（避免"顶层包名 = 子包名"的 import 歧义）
- `pdf2zh_next/high_level.py` 里 babeldoc 相关代码下沉到 `translator/pdf_backend/`
- 其余通用模块（`format/`、`config/`、`gui.py`、`main.py`）保留在顶层

**改名清单**：
- `pyproject.toml` 的 `[project].name`、`[project.scripts]`、`[tool.hatch.build.targets.wheel].packages`
- 所有 `from pdf2zh_next.xxx import ...`（批量 IDE 重构）
- `Dockerfile`、`tests/`、`script/setup.bat`、CI 配置里的路径引用
- **PyPI 上 `translator` 名称被占用**——仅限本地使用；将来发布需改 `pyproject.toml` 的 `name`（包名可保留）

### 2.3 目录结构

```
translator/                          # ← 原 pdf2zh_next/，顶层重命名
├── format/                          # 格式抽象层
│   ├── __init__.py                  🔧 注册 XLSX; detect_document_format 扩展
│   ├── base.py                      🔧 接口改正: translate() 替代 convert_to_pdf
│   ├── pdf.py                       🔧 PDFFormatHandler.translate() 委托 pdf_backend
│   ├── word.py                      🔧 重写: python-docx 管线
│   └── excel.py                     ✅ 新增: XlsxFormatHandler (openpyxl)
├── engines/                         🔧 ← 原 translator/ 子包改名
│   └── (内容不变, 仅路径重命名)
├── office/                          ✅ 新增: Office 管线共享小工具
│   ├── __init__.py
│   ├── batch_translator.py          ✅ 薄封装: 批量翻译 + 去重 + 并发 + QPS
│   └── text_utils.py                ✅ should_translate() 过滤规则
├── pdf_backend/                     ✅ 新增: babeldoc 集成下沉
│   ├── __init__.py
│   ├── subprocess_runner.py         🔧 原 _translate_wrapper / _translate_in_subprocess
│   └── babeldoc_config.py           🔧 原 create_babeldoc_config
├── config/                          🔧 加 XLSX/XLS 到 DocumentFormat
├── gui.py                           🔧 import 路径批量更新
├── main.py                          🔧 import 路径 + 扩展名 .xlsx/.xls
└── high_level.py                    🔧 只保留"调度/聚合"逻辑
```

### 2.4 FormatHandler 新接口

```python
# translator/format/base.py

class FormatHandler(ABC):
    @abstractmethod
    def get_format(self) -> DocumentFormat: ...

    @abstractmethod
    def detect_format(self, file_path: Path) -> bool: ...

    @abstractmethod
    def validate_file(self, file_path: Path) -> bool: ...

    @abstractmethod
    def translate(
        self,
        input_file: Path,
        settings: SettingsModel,
    ) -> AsyncGenerator[dict, None]:
        """产出和 babeldoc 一致的事件流:
        - {"type": "progress", "overall_progress": float, "stage": str}
        - {"type": "finish", "translate_result": TranslateResult}
        - {"type": "error", "error": str, "error_type": str, "details": str}
        """
```

**移除**的旧接口：`convert_to_pdf`、`get_babeldoc_processor`、`cleanup`（临时文件由各 handler 内部自理）。

### 2.5 事件流契约

所有 `translate()` 产出的事件必须兼容现有 GUI/CLI 事件消费代码（`high_level.do_translate_file_async` 的 progress_handler）：

| 阶段 | `overall_progress` | `stage` |
|---|---|---|
| 打开读取 | 0.05 | `"reading"` |
| 收集文本 | 0.10 | `"collecting"` |
| 翻译中 | 0.10 → 0.85 线性 | `"translating"` |
| 回填/保存 | 0.95 | `"writing"` |
| 完成 | — | 发 `{"type": "finish", "translate_result": {...}}` |

`TranslateResult` 字段（与 babeldoc 对齐）：`original_path`、`translated_path`、`total_seconds`。阶段 1 不产出 `dual_path`（双语对照）。

---

## 3. Word 管线（阶段 1）

### 3.1 收集范围

- ✅ 正文段落 `doc.paragraphs` 的每一个 `Paragraph`（作为**一个翻译单元**）
- ✅ 表格单元格 `doc.tables[*].rows[*].cells[*].paragraphs` 的每一个段落
- ❌ 跳过：页眉 / 页脚 / 脚注 / 文本框 / 批注 / OMML 公式节点 / 图片

### 3.2 段落级 vs Run 级翻译

**选型：段落级翻译 + dominant-run 回填**

- 把段落所有 run 的 `.text` 按顺序拼接成一句，作为翻译单元
- 译文写到**文本最长的 run**（称 dominant run），其他 run 的 `.text` 清空
- **保留所有 run 对象**，从而保留段落级样式：字体、字号、对齐、颜色、段前后距

**显式 trade-off**（阶段 1 接受）：
- 段落内部混排样式（如 `"这是 **粗体** 字"`）→ 译文统一采用 dominant run 的样式，混排样式丢失
- 理由：run 常切在词内部（"develop" + "ment"），run 级翻译会灾难性影响质量
- 阶段 2 可引入"占位符替换法"恢复混排：翻译前将 run 边界替换成占位符 `<R1>…</R1>`，翻译时要求模型保留占位符，回填时按占位符切分

### 3.3 公式保护（防御性处理）

阶段 1 **不翻译**数学公式，但必须保证公式**不被破坏**：

- 用 `lxml` 检测段落内的 `<w:oMath>` / `<m:oMath>` 节点
- 若一个段落**完全是公式**（无普通文本）→ 整段跳过，不进入翻译队列
- 若段落为"公式 + 文本"混排 → 阶段 1 策略：**整段跳过**（不冒险），文档化为已知限制；阶段 2 处理占位符替换

### 3.4 文本过滤 `should_translate()`

下列文本**不进入翻译队列**：
- 空字符串、纯空白（`text.strip() == ""`）
- 纯数字（`text.strip().replace(",", "").replace(".", "").isdigit()`）
- 纯符号 / 标点（`not any(ch.isalnum() for ch in text)`）
- 单字符（`len(text.strip()) == 1`）

### 3.5 输出

- 输出文件名：`{input_stem}.zh.docx`
- 输出目录：`settings.translation.output`（不存在则创建）
- 保存前不修改任何非文本属性（图片、SmartArt、嵌入对象原样保留，由 python-docx 自动处理）

### 3.6 `.doc` 处理

阶段 1 **不支持** `.doc`（旧二进制格式）翻译。`DocxFormatHandler.validate_file()` 对 `.doc` 返回 `False` 并给出清晰错误：

> ".doc format is not supported. Please open in Word and save as .docx."

---

## 4. Excel 管线（阶段 1）

### 4.1 收集范围

- 遍历 `wb.worksheets` 每个 `Worksheet`
- 遍历 `ws.iter_rows()` 每个 `Cell`
- **只翻译**：`cell.data_type == "s"`（字符串类型）且 `not str(cell.value).startswith("=")`
- **跳过**：公式单元格、数字、日期、布尔、空单元格、`should_translate=False` 的内容

### 4.2 样式与结构保持

openpyxl 修改 `cell.value` **不会**动：
- 字体 / 颜色 / 填充 / 边框
- 列宽 / 行高
- 合并单元格范围（openpyxl 已正确处理：合并范围的值只在左上角 cell，覆盖即可）
- 图表（不在本次处理范围）
- 公式引用关系

### 4.3 不在阶段 1 处理

- 图表标题 / 数据系列名称
- 绘图对象内文本（TextBox、SmartArt）
- 工作表名（sheet name）

### 4.4 输出

- 输出文件名：`{input_stem}.zh.xlsx`
- 输出目录：`settings.translation.output`

---

## 5. 共享组件

### 5.1 `office/batch_translator.py`

```python
class OfficeBatchTranslator:
    """批量翻译薄封装: 去重 + 并发 + QPS 限流 + 进度回调

    设计要点:
    - 不做缓存 (缓存在 engines 层 translator 对象内部)
    - 去重: 相同文本只翻译一次, 按索引还原
    - 并发: asyncio.Semaphore(qps) 限流 + asyncio.gather
    - 失败: 默认 fail-fast, 首个异常抛出即终止
    """

    def __init__(
        self,
        translator,           # engines.get_translator() 返回的对象
        qps: int,
        max_workers: int,
    ): ...

    async def translate_batch(
        self,
        texts: list[str],
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        """按 texts 的顺序返回译文列表"""
```

### 5.2 `office/text_utils.py`

```python
def should_translate(text: str) -> bool:
    """判定文本是否需要翻译"""

def split_preserving_whitespace(text: str) -> tuple[str, str, str]:
    """拆分首尾空白, 返回 (leading_ws, core, trailing_ws)
    避免翻译时丢失原有的缩进/换行"""
```

### 5.3 运行模型差异（vs PDF）

Word/Excel 管线**在主进程同步运行**（不子进程化）。理由：
- 不依赖 babeldoc 及其重型依赖，资源开销小
- 主进程运行便于调试
- 翻译器的 async 调用已经有并发，无需再叠加进程级并行

---

## 6. 配置与 CLI

### 6.1 `DocumentFormat` 扩展

```python
class DocumentFormat(enum.Enum):
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"          # 仅识别, 阶段 1 translate 报错
    XLSX = "xlsx"        # 新增
    XLS = "xls"          # 仅识别, 阶段 1 translate 报错
    AUTO = "auto"
```

### 6.2 CLI

- `main.py::find_all_files_in_directory` 扩展名列表增加 `.xlsx`、`.xls`
- `--input-format` 参数可接受 `pdf | docx | xlsx | auto`（CLI 层由 `BasicSettings.input_format` 自动驱动；默认 `auto`）
- `pyproject.toml` 的 `[project.scripts]` 入口点从 `pdf2zh / pdf2zh2 / pdf2zh_next` 调整为新名（建议保留 `pdf2zh` 别名以便过渡）：
  - `translator = "translator.main:cli"`
  - `pdf2zh = "translator.main:cli"`（向后兼容别名，保留）
- 用户常用调用形式：
  - `translator input.docx`（auto 检测）
  - `translator --input-format docx input.docx`（显式指定）

### 6.3 GUI

`gui.py` 文件选择器接受的扩展名同步扩展；GUI 配置 YAML (`gui_translation.yaml`) 的相关下拉选项新增 DOCX/XLSX（具体 YAML key 在实现阶段定位）。

---

## 7. 依赖变更

### 7.1 新增

- `python-docx` （最新稳定版，pyproject 不指定严格版本，取安装时 `pip`/`uv` 解析的最新）
- `openpyxl` （同上）
- `lxml` （python-docx 已隐式依赖；Excel 管线显式使用，`pyproject.toml` 显式列出）

### 7.2 移除

- `pypandoc` （若当前 `pyproject.toml` 有）—— 旧 Word 管线依赖，新管线不用

### 7.3 版本不写死

遵循 `writing-plans` 规则：`pyproject.toml` 中不硬编码新依赖版本，由 `uv add python-docx openpyxl lxml` 生成最新版本约束。

---

## 8. 错误处理

| 错误场景 | 处理 |
|---|---|
| 文件打开失败（损坏 / 权限） | `raise ValueError(msg) from e` → 上层转 `{"type": "error"}` |
| `.doc` / `.xls` 尝试翻译 | `raise ValueError("Please save as .docx/.xlsx first")` |
| 翻译单条失败 | fail-fast：首个异常终止整个文件翻译，抛 `TranslationError` 子类 |
| 保存失败（磁盘满 / 权限） | `raise ValueError(msg) from e` |
| 输出目录不存在 | 自动创建（`parent.mkdir(parents=True, exist_ok=True)`） |

未来扩展：`settings.translation.continue_on_error` 开关允许单条失败不终止整体（阶段 1 不做）。

---

## 9. 测试策略

### 9.1 测试目录

`tests/office/` 新增：
- `test_word.py` — Word handler 单测与集成测试
- `test_excel.py` — Excel handler 单测与集成测试
- `test_text_utils.py` — `should_translate` 规则
- `test_batch_translator.py` — 去重 / 并发 / 进度回调
- `fixtures/` — 测试用 .docx 和 .xlsx（脚本生成或手工准备）

### 9.2 Fixture 规划

**Word**：
1. `plain.docx` — 纯正文 3 段
2. `with_table.docx` — 正文 + 3×3 表格
3. `with_formula.docx` — 正文 + OMML 公式段
4. `mixed_runs.docx` — 段内混排样式（加粗/颜色）

**Excel**：
1. `single_sheet.xlsx` — 单 sheet，10 行字符串
2. `multi_sheet.xlsx` — 3 个 sheet，每 sheet 5 行
3. `with_formulas.xlsx` — 混合字符串和公式单元格
4. `with_merged.xlsx` — 带合并单元格和日期/数字列

### 9.3 Mock 翻译器

```python
class MockTranslator:
    """返回 '[zh]' + text, 同步接口, 不产生 LLM 调用"""
    def translate(self, text: str) -> str:
        return f"[zh]{text}"
```

### 9.4 集成测试核心断言

- 翻译后文件能被 python-docx/openpyxl **正常打开**（无 schema 错误）
- 翻译单元数量正确（translator mock 被调用 N 次，N = 收集到的文本数）
- 非翻译内容**字节级保留**（合并区域、公式、图片、日期、数字）
- 事件流包含 `reading → collecting → translating → writing → finish`

### 9.5 e2e 边界

**不做**：涉及真实 LLM 调用的 e2e 测试（慢、花钱、不稳定）。真实 LLM 验证由开发者手工在本地跑样例文件。

### 9.6 PDF 回归

所有现有 PDF 测试（`tests/test_*.py`）必须全部通过，且 CLI 的 PDF 翻译端到端行为不变。

---

## 10. 验收标准

1. **Word**：`translator input.docx` 产出 `input.zh.docx`，Word 打开：
   - ✅ 正文段落 / 表格单元格译文替换
   - ✅ 段落级样式保留（字体、对齐、颜色、段前后距）
   - ✅ OMML 公式、图片、页眉页脚、批注**原样保留**
   - ⚠️ 段落内部 run 混排样式允许丢失（已文档化）
2. **Excel**：`translator input.xlsx` 产出 `input.zh.xlsx`：
   - ✅ 所有 sheet 字符串译文替换
   - ✅ 公式 / 日期 / 数字 / 布尔 / 合并单元格 / 列宽行高**全保留**
3. 事件流与 PDF 一致，GUI 进度条显示正常
4. **PDF 翻译零回归**
5. 新增代码单测覆盖率 ≥ 80%
6. 包名改名后 `uv run translator <file>` CLI 正常工作

---

## 11. 阶段 1 不做（已知限制）

明确文档化，避免后续被当 bug 提：

- 段落内部混排样式（run 级 bold/italic/color）丢失
- 页眉、页脚、脚注、批注、文本框不翻译
- 数学公式（OMML/LaTeX）不翻译，但保留不破坏
- SmartArt / 嵌入对象 / 图片 OCR 不处理
- Excel 图表标题 / 数据系列名 / sheet 名不翻译
- `.doc` / `.xls` 旧格式不支持翻译（要求用户另存为新格式）
- 双语对照输出（dual）不支持

这些均留给阶段 2 及以后。

---

## 12. 开放决策（实现阶段再定）

- **输出文件命名后缀**：`.zh.docx` vs `.translated.docx` vs `.{lang_out}.docx`——建议按 `lang_out` 动态决定（例如 `settings.translation.lang_out = "zh"` → `.zh.docx`），但阶段 1 实现时先硬编码 `.zh.docx`，统一后在阶段 2 改
- **dominant run 选取规则**：取 `len(text)` 最大者。若多个 run 长度相同，取第一个
- **`OfficeBatchTranslator` 的 `max_workers`**：复用 `settings.translation.pool_max_workers`
