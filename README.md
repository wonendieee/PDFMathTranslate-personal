# doc-translator

一个基于 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 与 [PDFMathTranslate-next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) 的个人 fork 版文档翻译工具，在原有 **PDF** 翻译能力基础上扩展了 **Word (`.docx`)** 与 **Excel (`.xlsx`)** 的"忠实回写式"翻译。

> 本仓库是个人使用的 fork，不接受外部贡献、不发布 PyPI；如需通用版本请移步上游项目。

---

## 特性

- **PDF**：完全保留上游能力——公式、图表、目录、注释、双语对照等，由 BabelDOC 处理。
- **Word (`.docx`)**：保留段落格式（粗体 / 斜体 / 字号 / 表格结构），自动跳过 OMML 数学公式，对段落 dominant run 回写译文。
- **Excel (`.xlsx`)**：逐单元格翻译，保留公式 (`=A1+B1` 不会被翻）、合并单元格范围、日期类型、数字格式。
- **统一命令行入口**：自动按扩展名识别格式，无需指定子命令。
- **默认免费后端**：不填任何 API key 即可使用 SiliconFlow Free 代理 (`api1.pdf2zh-next.com` / `api2.pdf2zh-next.com`)，由上游项目维护。
- **Gradio WebUI**：文件上传支持 PDF / DOCX / XLSX 混选。

---

## 架构概览

```
translator/
├── format/
│   ├── base.py          # FormatHandler 抽象基类 + DocumentFormat 枚举
│   ├── pdf.py           # PDFFormatHandler -> pdf_backend
│   ├── word.py          # WordFormatHandler -> word_pipeline
│   └── excel.py         # XlsxFormatHandler
├── pdf_backend/         # babeldoc 子进程封装
├── office/              # Office 通用工具：should_translate / batch_translator
├── format/word_pipeline/ # Word 专属：collector / writer
├── engines/             # 翻译引擎实现（SiliconFlow / OpenAI / DeepL / ...）
├── high_level.py        # do_translate_async_stream：按格式分发到 handler
├── main.py              # CLI
└── gui.py               # Gradio WebUI
```

核心思路：`high_level.do_translate_async_stream()` 根据文件扩展名选择对应的 `FormatHandler`，统一产出 babeldoc 风格的事件流 (`progress_start` / `progress_update` / `finish`)。每个 handler 内部独立实现各自的收集—翻译—回写流程，互不干扰。

---

## 安装

推荐使用 [uv](https://github.com/astral-sh/uv)：

```bash
git clone https://github.com/wonendieee/PDFMathTranslate-personal.git
cd PDFMathTranslate-personal
uv sync
```

或使用 conda + pip：

```bash
conda create -n doc-translator python=3.12 -y
conda activate doc-translator
pip install -e .
```

---

## 使用

### 命令行

```bash
# PDF（自动识别）
doc-translator input.pdf --output ./out

# Word
doc-translator input.docx --output ./out

# Excel
doc-translator input.xlsx --output ./out
```

入口别名 `translator` / `pdf2zh` / `pdf2zh_next` 同样可用。

### 启动 WebUI

```bash
doc-translator --gui
```

### 指定翻译引擎

默认是 SiliconFlow Free（无需 API key）。切换示例：

```bash
doc-translator input.pdf --openai --openai-api-key sk-xxx --openai-model gpt-4o-mini
```

完整可用引擎参数见 `doc-translator --help`。

---

## 开发

```bash
uv sync --group dev
uv run pytest -q          # 全量单测
uv run ruff check .       # 代码风格
```

测试覆盖：`tests/format/`、`tests/office/`、`tests/config/`。Office 端到端测试使用 `MockTranslator`，不会发出真实 API 请求。

---

## 已知限制

- `.doc` / `.xls`（旧二进制格式）**不支持**，需先在 Office / WPS 中另存为新格式。
- Word 翻译以段落级为单位，若一个段落内部跨了多个不同字体 / 颜色的 run，所有格式会统一到 dominant run；这是精度与忠实度的权衡。
- Excel 公式、图表标题内部的引用不翻译。
- 由于默认调用上游公共免费代理，高频使用时请尊重上游的 QPS 限制，或切换到自有 API key。

---

## 致谢

本项目完全站在以下工作的肩上：

- [BabelDOC](https://github.com/funstory-ai/BabelDOC) — PDF 版面分析与布局保持
- [PDFMathTranslate-next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) — 本 fork 的原项目
- [python-docx](https://github.com/python-openxml/python-docx) / [openpyxl](https://openpyxl.readthedocs.io/) — Office 文件读写

License: AGPL-3.0（继承自上游）。
