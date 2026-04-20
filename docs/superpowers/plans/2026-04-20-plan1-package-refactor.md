# Plan 1 — 包名重构与 FormatHandler 接口改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把顶层包 `pdf2zh_next/` 重命名为 `translator/`，将 babeldoc 集成代码从 `high_level.py` 下沉到新建的 `translator/pdf_backend/` 子包，改正 `FormatHandler` 接口（移除错误的 `convert_to_pdf`，改为统一的 `translate()` 事件流），并为后续 Office 管线铺好位。

**Architecture:** 保持 PDF 翻译行为零变化，纯架构重构。顶层包通用化；PDF 特有代码集中在 `pdf_backend/` 子包；`FormatHandler` 统一对外暴露 `translate(input, settings) -> AsyncGenerator[dict]` 事件流。

**Tech Stack:** Python 3.10–3.13、hatchling 构建、uv 包管理、pytest、python-docx / openpyxl / lxml（新依赖，本 Plan 只加入，实际使用在 Plan 2）。

**Commit 策略：** 用户要求"等整体改动基本完成再统一提交"——所有 Task 的最后一步改为 **Checkpoint（运行测试验证，不 commit）**。Plan 1 + Plan 2 全部完成后再一次性 commit。

---

## Task 顺序依赖

```
Task 1 (deps) → Task 2 (顶层 rename) → Task 3 (子包 rename) → Task 4 (pdf_backend 下沉)
                                                              ↓
Task 5 (FormatHandler 接口) → Task 6 (PDF handler) → Task 7 (Word 占位)
                                                              ↓
                                          Task 8 (DocumentFormat 扩展) → Task 9 (调度层) → Task 10 (回归)
```

每个 Task 独立可验证，下游依赖上游必须先通过 Checkpoint。

---

## Task 1: 更新 pyproject.toml 依赖

**Files:**
- Modify: `pyproject.toml:18-51` (主依赖列表)
- Modify: `pyproject.toml:69-81` (word 可选依赖组)

**- [ ] Step 1.1: 加入主依赖 python-docx / openpyxl / lxml**

在 `pyproject.toml` 的 `[project].dependencies` 列表（行 18-51）**末尾**加三行：

```toml
    "python-docx",
    "openpyxl",
    "lxml",
```

**- [ ] Step 1.2: 移除 pypandoc**

删除 `pyproject.toml` 中以下两处的 `pypandoc>=1.14`：
- `[dependency-groups].word`（行 69-72）整组删除（里面只有 word 组且已重复）
- `[project.optional-dependencies].word`（行 77-81）整组删除

改后 `pyproject.toml` 将没有 `word` 可选组，因为新依赖已下沉到主依赖。

**- [ ] Step 1.3: 同步依赖并验证**

Run: `uv sync`

Expected: 成功拉取 python-docx、openpyxl、lxml；无报错。

**- [ ] Step 1.4: Checkpoint — 运行现有 PDF 测试**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过（此时包名还是 `pdf2zh_next`，测试集里的 import 仍有效）。

---

## Task 2: 顶层包 `pdf2zh_next` → `translator`

**Files:**
- Rename: `pdf2zh_next/` → `translator/`
- Modify: 所有 `.py` 文件中的 `pdf2zh_next` 字符串（约 22 个文件，100+ 处）
- Modify: `pyproject.toml`（`name`、`[project.scripts]`、`bumpver`、`per-file-ignores`）
- Modify: `tests/config/test_main.py`、`tests/config/test_model.py`、`test/test_cache.py`
- Modify: `.github/workflows/python-test.yml`、`.github/workflows/fork-build.yml`

**- [ ] Step 2.1: 关掉可能持有文件句柄的进程**

Run (PowerShell): 确保无 IDE 的 Python 进程、babeldoc 子进程等仍在运行；否则 `git mv` 会失败。

**- [ ] Step 2.2: 目录重命名**

Run: `git mv pdf2zh_next translator`

Expected: 目录改名完成；`git status` 显示大量 `renamed: pdf2zh_next/... → translator/...`。

**- [ ] Step 2.3: 批量替换所有 .py 文件中的 import 字符串**

在项目根目录创建临时脚本 `scripts/rename_imports.py`（**任务结束时删除**）：

```python
"""一次性脚本: 把 pdf2zh_next 替换为 translator."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
TARGETS = [
    *ROOT.rglob("*.py"),
    *ROOT.rglob("*.yml"),
    *ROOT.rglob("*.yaml"),
    *ROOT.rglob("*.toml"),
]
PATTERN = re.compile(r"\bpdf2zh_next\b")

def should_process(p: Path) -> bool:
    parts = p.parts
    return not any(x in parts for x in (".venv", "__pycache__", ".git", ".doctemp", "dist", "build"))

count = 0
for f in TARGETS:
    if not should_process(f):
        continue
    try:
        text = f.read_text(encoding="utf-8")
    except Exception:
        continue
    new_text, n = PATTERN.subn("translator", text)
    if n > 0:
        f.write_text(new_text, encoding="utf-8")
        print(f"[{n:3d}] {f.relative_to(ROOT)}")
        count += n
print(f"Total replacements: {count}")
```

Run: `uv run python scripts/rename_imports.py`

Expected: 打印出被修改的文件列表和替换计数；无异常。重点文件应包含：
- `translator/__init__.py`
- `translator/main.py`
- `translator/high_level.py`
- `translator/config/model.py`
- `translator/format/__init__.py` 等
- `tests/config/test_main.py`、`tests/config/test_model.py`
- `test/test_cache.py`

**- [ ] Step 2.4: 修改 pyproject.toml**

用 StrReplace 分别做以下四处修改：

a) `[project].name`：
```toml
name = "pdf2zh-next"
```
改为：
```toml
name = "translator"
# NOTE: "translator" 在 PyPI 上已被占用, 仅限本地安装。发 PyPI 时改回或加后缀（例如 translator-next）。
```

b) `[project.scripts]`：
```toml
[project.scripts]
pdf2zh = "pdf2zh_next.main:cli"
pdf2zh2 = "pdf2zh_next.main:cli"
pdf2zh_next = "pdf2zh_next.main:cli"
```
改为：
```toml
[project.scripts]
translator = "translator.main:cli"
pdf2zh = "translator.main:cli"
pdf2zh2 = "translator.main:cli"
pdf2zh_next = "translator.main:cli"
```
（保留 `pdf2zh` 等别名不改，让 Dockerfile 里 `CMD ["pdf2zh", "--gui"]` 及用户已有脚本继续工作。）

c) `[bumpver.file_patterns]`：三处 `"pdf2zh_next/..."` 改成 `"translator/..."`。

d) `[tool.ruff.lint.per-file-ignores]`：`"pdf2zh_next/gui.py"` 改成 `"translator/gui.py"`。

e) `[tool.ruff].src`：`src = ["babeldoc"]` 保持不变（babeldoc 是外部依赖）。

**- [ ] Step 2.5: 删除临时脚本**

Run: `Remove-Item scripts/rename_imports.py`（PowerShell）

**- [ ] Step 2.6: 重新安装包（entry point 生效）**

Run: `uv sync`

Expected: 成功；`uv pip list` 显示 `translator` 已注册。

**- [ ] Step 2.7: 手动验证一下核心 import 正常**

Run: `uv run python -c "from translator.config.model import SettingsModel; print(SettingsModel)"`

Expected: 输出类对象，无 ImportError。

**- [ ] Step 2.8: 验证 CLI 入口生效**

Run: `uv run translator --version`

Expected: 输出 `pdf2zh-next version: 2.8.2`（内部 `__version__` 沿用，后续任务修正字符串）。

**- [ ] Step 2.9: Checkpoint — PDF 回归**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。若失败，检查剩余未替换的 `pdf2zh_next` 字符串（`rg "pdf2zh_next" --type py`）。

---

## Task 3: 子包 `translator/translator` → `translator/engines`

**Files:**
- Rename: `translator/translator/` → `translator/engines/`
- Modify: 所有含 `translator.translator` 或 `from translator.translator` 的 `.py` 文件

**- [ ] Step 3.1: 目录重命名**

Run: `git mv translator/translator translator/engines`

**- [ ] Step 3.2: 批量替换 import 字符串**

创建临时脚本 `scripts/rename_engines.py`：

```python
"""一次性脚本: translator.translator -> translator.engines"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

def should_process(p: Path) -> bool:
    parts = p.parts
    return not any(x in parts for x in (".venv", "__pycache__", ".git", ".doctemp", "dist", "build"))

# 注意顺序: 先替换最长的 pattern, 避免 "translator.translator" 的第二个 translator 被先替换
REPLACEMENTS = [
    (re.compile(r"\btranslator\.translator\b"), "translator.engines"),
    (re.compile(r"^from translator\.translator "), "from translator.engines "),
]

count = 0
for f in ROOT.rglob("*.py"):
    if not should_process(f):
        continue
    try:
        text = f.read_text(encoding="utf-8")
    except Exception:
        continue
    original = text
    for pat, repl in REPLACEMENTS:
        text = pat.sub(repl, text)
    if text != original:
        f.write_text(text, encoding="utf-8")
        print(f"  {f.relative_to(ROOT)}")
        count += 1
print(f"Files modified: {count}")
```

Run: `uv run python scripts/rename_engines.py`

Expected: 受影响文件含 `translator/__init__.py`、`translator/config/*.py`、`translator/gui.py`、`translator/high_level.py` 等。

**- [ ] Step 3.3: 人工复查字符串形式的动态 import**

Run: `rg "translator\.translator" --type py`

Expected: **0 个匹配**。如有残留（可能是字符串里动态拼接的模块名），用 StrReplace 手工修改。

常见风险点：`translator/engines/translator_impl/*.py` 里可能有 `importlib.import_module("translator.translator.xxx")` 之类——需手动改为 `translator.engines.xxx`。

**- [ ] Step 3.4: 删除临时脚本**

Run: `Remove-Item scripts/rename_engines.py`

**- [ ] Step 3.5: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。

---

## Task 4: 创建 `translator/pdf_backend/` 并下沉 babeldoc 集成

**Files:**
- Create: `translator/pdf_backend/__init__.py`
- Create: `translator/pdf_backend/subprocess_runner.py`
- Create: `translator/pdf_backend/babeldoc_config.py`
- Modify: `translator/high_level.py`（移除搬走的内容，只保留调度层）
- Modify: `translator/__init__.py`（保留公共 API 的 re-export）

**- [ ] Step 4.1: 创建 pdf_backend 包目录**

Write `translator/pdf_backend/__init__.py`:

```python
"""PDF backend - babeldoc integration for PDF translation.

Not intended for Office (docx/xlsx) consumers.
"""

from translator.pdf_backend.babeldoc_config import create_babeldoc_config
from translator.pdf_backend.subprocess_runner import BabeldocError
from translator.pdf_backend.subprocess_runner import IPCError
from translator.pdf_backend.subprocess_runner import SubprocessCrashError
from translator.pdf_backend.subprocess_runner import SubprocessError
from translator.pdf_backend.subprocess_runner import TranslationError
from translator.pdf_backend.subprocess_runner import translate_in_subprocess

__all__ = [
    "TranslationError",
    "BabeldocError",
    "SubprocessError",
    "IPCError",
    "SubprocessCrashError",
    "create_babeldoc_config",
    "translate_in_subprocess",
]
```

**- [ ] Step 4.2: 迁移 subprocess_runner.py**

Write `translator/pdf_backend/subprocess_runner.py` with the following structure (copy verbatim from original `translator/high_level.py` 然后加上下面头部/调整导出名):

```python
"""Subprocess runner for babeldoc PDF translation.

Migrated from translator/high_level.py (原 _translate_wrapper, _translate_in_subprocess
and related error classes). Behavior is unchanged; only location and the public
function name are adjusted (_translate_in_subprocess → translate_in_subprocess).
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import multiprocessing
import multiprocessing.connection
import multiprocessing.queues
import queue
import threading
import traceback
from logging.handlers import QueueHandler
from pathlib import Path

from babeldoc.format.pdf.high_level import async_translate as babeldoc_translate
from rich.logging import RichHandler

from translator.config.model import SettingsModel
from translator.pdf_backend.babeldoc_config import create_babeldoc_config
from translator.utils import asynchronize

logger = logging.getLogger(__name__)


# --- Error classes (migrated from high_level.py:34-108) ---

class TranslationError(Exception):
    """Base class for all translation-related errors."""

    def __reduce__(self):
        return self.__class__, (str(self),)


class BabeldocError(TranslationError):
    """Error originating from the babeldoc library."""

    def __init__(self, message, original_error=None):
        super().__init__(message)
        self.original_error = original_error

    def __reduce__(self):
        return self.__class__, (str(self), self.original_error)

    def __str__(self):
        if self.original_error:
            return f"{super().__str__()} - Original error: {self.original_error}"
        return super().__str__()


class SubprocessError(TranslationError):
    """Error occurring in the translation subprocess outside of babeldoc."""

    def __init__(self, message, traceback_str=None):
        self.raw_message = message
        super().__init__(message)
        self.traceback_str = traceback_str

    def __reduce__(self):
        return (self.__class__, (self.raw_message, self.traceback_str))

    def __str__(self):
        if self.traceback_str:
            return f"{super().__str__()}\nTraceback: {self.traceback_str}"
        return super().__str__()


class IPCError(TranslationError):
    """Error in inter-process communication."""

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details

    def __reduce__(self):
        return self.__class__, (str(self), self.details)

    def __str__(self):
        if self.details:
            return f"{super().__str__()} - Details: {self.details}"
        return super().__str__()


class SubprocessCrashError(TranslationError):
    """Error occurring when the subprocess crashes unexpectedly."""

    def __init__(self, message, exit_code=None):
        super().__init__(message)
        self.exit_code = exit_code

    def __reduce__(self):
        return self.__class__, (str(self), self.exit_code)

    def __str__(self):
        if self.exit_code is not None:
            return f"{super().__str__()} (exit code: {self.exit_code})"
        return super().__str__()


# --- Subprocess worker (was _translate_wrapper, lines 114-313 of original) ---
# PASTE ORIGINAL _translate_wrapper BODY VERBATIM, RENAMED TO _translate_wrapper (still private)


def _translate_wrapper(
    settings: SettingsModel,
    file: Path,
    pipe_progress_send: multiprocessing.connection.Connection,
    pipe_cancel_message_recv: multiprocessing.connection.Connection,
    logger_queue: multiprocessing.Queue,
):
    # ---- BEGIN VERBATIM COPY from translator/high_level.py:114-313 ----
    # Copy the body as-is. No modifications. Do not change any logger.X call,
    # no reformatting, no rename. The error classes (BabeldocError etc.) are
    # resolved from the same module; behavior is identical.
    # ---- END VERBATIM COPY ----
    pass  # <-- replace this line with the copied body


# --- Async runner (was _translate_in_subprocess, lines 316-498 of original) ---


async def translate_in_subprocess(
    settings: SettingsModel,
    file: Path,
):
    # ---- BEGIN VERBATIM COPY from translator/high_level.py:316-498 ----
    # Copy the body as-is. ONLY change: function was named
    # "_translate_in_subprocess" there; it's "translate_in_subprocess" here
    # (public). No other edits.
    # ---- END VERBATIM COPY ----
    # NOTE: this function uses `yield`, do not replace with `pass`.
    if False:  # <-- delete this guard and paste the copied body below it
        yield
```

> **实施指示：**
> 1. 完整保留上面模板中的 import、error classes、函数签名
> 2. `_translate_wrapper` 函数体：从原 `translator/high_level.py` 行 114-313 **一字不改**复制到函数签名下，删除占位的 `pass`
> 3. `translate_in_subprocess` 函数体：从原 `translator/high_level.py` 行 316-498 **一字不改**复制，删除 `if False: yield` 占位；函数名从 `_translate_in_subprocess` 改为 `translate_in_subprocess`（去掉下划线），函数体里如果有自引用也一起改
> 4. 验证：`rg "_translate_in_subprocess" translator/pdf_backend/` 应该 **0 匹配**

**- [ ] Step 4.3: 迁移 babeldoc_config.py**

Write `translator/pdf_backend/babeldoc_config.py`:

```python
"""Build babeldoc TranslationConfig from pdf2zh-next SettingsModel.

Migrated from translator/high_level.py (原 _get_glossaries 和 create_babeldoc_config).
Behavior unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path

from babeldoc.format.pdf.translation_config import TranslationConfig as BabelDOCConfig
from babeldoc.format.pdf.translation_config import (
    WatermarkOutputMode as BabelDOCWatermarkMode,
)
from babeldoc.glossary import Glossary

from translator.config.model import SettingsModel
from translator.engines import get_term_translator
from translator.engines import get_translator

logger = logging.getLogger(__name__)


def _get_glossaries(settings: SettingsModel) -> list[Glossary] | None:
    # ---- VERBATIM COPY from translator/high_level.py:501-509 ----
    pass


def create_babeldoc_config(settings: SettingsModel, file: Path) -> BabelDOCConfig:
    # ---- VERBATIM COPY from translator/high_level.py:512-612 ----
    pass
```

> **实施指示：** 两个函数体**一字不改**从 `translator/high_level.py` 对应行复制；删除 `pass` 占位。由于这两个函数只在 babeldoc_config 语境下用到，不需要其他改动。

**- [ ] Step 4.4: 精简 translator/high_level.py**

修改 `translator/high_level.py`:

1. **删除** 行 1-108（import + 错误类）以及 行 114-498（`_translate_wrapper`、`_translate_in_subprocess`）以及 行 501-612（`_get_glossaries`、`create_babeldoc_config`）
2. **保留**：`do_translate_async_stream`、`do_translate_file_async`、`do_translate_file`
3. **新的顶部 import 区**：

```python
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from functools import partial
from pathlib import Path

from babeldoc.format.pdf.high_level import async_translate as babeldoc_translate
from babeldoc.format.pdf.translation_config import TranslationConfig as BabelDOCConfig
from babeldoc.main import create_progress_handler

from translator.config.model import SettingsModel
from translator.format import DocumentFormat
from translator.format import detect_document_format
from translator.format import get_format_handler
from translator.pdf_backend import BabeldocError
from translator.pdf_backend import IPCError
from translator.pdf_backend import SubprocessCrashError
from translator.pdf_backend import SubprocessError
from translator.pdf_backend import TranslationError
from translator.pdf_backend import create_babeldoc_config
from translator.pdf_backend import translate_in_subprocess

logger = logging.getLogger(__name__)
```

4. `do_translate_async_stream` 里原来 `partial(_translate_in_subprocess, settings, pdf_file)` 改成 `partial(translate_in_subprocess, settings, pdf_file)`

> 本任务只做"代码位置迁移 + import 重新连线"，**不改行为**。Task 9 才会改 `do_translate_async_stream` 的内部逻辑。

**- [ ] Step 4.5: 更新 translator/__init__.py 的 re-export**

修改 `translator/__init__.py`:

把这行：
```python
from translator.high_level import create_babeldoc_config
```

改成：
```python
from translator.pdf_backend import create_babeldoc_config
```

（`do_translate_async_stream`、`do_translate_file` 等行不变，因为它们仍在 `high_level.py`。）

**- [ ] Step 4.6: Checkpoint — 回归测试**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。如失败，最常见原因：
- 某个函数/类名少改或多改了：用 `rg "<symbol>" --type py` 检查
- import 循环：检查 pdf_backend 内部不能反向 import high_level

---

## Task 5: FormatHandler 基类接口改造

**Files:**
- Modify: `translator/format/base.py`（移除旧抽象方法，添加 `translate()`）
- Test: `tests/format/test_base.py`（新建，验证 ABC 强制）

**- [ ] Step 5.1: 写失败测试**

Create `tests/format/__init__.py`（空文件）。

Create `tests/format/test_base.py`:

```python
"""Tests for FormatHandler abstract base class."""
import pytest

from translator.format.base import DocumentFormat
from translator.format.base import FormatHandler


def test_format_handler_is_abstract():
    """FormatHandler cannot be instantiated directly."""
    with pytest.raises(TypeError):
        FormatHandler()


def test_format_handler_translate_is_async_generator_method():
    """Concrete subclass must implement translate() as async generator."""
    from pathlib import Path

    class DummyHandler(FormatHandler):
        def get_format(self): return DocumentFormat.PDF
        def detect_format(self, p): return True
        def validate_file(self, p): return True

        async def translate(self, input_file, settings):
            yield {"type": "finish", "translate_result": None}

    h = DummyHandler()
    gen = h.translate(Path("x"), None)
    # AsyncGenerator has __aiter__
    assert hasattr(gen, "__aiter__")


def test_old_convert_to_pdf_removed():
    """FormatHandler should no longer define convert_to_pdf."""
    assert not hasattr(FormatHandler, "convert_to_pdf")
    assert not hasattr(FormatHandler, "get_babeldoc_processor")
    assert not hasattr(FormatHandler, "cleanup")


def test_document_format_has_xlsx():
    """DocumentFormat enum must include XLSX and XLS (for Plan 2)."""
    # These will pass after Task 8, not Task 5. Keep as xfail here.
    pass
```

**- [ ] Step 5.2: 运行测试验证失败**

Run: `uv run pytest tests/format/test_base.py -v`

Expected: `test_old_convert_to_pdf_removed` **FAIL**（旧方法还在）；其他通过或错误（因为新接口还没加）。

**- [ ] Step 5.3: 改写 translator/format/base.py**

Overwrite `translator/format/base.py` 完整内容为：

```python
"""Base classes for document format handling."""

from __future__ import annotations

import enum
import logging
from abc import ABC
from abc import abstractmethod
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from translator.config.model import SettingsModel

logger = logging.getLogger(__name__)


class DocumentFormat(enum.Enum):
    """Supported document formats."""

    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    XLSX = "xlsx"
    XLS = "xls"
    AUTO = "auto"


class FormatHandler(ABC):
    """Abstract base class for document format handlers.

    A handler is responsible for:
      1. Detecting/validating whether a file belongs to its format.
      2. Running the full translation pipeline for a file of that format,
         emitting progress events compatible with the babeldoc event stream.

    Event stream contract (events emitted from translate()):
      - {"type": "progress", "overall_progress": float, "stage": str, ...}
      - {"type": "finish", "translate_result": object}
      - {"type": "error", "error": str, "error_type": str, "details": str}
    """

    @abstractmethod
    def get_format(self) -> DocumentFormat:
        """Return the document format this handler supports."""

    @abstractmethod
    def detect_format(self, file_path: Path) -> bool:
        """Return True if file_path looks like a document of this format."""

    @abstractmethod
    def validate_file(self, file_path: Path) -> bool:
        """Return True if file_path is a valid parseable document of this format."""

    @abstractmethod
    def translate(
        self,
        input_file: Path,
        settings: SettingsModel,
    ) -> AsyncGenerator[dict, None]:
        """Run translation pipeline; yields babeldoc-compatible events."""
```

**- [ ] Step 5.4: 运行测试**

Run: `uv run pytest tests/format/test_base.py -v`

Expected: 4 个测试全通过（test_document_format_has_xlsx 是 no-op 占位，返回 pass；其他真验证）。

**- [ ] Step 5.5: Checkpoint — 确认旧代码会报错**

Run: `uv run pytest tests/ -x -q`

Expected: **会有失败**（Task 6/7 还没更新 PDF/Word handler 以及 `high_level.py` 调度层对旧接口的引用）。这是预期的；下一个 Task 会修。
**失败即通过本 Checkpoint**（ImportError / AttributeError / ABC 实例化失败）。

---

## Task 6: PDFFormatHandler 改用 translate() 委托给 pdf_backend

**Files:**
- Modify: `translator/format/pdf.py`（重写，移除 `convert_to_pdf` 等）

**- [ ] Step 6.1: 改写 translator/format/pdf.py**

Overwrite `translator/format/pdf.py`:

```python
"""PDF format handler - thin wrapper delegating to translator.pdf_backend."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING

from translator.format.base import DocumentFormat
from translator.format.base import FormatHandler

if TYPE_CHECKING:
    from translator.config.model import SettingsModel

logger = logging.getLogger(__name__)


class PDFFormatHandler(FormatHandler):
    """PDF document format handler.

    Delegates actual translation to translator.pdf_backend (babeldoc subprocess).
    """

    def get_format(self) -> DocumentFormat:
        return DocumentFormat.PDF

    def detect_format(self, file_path: Path) -> bool:
        if not file_path.exists():
            return False
        if file_path.suffix.lower() == ".pdf":
            return True
        try:
            with file_path.open("rb") as f:
                return f.read(5).startswith(b"%PDF-")
        except Exception:
            return False

    def validate_file(self, file_path: Path) -> bool:
        if not file_path.exists() or not self.detect_format(file_path):
            return False
        try:
            if file_path.stat().st_size < 200:
                return True
        except OSError:
            return False
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            doc.close()
            return True
        except Exception as e:
            logger.debug(f"PDF validation failed for {file_path}: {e}")
            try:
                return file_path.stat().st_size < 500
            except OSError:
                return False

    async def translate(
        self,
        input_file: Path,
        settings: SettingsModel,
    ) -> AsyncGenerator[dict, None]:
        """Delegate to pdf_backend subprocess or in-process babeldoc."""
        from babeldoc.format.pdf.high_level import async_translate as babeldoc_translate

        from translator.pdf_backend import create_babeldoc_config
        from translator.pdf_backend import translate_in_subprocess

        if settings.basic.debug:
            cfg = create_babeldoc_config(settings, input_file)
            logger.debug("debug mode: babeldoc runs in main process")
            async for event in babeldoc_translate(translation_config=cfg):
                yield event
                if event["type"] == "finish":
                    break
        else:
            async for event in translate_in_subprocess(settings, input_file):
                yield event
                if event["type"] == "finish":
                    break
```

**- [ ] Step 6.2: Checkpoint — PDF handler 可构造、接口齐全**

Run:
```
uv run python -c "from translator.format.pdf import PDFFormatHandler; h = PDFFormatHandler(); print(h.get_format())"
```

Expected: `DocumentFormat.PDF`

**- [ ] Step 6.3: Checkpoint — 整体暂时仍有失败（word 还没改）**

Run: `uv run pytest tests/ -x -q`

Expected: format/test_base.py 全通过；旧 `translator/format/word.py` 可能因旧接口残留引发失败 —— Task 7 解决。

---

## Task 7: WordFormatHandler 占位实现

**Files:**
- Modify: `translator/format/word.py`（清空旧 pypandoc 实现，translate() 抛 NotImplementedError）

**- [ ] Step 7.1: 改写 translator/format/word.py**

Overwrite `translator/format/word.py`:

```python
"""Word document format handler (stub for Plan 1).

Real implementation lands in Plan 2. Plan 1 only needs:
  - Correct detect/validate (so auto-detect works and config validation passes).
  - translate() that raises NotImplementedError clearly (wired for Plan 2).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING

from translator.format.base import DocumentFormat
from translator.format.base import FormatHandler

if TYPE_CHECKING:
    from translator.config.model import SettingsModel

logger = logging.getLogger(__name__)


class WordFormatHandler(FormatHandler):
    """.docx handler.

    Plan 1: detect/validate only. Plan 2 implements translate().
    .doc (legacy binary) is not supported: validate_file() returns False.
    """

    def get_format(self) -> DocumentFormat:
        return DocumentFormat.DOCX

    def detect_format(self, file_path: Path) -> bool:
        if not file_path.exists():
            return False
        suffix = file_path.suffix.lower()
        if suffix == ".docx":
            return self._is_docx_file(file_path)
        return False

    def _is_docx_file(self, file_path: Path) -> bool:
        try:
            import zipfile
            with zipfile.ZipFile(file_path, "r") as zf:
                return any(n.startswith("word/") for n in zf.namelist())
        except Exception:
            return False

    def validate_file(self, file_path: Path) -> bool:
        if not file_path.exists() or not self.detect_format(file_path):
            return False
        try:
            import docx
            doc = docx.Document(file_path)
            _ = doc.paragraphs
            return True
        except Exception as e:
            logger.debug(f".docx validation failed for {file_path}: {e}")
            return False

    async def translate(
        self,
        input_file: Path,
        settings: SettingsModel,
    ) -> AsyncGenerator[dict, None]:
        raise NotImplementedError(
            "Word translation pipeline is implemented in Plan 2. "
            "If you reach this path, Plan 2 has not been delivered yet."
        )
        yield  # unreachable; for AsyncGenerator protocol
```

**- [ ] Step 7.2: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过（Task 5/6/7 已联动，format 模块自洽）。

---

## Task 8: DocumentFormat 扩展 + main.py 扩展名支持

**Files:**
- Create: `translator/format/excel.py`（占位）
- Modify: `translator/format/__init__.py`（detect 支持 .xlsx/.xls、注册 XlsxFormatHandler 占位）
- Modify: `translator/main.py`（find_all_files_in_directory 的扩展名列表）

**- [ ] Step 8.1: 创建 Excel 占位 handler**

Write `translator/format/excel.py`:

```python
"""Excel format handler (stub for Plan 1).

Real implementation lands in Plan 2.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING

from translator.format.base import DocumentFormat
from translator.format.base import FormatHandler

if TYPE_CHECKING:
    from translator.config.model import SettingsModel

logger = logging.getLogger(__name__)


class XlsxFormatHandler(FormatHandler):
    """.xlsx handler stub for Plan 1. .xls (legacy) is NOT supported."""

    def get_format(self) -> DocumentFormat:
        return DocumentFormat.XLSX

    def detect_format(self, file_path: Path) -> bool:
        if not file_path.exists():
            return False
        if file_path.suffix.lower() != ".xlsx":
            return False
        try:
            import zipfile
            with zipfile.ZipFile(file_path, "r") as zf:
                return any(n.startswith("xl/") for n in zf.namelist())
        except Exception:
            return False

    def validate_file(self, file_path: Path) -> bool:
        if not file_path.exists() or not self.detect_format(file_path):
            return False
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True)
            _ = wb.sheetnames
            wb.close()
            return True
        except Exception as e:
            logger.debug(f".xlsx validation failed for {file_path}: {e}")
            return False

    async def translate(
        self,
        input_file: Path,
        settings: SettingsModel,
    ) -> AsyncGenerator[dict, None]:
        raise NotImplementedError(
            "Excel translation pipeline is implemented in Plan 2."
        )
        yield
```

**- [ ] Step 8.2: 更新 translator/format/__init__.py**

修改 `translator/format/__init__.py`:

a) `detect_document_format` 函数里，加扩展名分支。找到现有的：
```python
    elif suffix == ".doc":
        return DocumentFormat.DOC
```
**后面**插入：
```python
    elif suffix == ".xlsx":
        return DocumentFormat.XLSX
    elif suffix == ".xls":
        return DocumentFormat.XLS
```

b) `_register_available_handlers` 函数里，在现有 word handler 注册 **之后** 追加：
```python
    try:
        from translator.format.excel import XlsxFormatHandler
        register_format_handler(DocumentFormat.XLSX, XlsxFormatHandler)
    except ImportError as e:
        logger.debug(f"Excel format handler not available: {e}")
```

**- [ ] Step 8.3: 更新 translator/main.py**

修改 `translator/main.py` 的 `find_all_files_in_directory` 函数。找到：
```python
            if file.lower().endswith((".pdf", ".docx", ".doc")):
```
改为：
```python
            if file.lower().endswith((".pdf", ".docx", ".doc", ".xlsx", ".xls")):
```

同步修改同文件的注释：`"""Recursively search all supported document files (PDF, DOCX, DOC) in the given directory..."""` → `"""Recursively search all supported document files (PDF, DOCX, DOC, XLSX, XLS) in the given directory..."""`。

**- [ ] Step 8.4: 写新枚举值的测试**

Add to `tests/format/test_base.py`:

```python
def test_document_format_has_xlsx():
    assert DocumentFormat.XLSX.value == "xlsx"
    assert DocumentFormat.XLS.value == "xls"
```

（替换掉 Step 5.1 中的占位函数体）

**- [ ] Step 8.5: 扩展 GUI 文件选择器（spec 6.3）**

修改 `translator/gui.py` **第 2380 行** 附近的文件过滤器：

找到：
```python
                                file_types=[".pdf", ".PDF", ".docx", ".doc", ".DOCX", ".DOC"],
```

改为：
```python
                                file_types=[
                                    ".pdf", ".PDF",
                                    ".docx", ".DOCX",
                                    ".doc", ".DOC",
                                    ".xlsx", ".XLSX",
                                    ".xls", ".XLS",
                                ],
```

> `.doc` / `.xls` 加入选择器仅为方便用户可以"选中"文件，实际会被 `validate_file()` 拒绝（Plan 1 Task 7/8 的 WordFormatHandler/XlsxFormatHandler 对这两个扩展名返回 False）。GUI 层应捕获并提示"legacy 格式不支持"——这一提示的代码路径属 Stage 2，Plan 1/2 不覆盖。

**- [ ] Step 8.6: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过（GUI 改动不影响现有测试，因为 tests/ 没覆盖 gradio UI）。

Run: `uv run python -c "import translator.gui; print('gui module imports ok')"`

Expected: 无 ImportError（`gui.py` 里没有独立 `setup_gui` 入口；import 成功即可）。

---

## Task 9: `do_translate_async_stream` 调度层改造

**Files:**
- Modify: `translator/high_level.py`（简化 do_translate_async_stream，改用 handler.translate()）

**- [ ] Step 9.1: 重写 do_translate_async_stream 核心逻辑**

打开 `translator/high_level.py`，找到 `do_translate_async_stream` 函数。当前主体大致是：

```python
# (伪代码)
# 1. 检测 format
# 2. 如果非 PDF, handler.convert_to_pdf() 转成 PDF
# 3. translate_func = partial(_translate_in_subprocess, settings, pdf_file)
# 4. 遍历事件
# 5. cleanup temp files
```

改为：

```python
async def do_translate_async_stream(
    settings: SettingsModel, file: Path | str
) -> AsyncGenerator[dict, None]:
    settings.validate_settings()
    if isinstance(file, str):
        file = Path(file)

    if settings.basic.input_files and len(settings.basic.input_files):
        logger.warning(
            "settings.basic.input_files is for cli & config, "
            "translator.highlevel.do_translate_async_stream will ignore this field "
            "and only translate the file pointed to by the file parameter."
        )

    if not file.exists():
        raise FileNotFoundError(f"file {file} not found")

    # Determine document format
    if settings.basic.input_format == DocumentFormat.AUTO:
        try:
            format_type = detect_document_format(file)
            logger.debug(f"Auto-detected format for {file}: {format_type}")
        except ValueError as e:
            raise ValueError(f"Could not detect format for {file}: {e}") from e
    else:
        format_type = settings.basic.input_format

    # Dispatch to handler
    handler = get_format_handler(format_type)
    logger.info(f"Translating via {handler.__class__.__name__}: {file}")

    try:
        async for event in handler.translate(file, settings):
            yield event
            if settings.basic.debug:
                logger.debug(event)
            if event["type"] == "finish":
                break
    except TranslationError as e:
        logger.error(f"Translation error: {e}")
        if isinstance(e, BabeldocError) and e.original_error:
            logger.error(f"Original babeldoc error: {e.original_error}")
        elif isinstance(e, SubprocessError) and e.traceback_str:
            logger.error(f"Subprocess traceback: {e.traceback_str}")
        error_event = {
            "type": "error",
            "error": str(e) if not isinstance(e, SubprocessError) else e.raw_message,
            "error_type": e.__class__.__name__,
            "details": getattr(e, "original_error", "")
            or getattr(e, "traceback_str", "")
            or "",
        }
        yield error_event
        raise
```

（注意：不再需要 `temp_files` / `handler.cleanup()` / `partial(_translate_in_subprocess, ...)` —— handler 自己管理子进程调用和临时文件。）

**- [ ] Step 9.2: 保留 do_translate_file_async、do_translate_file 不变**

这两个函数里调用 `do_translate_async_stream` 的部分保持不动。它们消费事件流的逻辑不需要改。

**- [ ] Step 9.3: Checkpoint — 静态检查 + 单元测试**

Run: `uv run ruff check translator/high_level.py`

Expected: 无严重错误（Warning 可接受）。

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。

---

## Task 10: 真实 PDF 回归验证

**Files:** （无改动，仅执行）

**- [ ] Step 10.1: 端到端 CLI 验证**

Run:
```
uv run translator --help
```

Expected: 正常打印 help 输出，不报 ImportError。

**- [ ] Step 10.2: 用一个现有测试 PDF 跑翻译（只要能进入翻译流程即可，翻译服务可失败）**

Run:
```
uv run translator test/file/translate.cli.font.unknown.pdf --debug --translate-engine openai --openai-api-key fake_key_for_smoke_test 2>&1 | Select-String -Pattern "Translating via|translate file|error"
```

Expected: 能看到 `Translating via PDFFormatHandler` 字样，说明调度层接通。LLM 调用会失败（fake_key），但**不应该出现 ImportError、AttributeError、KeyError**。

> 如果你有能用的 API key，可以在本地真翻一个小 PDF 完整走通；CI 不跑这一步。

**- [ ] Step 10.3: 全量 pytest 最终回归**

Run: `uv run pytest tests/ test/ -v`

Expected: 全部通过。

**- [ ] Step 10.4: Ruff 检查新/改动的文件**

Run:
```
uv run ruff check translator/format/ translator/pdf_backend/ translator/high_level.py translator/main.py
```

Expected: 无 `error`；`warning` 可接受（遵循现有代码风格）。

**- [ ] Step 10.5: 最终 Checkpoint**

Plan 1 验收标准全部满足：
- ✅ 顶层包已从 `pdf2zh_next` 重命名为 `translator`
- ✅ `translator/engines/` 子包已就位
- ✅ `translator/pdf_backend/` 已下沉 babeldoc 集成
- ✅ `FormatHandler` 接口已改为 `translate()` 事件流
- ✅ `PDFFormatHandler.translate()` 委托 pdf_backend
- ✅ `WordFormatHandler` / `XlsxFormatHandler` 为 Plan 2 预留占位（detect/validate 可用）
- ✅ `DocumentFormat` 枚举含 XLSX/XLS
- ✅ `main.py` 支持 .xlsx/.xls 扩展名发现
- ✅ `gui.py` 文件过滤器已扩展到 Office 扩展名
- ✅ PDF 翻译 pytest 回归全通
- ✅ 未 commit（按用户要求待 Plan 2 完成后一次性提交）

**Plan 1 完成。进入 Plan 2。**

---

## 附录 A — 风险点与缓解

| 风险 | 缓解 |
|---|---|
| `git mv` 在 Windows 文件锁定时失败 | 关闭所有 IDE/进程；如实在不行，用 `Move-Item` + `git add -A` 手动 |
| 批量替换误伤（字符串里的 `pdf2zh_next`） | Step 2.3 脚本用 `\b` 词边界；完成后 `rg "pdf2zh_next"` 扫一遍残留手工复查 |
| `translator.engines` vs `engines` import 混淆 | Step 3.3 强制 `rg "translator\.translator"` 必须 0 匹配 |
| babeldoc 代码迁移时漏了某个内部函数 | Step 4.4 中的"保留清单"明确列出要保留的函数 |
| `do_translate_async_stream` 里异常处理改写出错 | Step 9.1 提供完整新代码；Task 10 回归测试兜底 |
| PyPI 已占用 `translator` 名 | Step 2.4 注释已标注；仅限本地使用 |

## 附录 B — 取消/回滚

整个 Plan 1 都没有 commit，如果中途出问题可以：
1. `git restore --staged .`
2. `git restore .`
3. `git clean -fd translator/ translator/pdf_backend/ translator/format/excel.py`（如已创建）
4. 重跑从 Task 1 开始
