# Plan 2 — Office 格式翻译管线（Word + Excel）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Prerequisites:** Plan 1 必须完全完成（包名已改为 `translator/`，`pdf_backend/` 已下沉，`FormatHandler.translate()` 接口就位，`WordFormatHandler` / `XlsxFormatHandler` 占位 stub 已到位）。

**Goal:** 把 `WordFormatHandler` 和 `XlsxFormatHandler` 的 `translate()` 方法从 `NotImplementedError` 实打实地填好：.docx → .zh.docx、.xlsx → .zh.xlsx，正文段落 + 表格单元格 + Excel 单元格都能被翻译，同时保真度达到 spec 第 10 节验收标准。

**Architecture:** Office 管线不走子进程（在主进程同步+协程运行），通过 `translator.office.OfficeBatchTranslator` 复用 `translator.engines.get_translator(settings)` 提供的 `BaseTranslator.translate(text)`（同步接口，用 `asyncio.to_thread` 并发化）。Word 用 `python-docx` 读写，以段落为翻译单元、dominant-run 回填；Excel 用 `openpyxl` 就地修改字符串单元格。

**Tech Stack:** python-docx、openpyxl、lxml、pytest、asyncio。

**Commit 策略：** 同 Plan 1 —— 全部完成后再一次性 commit（Plan 1 + Plan 2 合并提交）。

---

## Task 顺序

```
Task 1 (text_utils TDD) ──► Task 2 (batch_translator TDD) ──► Task 3 (Word fixtures)
                                                                      │
                                                                      ▼
Task 8 (事件流 & Word.translate()) ◄── Task 7 (OMML 跳过) ◄── Task 6 (表格) ◄── Task 5 (段落 + dominant run 回填) ◄── Task 4 (文本收集器)
                                                                      │
                                                                      ▼
Task 9 (Word 集成测试) ──► Task 10 (Excel fixtures) ──► Task 11 (Excel.translate() 实现) ──► Task 12 (Excel 集成测试) ──► Task 13 (回归 & 手工 e2e)
```

---

## Task 1: `office/text_utils.py` — should_translate 规则（TDD）

**Files:**
- Create: `translator/office/__init__.py`（空）
- Create: `translator/office/text_utils.py`
- Test: `tests/office/__init__.py`（空）
- Test: `tests/office/test_text_utils.py`

**- [ ] Step 1.1: 写失败测试**

Create `tests/office/__init__.py`（空）。

Create `tests/office/test_text_utils.py`:

```python
"""Tests for translator.office.text_utils.should_translate()."""
import pytest

from translator.office.text_utils import should_translate
from translator.office.text_utils import split_preserving_whitespace


class TestShouldTranslate:
    def test_empty_string_is_false(self):
        assert should_translate("") is False

    def test_whitespace_only_is_false(self):
        assert should_translate("   \t\n") is False

    def test_normal_english_sentence_is_true(self):
        assert should_translate("Hello, world!") is True

    def test_single_char_is_false(self):
        assert should_translate("a") is False
        assert should_translate(" I ") is False

    def test_pure_integer_is_false(self):
        assert should_translate("123") is False
        assert should_translate("1234567") is False

    def test_pure_decimal_is_false(self):
        assert should_translate("3.14") is False
        assert should_translate("1,234.56") is False

    def test_pure_symbols_is_false(self):
        assert should_translate("***") is False
        assert should_translate("---") is False
        assert should_translate("—") is False
        assert should_translate("...") is False

    def test_mixed_alpha_and_digits_is_true(self):
        assert should_translate("V2.0") is True
        assert should_translate("iPhone 15") is True

    def test_chinese_is_true(self):
        assert should_translate("中文测试") is True


class TestSplitPreservingWhitespace:
    def test_no_whitespace(self):
        assert split_preserving_whitespace("hello") == ("", "hello", "")

    def test_leading_whitespace(self):
        assert split_preserving_whitespace("  hello") == ("  ", "hello", "")

    def test_trailing_whitespace(self):
        assert split_preserving_whitespace("hello\n") == ("", "hello", "\n")

    def test_both(self):
        assert split_preserving_whitespace("  hello  ") == ("  ", "hello", "  ")

    def test_only_whitespace(self):
        # empty core, all whitespace goes to leading
        lead, core, trail = split_preserving_whitespace("   ")
        assert lead + core + trail == "   "
        assert core == ""
```

**- [ ] Step 1.2: 运行测试验证失败**

Run: `uv run pytest tests/office/test_text_utils.py -v`

Expected: ImportError (`translator.office.text_utils` 不存在)。

**- [ ] Step 1.3: 实现 text_utils**

Write `translator/office/__init__.py`（空，仅作为 package marker）。

Write `translator/office/text_utils.py`:

```python
"""Text filtering utilities for Office translation pipelines."""

from __future__ import annotations

import re

_DIGIT_ONLY_PATTERN = re.compile(r"^[\d.,\s]+$")


def should_translate(text: str) -> bool:
    """Decide if a piece of text is worth sending to the translator.

    Rules (short-circuit in order):
      - Empty or whitespace-only -> False
      - Single character after strip -> False (e.g. "a", "I", "—")
      - Pure digits / decimals / number-like (e.g. "3.14", "1,234.56") -> False
      - No alphanumeric chars at all (pure punctuation / symbols) -> False
      - Otherwise -> True
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) == 1:
        return False
    if _DIGIT_ONLY_PATTERN.match(stripped):
        return False
    if not any(ch.isalnum() for ch in stripped):
        return False
    return True


def split_preserving_whitespace(text: str) -> tuple[str, str, str]:
    """Split text into (leading_ws, core, trailing_ws).

    Used so that after translation we can re-attach the original
    leading/trailing whitespace verbatim (preserves indentation/newlines).
    """
    if not text:
        return ("", "", "")
    lstripped = text.lstrip()
    if not lstripped:
        # all whitespace; bucket everything into `leading`
        return (text, "", "")
    leading = text[: len(text) - len(lstripped)]
    core = lstripped.rstrip()
    trailing = lstripped[len(core):]
    return (leading, core, trailing)
```

**- [ ] Step 1.4: 验证通过**

Run: `uv run pytest tests/office/test_text_utils.py -v`

Expected: 11 个测试全部通过。

**- [ ] Step 1.5: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过（不影响 Plan 1 的测试）。

---

## Task 2: `office/batch_translator.py` — 批量翻译器（TDD）

**Files:**
- Create: `translator/office/batch_translator.py`
- Test: `tests/office/test_batch_translator.py`
- Helper: `tests/office/helpers.py`（MockTranslator）

**- [ ] Step 2.1: 写 MockTranslator helper**

Create `tests/office/helpers.py`:

```python
"""Shared test helpers for Office tests."""
from __future__ import annotations

import time


class MockTranslator:
    """Mimics translator.engines.BaseTranslator.translate() synchronously.

    Returns "[zh]" + text. Records all call args for assertion.
    Optional `delay_ms` simulates slow translation for concurrency tests.
    """

    name = "mock"

    def __init__(self, delay_ms: int = 0):
        self.delay_ms = delay_ms
        self.calls: list[str] = []

    def translate(self, text, ignore_cache=False, rate_limit_params=None):
        self.calls.append(text)
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000.0)
        return f"[zh]{text}"
```

**- [ ] Step 2.2: 写失败测试**

Create `tests/office/test_batch_translator.py`:

```python
"""Tests for translator.office.batch_translator.OfficeBatchTranslator."""
import asyncio
import time

import pytest

from translator.office.batch_translator import OfficeBatchTranslator
from tests.office.helpers import MockTranslator


@pytest.fixture
def mock_translator():
    return MockTranslator()


def test_empty_list(mock_translator):
    bt = OfficeBatchTranslator(mock_translator, qps=4, max_workers=4)
    result = asyncio.run(bt.translate_batch([]))
    assert result == []
    assert mock_translator.calls == []


def test_preserves_order(mock_translator):
    bt = OfficeBatchTranslator(mock_translator, qps=4, max_workers=4)
    inputs = ["alpha", "beta", "gamma"]
    result = asyncio.run(bt.translate_batch(inputs))
    assert result == ["[zh]alpha", "[zh]beta", "[zh]gamma"]


def test_deduplicates(mock_translator):
    """Same text should only call translator once, but appear at all original positions."""
    bt = OfficeBatchTranslator(mock_translator, qps=4, max_workers=4)
    inputs = ["same", "diff", "same", "same"]
    result = asyncio.run(bt.translate_batch(inputs))
    assert result == ["[zh]same", "[zh]diff", "[zh]same", "[zh]same"]
    # "same" should only be translated once despite appearing 3 times
    assert sorted(mock_translator.calls) == sorted(["same", "diff"])


def test_concurrency_faster_than_sequential():
    """Concurrent execution should be noticeably faster than sequential."""
    mt = MockTranslator(delay_ms=100)  # each translate takes 100ms
    bt = OfficeBatchTranslator(mt, qps=4, max_workers=4)
    inputs = [f"t{i}" for i in range(8)]  # 8 unique texts

    start = time.perf_counter()
    result = asyncio.run(bt.translate_batch(inputs))
    elapsed = time.perf_counter() - start

    assert len(result) == 8
    # Sequential would be ~800ms; with 4-way concurrency should be ~200-300ms
    # Allow generous margin for CI slowness: < 600ms
    assert elapsed < 0.6, f"Expected concurrency, took {elapsed:.2f}s"


def test_progress_callback(mock_translator):
    """Progress callback should receive (completed, total) updates."""
    progress_log: list[tuple[int, int]] = []

    bt = OfficeBatchTranslator(mock_translator, qps=4, max_workers=4)
    inputs = [f"t{i}" for i in range(5)]
    asyncio.run(bt.translate_batch(inputs, progress_cb=lambda c, t: progress_log.append((c, t))))

    # Last callback should report (5, 5)
    assert progress_log[-1] == (5, 5)
    # Total calls should equal number of completed items
    assert len(progress_log) == 5


def test_translator_exception_propagates():
    """If translator raises, translate_batch should raise too (fail-fast)."""
    class BoomTranslator:
        name = "boom"
        def translate(self, text, **kwargs):
            raise RuntimeError("kaboom")

    bt = OfficeBatchTranslator(BoomTranslator(), qps=4, max_workers=4)
    with pytest.raises(RuntimeError, match="kaboom"):
        asyncio.run(bt.translate_batch(["x", "y"]))
```

**- [ ] Step 2.3: 运行验证失败**

Run: `uv run pytest tests/office/test_batch_translator.py -v`

Expected: ImportError.

**- [ ] Step 2.4: 实现 batch_translator.py**

Write `translator/office/batch_translator.py`:

```python
"""Batch translator for Office pipelines.

Thin wrapper around translator.engines.BaseTranslator.translate() (synchronous).
Responsibilities:
  - Deduplicate: same text -> one translator call, broadcast result.
  - Concurrency: asyncio.to_thread fan-out bounded by asyncio.Semaphore.
  - QPS limiting: via the semaphore size (simple; caller picks from settings).
  - Progress callback: (completed, total) on each completion.
  - Fail-fast: first exception aborts the rest.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class OfficeBatchTranslator:
    def __init__(self, translator: Any, qps: int, max_workers: int):
        self.translator = translator
        # Use the smaller of qps/max_workers as concurrency bound.
        # QPS here is approximated as concurrency (Office payloads are small
        # enough that each call completes quickly; exact QPS smoothing is
        # already handled by the translator's internal rate_limiter if any).
        self.concurrency = max(1, min(qps, max_workers))

    async def translate_batch(
        self,
        texts: list[str],
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        if not texts:
            return []

        # Deduplicate
        unique = list(dict.fromkeys(texts))  # preserves insertion order
        sem = asyncio.Semaphore(self.concurrency)
        results: dict[str, str] = {}
        completed = [0]
        total = len(texts)

        async def worker(t: str) -> None:
            async with sem:
                translated = await asyncio.to_thread(self.translator.translate, t)
                results[t] = translated
                # Count how many *original* positions this resolves
                count_for_this = sum(1 for x in texts if x == t)
                completed[0] += count_for_this
                if progress_cb:
                    progress_cb(completed[0], total)

        # Fail-fast via asyncio.gather (return_exceptions=False default)
        await asyncio.gather(*(worker(t) for t in unique))

        # Reconstruct in original order
        return [results[t] for t in texts]
```

**- [ ] Step 2.5: 运行验证通过**

Run: `uv run pytest tests/office/test_batch_translator.py -v`

Expected: 6 个测试全部通过。

**- [ ] Step 2.6: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。

---

## Task 3: Word fixtures

**Files:**
- Create: `tests/office/fixtures/__init__.py`（空）
- Create: `tests/office/fixtures/build_docx.py`（一次性生成脚本）
- Create: `tests/office/fixtures/plain.docx` (by running the script)
- Create: `tests/office/fixtures/with_table.docx`
- Create: `tests/office/fixtures/mixed_runs.docx`
- Create: `tests/office/fixtures/with_formula.docx`

**- [ ] Step 3.1: 写 fixture 生成脚本**

Create `tests/office/fixtures/__init__.py`（空）。

Create `tests/office/fixtures/build_docx.py`:

```python
"""Generate Word fixture files for tests.

Run once: `uv run python tests/office/fixtures/build_docx.py`
Output files are committed to the repo (small binary <20KB each).
"""

from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from lxml import etree

HERE = Path(__file__).parent


def build_plain():
    doc = Document()
    doc.add_paragraph("Hello, world.")
    doc.add_paragraph("This is a second paragraph.")
    doc.add_paragraph("")  # empty paragraph (should be skipped)
    doc.add_paragraph("   ")  # whitespace (should be skipped)
    doc.add_paragraph("Third real paragraph with numbers 123.")
    doc.save(HERE / "plain.docx")


def build_with_table():
    doc = Document()
    doc.add_paragraph("Title paragraph.")
    t = doc.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "Row 1 Col 1"
    t.cell(0, 1).text = "Row 1 Col 2"
    t.cell(1, 0).text = "Row 2 Col 1"
    t.cell(1, 1).text = "Row 2 Col 2"
    doc.add_paragraph("Footer paragraph.")
    doc.save(HERE / "with_table.docx")


def build_mixed_runs():
    """Paragraph with bold + normal + italic runs."""
    doc = Document()
    p = doc.add_paragraph("")
    p.add_run("Normal ")
    p.add_run("bold").bold = True
    p.add_run(" and ")
    p.add_run("italic").italic = True
    p.add_run(" here.")
    doc.save(HERE / "mixed_runs.docx")


def build_with_formula():
    """Paragraph that is purely an OMML math formula."""
    doc = Document()
    doc.add_paragraph("Before formula.")
    p = doc.add_paragraph()
    # Inject a minimal OMML <m:oMath> element as a child of <w:p>
    oMath_xml = (
        '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
        '<m:r><m:t>x^2 + y^2 = z^2</m:t></m:r></m:oMath>'
    )
    p._p.append(etree.fromstring(oMath_xml))
    doc.add_paragraph("After formula.")
    doc.save(HERE / "with_formula.docx")


if __name__ == "__main__":
    build_plain()
    build_with_table()
    build_mixed_runs()
    build_with_formula()
    print("Fixtures generated in:", HERE)
```

**- [ ] Step 3.2: 生成 fixtures**

Run: `uv run python tests/office/fixtures/build_docx.py`

Expected: 打印生成路径；`tests/office/fixtures/` 下出现 4 个 `.docx` 文件。

**- [ ] Step 3.3: Checkpoint — 生成的 docx 能被打开**

Run:
```
uv run python -c "from docx import Document; import pathlib; [print(f, len(Document(f).paragraphs), 'paragraphs') for f in pathlib.Path('tests/office/fixtures').glob('*.docx')]"
```

Expected: 4 个文件均能打开，打印各自段落数。

---

## Task 4: Word 管线 — 文本收集器（TDD）

**Files:**
- Create: `translator/format/word_pipeline/__init__.py`（空）
- Create: `translator/format/word_pipeline/collector.py`
- Test: `tests/office/test_word_collector.py`

> 把 Word 管线的实现拆到子包 `word_pipeline/` 以保持 `word.py` 只作为 handler 入口，便于单测。

**- [ ] Step 4.1: 写失败测试**

Create `tests/office/test_word_collector.py`:

```python
"""Tests for Word paragraph text collection."""
from pathlib import Path

import pytest
from docx import Document

from translator.format.word_pipeline.collector import WordTextUnit
from translator.format.word_pipeline.collector import collect_translation_units

FIXTURES = Path(__file__).parent / "fixtures"


def test_collect_plain_yields_non_empty_paragraphs_only():
    doc = Document(FIXTURES / "plain.docx")
    units = collect_translation_units(doc)
    texts = [u.text for u in units]
    assert "Hello, world." in texts
    assert "This is a second paragraph." in texts
    assert "Third real paragraph with numbers 123." in texts
    # Empty/whitespace paragraphs filtered
    assert "" not in texts
    assert "   " not in texts


def test_collect_table_cells():
    doc = Document(FIXTURES / "with_table.docx")
    units = collect_translation_units(doc)
    texts = [u.text for u in units]
    assert "Title paragraph." in texts
    assert "Row 1 Col 1" in texts
    assert "Row 2 Col 2" in texts
    assert "Footer paragraph." in texts


def test_collect_skips_pure_formula_paragraph():
    doc = Document(FIXTURES / "with_formula.docx")
    units = collect_translation_units(doc)
    texts = [u.text for u in units]
    assert "Before formula." in texts
    assert "After formula." in texts
    # Pure formula paragraph must NOT be in units
    assert not any("x^2" in t for t in texts)


def test_collect_mixed_runs_produces_single_unit_with_concatenated_text():
    doc = Document(FIXTURES / "mixed_runs.docx")
    units = collect_translation_units(doc)
    assert len(units) == 1
    u = units[0]
    assert u.text == "Normal bold and italic here."
    # dominant_run_index must point to the longest run
    # "Normal " (7) vs "bold" (4) vs " and " (5) vs "italic" (6) vs " here." (6)
    # Actually " here." has a leading space, length 6
    # Longest is "Normal " at 7
    assert u.dominant_run_index == 0


def test_word_text_unit_has_required_fields():
    u = WordTextUnit(
        paragraph_element=None,
        run_count=3,
        dominant_run_index=1,
        text="hello",
    )
    assert u.text == "hello"
    assert u.run_count == 3
    assert u.dominant_run_index == 1
```

**- [ ] Step 4.2: 运行验证失败**

Run: `uv run pytest tests/office/test_word_collector.py -v`

Expected: ImportError.

**- [ ] Step 4.3: 实现 collector**

Create `translator/format/word_pipeline/__init__.py`（空）。

Write `translator/format/word_pipeline/collector.py`:

```python
"""Collect translation units from a python-docx Document.

A translation unit = one paragraph's concatenated run text.
Tables are walked: each cell's paragraphs are also units.
Paragraphs containing OMML math are skipped (spec stage 1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from translator.office.text_utils import should_translate

if TYPE_CHECKING:
    from docx.document import Document
    from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)

# OMML namespaces appearing as children of <w:p>
_OMML_NS_URIS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/math",
)
_OMML_LOCAL_NAMES = ("oMath", "oMathPara")


@dataclass
class WordTextUnit:
    """A paragraph-level translation unit.

    paragraph_element: the underlying lxml <w:p> element (for injection back)
    run_count: total number of runs at collection time (for diagnostics)
    dominant_run_index: index of the run chosen to receive translated text
    text: concatenated run text (what we send to the translator)
    """
    paragraph_element: object
    run_count: int
    dominant_run_index: int
    text: str


def _has_omml(paragraph: Paragraph) -> bool:
    """Return True if the paragraph XML contains any OMML math element."""
    p = paragraph._p
    for child in p.iter():
        tag = child.tag  # "{uri}local"
        if not isinstance(tag, str) or "}" not in tag:
            continue
        uri = tag.split("}", 1)[0].lstrip("{")
        local = tag.split("}", 1)[1]
        if uri in _OMML_NS_URIS and local in _OMML_LOCAL_NAMES:
            return True
    return False


def _paragraph_to_unit(paragraph: Paragraph) -> WordTextUnit | None:
    """Build a translation unit for one paragraph, or None if it should be skipped."""
    if _has_omml(paragraph):
        logger.debug("Skipping paragraph with OMML math")
        return None

    runs = paragraph.runs
    if not runs:
        return None

    concatenated = "".join(r.text for r in runs)
    if not should_translate(concatenated):
        return None

    # dominant run = longest by text length; ties -> first
    dominant_idx = 0
    max_len = len(runs[0].text)
    for i, r in enumerate(runs[1:], start=1):
        if len(r.text) > max_len:
            max_len = len(r.text)
            dominant_idx = i

    return WordTextUnit(
        paragraph_element=paragraph._p,
        run_count=len(runs),
        dominant_run_index=dominant_idx,
        text=concatenated,
    )


def collect_translation_units(doc: Document) -> list[WordTextUnit]:
    """Walk the document and return all translation units in visiting order.

    Order: body paragraphs first (top-to-bottom), then table cells (row-major).
    Matches the order in which they'll be written back.
    """
    units: list[WordTextUnit] = []

    for p in doc.paragraphs:
        u = _paragraph_to_unit(p)
        if u is not None:
            units.append(u)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    u = _paragraph_to_unit(p)
                    if u is not None:
                        units.append(u)

    return units
```

**- [ ] Step 4.4: 运行验证**

Run: `uv run pytest tests/office/test_word_collector.py -v`

Expected: 5 个测试全部通过。

**- [ ] Step 4.5: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。

---

## Task 5: Word 管线 — dominant-run 回填（TDD）

**Files:**
- Create: `translator/format/word_pipeline/writer.py`
- Test: `tests/office/test_word_writer.py`

**- [ ] Step 5.1: 写失败测试**

Create `tests/office/test_word_writer.py`:

```python
"""Tests for Word dominant-run writeback."""
from pathlib import Path

import pytest
from docx import Document

from translator.format.word_pipeline.collector import collect_translation_units
from translator.format.word_pipeline.writer import apply_translations

FIXTURES = Path(__file__).parent / "fixtures"


def test_writeback_plain_replaces_paragraph_text(tmp_path):
    src = FIXTURES / "plain.docx"
    doc = Document(src)
    units = collect_translation_units(doc)
    # Pretend to translate: upper-case
    translations = [u.text.upper() for u in units]
    apply_translations(units, translations)

    out = tmp_path / "out.docx"
    doc.save(out)

    # Re-open and verify
    d2 = Document(out)
    all_text = "\n".join(p.text for p in d2.paragraphs)
    assert "HELLO, WORLD." in all_text
    assert "THIS IS A SECOND PARAGRAPH." in all_text


def test_writeback_mixed_runs_preserves_run_count(tmp_path):
    """Run count MUST be preserved: non-dominant runs kept but text cleared."""
    doc = Document(FIXTURES / "mixed_runs.docx")
    units = collect_translation_units(doc)
    assert len(units) == 1
    original_run_count = units[0].run_count
    apply_translations(units, ["TRANSLATED"])

    # Reload to check persistence
    out = tmp_path / "mixed_out.docx"
    doc.save(out)
    d2 = Document(out)
    p = d2.paragraphs[0]
    assert len(p.runs) == original_run_count
    # dominant run (index 0, the first run) got the translation
    assert p.runs[0].text == "TRANSLATED"
    # Other runs cleared to empty text
    for r in p.runs[1:]:
        assert r.text == ""


def test_writeback_preserves_dominant_run_formatting(tmp_path):
    """The dominant run's formatting (bold/italic) must be preserved."""
    doc = Document(FIXTURES / "mixed_runs.docx")
    units = collect_translation_units(doc)
    apply_translations(units, ["TRANS"])

    out = tmp_path / "mixed2.docx"
    doc.save(out)
    d2 = Document(out)
    # dominant run is run 0 ("Normal "), which has no bold; verify it's still not bold
    assert d2.paragraphs[0].runs[0].bold is not True  # None or False
```

**- [ ] Step 5.2: 运行失败**

Run: `uv run pytest tests/office/test_word_writer.py -v`

Expected: ImportError.

**- [ ] Step 5.3: 实现 writer**

Write `translator/format/word_pipeline/writer.py`:

```python
"""Dominant-run writeback of translated text into python-docx paragraphs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from translator.format.word_pipeline.collector import WordTextUnit

logger = logging.getLogger(__name__)


def apply_translations(
    units: list[WordTextUnit],
    translations: list[str],
) -> None:
    """Write translated strings back into the underlying paragraphs.

    Rules:
      - translation goes entirely into the dominant run
      - non-dominant runs have their .text cleared to '' (run object + formatting retained)
    """
    if len(units) != len(translations):
        raise ValueError(
            f"units/translations length mismatch: {len(units)} vs {len(translations)}"
        )

    for unit, translated in zip(units, translations, strict=True):
        # paragraph_element is a <w:p> lxml element; find its runs via XPath
        # But python-docx keeps runs attached to Paragraph. We walk <w:r> children.
        p_element = unit.paragraph_element
        run_elements = [
            c for c in p_element
            if isinstance(c.tag, str) and c.tag.endswith("}r")
        ]
        if len(run_elements) == 0:
            logger.warning("Paragraph has no runs; skipping writeback")
            continue

        for i, r_elem in enumerate(run_elements):
            # A <w:r> contains <w:t> (text) children. Clear them all.
            # Then, if this is the dominant run, set the first <w:t> to translated.
            t_elements = [
                c for c in r_elem
                if isinstance(c.tag, str) and c.tag.endswith("}t")
            ]
            for t in t_elements:
                t.text = ""

            if i == unit.dominant_run_index:
                if t_elements:
                    # Preserve xml:space="preserve" by using the first <w:t>
                    t_elements[0].text = translated
                else:
                    # No <w:t> child (shouldn't happen if run had text); create one
                    from lxml import etree
                    # Use same namespace as <w:r>
                    ns = r_elem.tag.split("}", 1)[0].lstrip("{")
                    new_t = etree.SubElement(r_elem, f"{{{ns}}}t")
                    new_t.text = translated
                    new_t.set(
                        "{http://www.w3.org/XML/1998/namespace}space", "preserve"
                    )
```

**- [ ] Step 5.4: 运行通过**

Run: `uv run pytest tests/office/test_word_writer.py -v`

Expected: 3 个测试全部通过。

**- [ ] Step 5.5: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。

---

## Task 6: Word 管线 — 表格单元格端到端覆盖

**Files:** （无新代码，仅测试验证 collector+writer 已覆盖表格）
- Test: `tests/office/test_word_table_e2e.py`

**- [ ] Step 6.1: 写集成测试**

Create `tests/office/test_word_table_e2e.py`:

```python
"""End-to-end: table cells survive the collector+writer pipeline."""
from pathlib import Path

from docx import Document

from translator.format.word_pipeline.collector import collect_translation_units
from translator.format.word_pipeline.writer import apply_translations

FIXTURES = Path(__file__).parent / "fixtures"


def test_table_cells_translated(tmp_path):
    doc = Document(FIXTURES / "with_table.docx")
    units = collect_translation_units(doc)
    # Should have: 1 title + 4 cells + 1 footer = 6 units
    assert len(units) == 6

    translations = [f"[T]{u.text}" for u in units]
    apply_translations(units, translations)

    out = tmp_path / "table_out.docx"
    doc.save(out)

    d2 = Document(out)
    # Verify title
    assert d2.paragraphs[0].text.startswith("[T]")
    # Verify all 4 table cells start with [T]
    cells_text = []
    for table in d2.tables:
        for row in table.rows:
            for cell in row.cells:
                cells_text.append(cell.text)
    assert all(t.startswith("[T]") for t in cells_text)
    assert len(cells_text) == 4


def test_table_structure_preserved(tmp_path):
    """Row/col count and cell borders must survive the write cycle."""
    doc = Document(FIXTURES / "with_table.docx")
    units = collect_translation_units(doc)
    apply_translations(units, ["X"] * len(units))

    out = tmp_path / "struct.docx"
    doc.save(out)

    d2 = Document(out)
    assert len(d2.tables) == 1
    t = d2.tables[0]
    assert len(t.rows) == 2
    assert len(t.columns) == 2
```

**- [ ] Step 6.2: 运行**

Run: `uv run pytest tests/office/test_word_table_e2e.py -v`

Expected: 2 个测试全部通过。

**- [ ] Step 6.3: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。

---

## Task 7: Word 管线 — OMML 公式保留验证

**Files:** （仅测试）
- Test: `tests/office/test_word_formula_preservation.py`

**- [ ] Step 7.1: 写测试**

Create `tests/office/test_word_formula_preservation.py`:

```python
"""OMML paragraphs must pass through unchanged (spec stage 1 guarantee)."""
from pathlib import Path

from docx import Document

from translator.format.word_pipeline.collector import collect_translation_units
from translator.format.word_pipeline.writer import apply_translations

FIXTURES = Path(__file__).parent / "fixtures"


def test_formula_paragraph_not_in_units():
    doc = Document(FIXTURES / "with_formula.docx")
    units = collect_translation_units(doc)
    assert all("x^2" not in u.text for u in units)


def test_formula_paragraph_text_unchanged_after_pipeline(tmp_path):
    """After collect+translate+write, the formula paragraph's XML is bit-identical."""
    src = FIXTURES / "with_formula.docx"
    doc = Document(src)

    # Snapshot the formula paragraph XML BEFORE
    formula_paragraphs_before = []
    for p in doc.paragraphs:
        # OMML paragraphs have children whose tag ends with }oMath
        has_omml = any(
            (isinstance(c.tag, str) and c.tag.endswith("}oMath"))
            for c in p._p.iter()
        )
        if has_omml:
            from lxml import etree
            formula_paragraphs_before.append(etree.tostring(p._p))

    assert len(formula_paragraphs_before) == 1

    # Run full pipeline
    units = collect_translation_units(doc)
    apply_translations(units, [u.text.upper() for u in units])

    out = tmp_path / "f.docx"
    doc.save(out)
    d2 = Document(out)

    formula_paragraphs_after = []
    for p in d2.paragraphs:
        has_omml = any(
            (isinstance(c.tag, str) and c.tag.endswith("}oMath"))
            for c in p._p.iter()
        )
        if has_omml:
            from lxml import etree
            formula_paragraphs_after.append(etree.tostring(p._p))

    assert formula_paragraphs_after == formula_paragraphs_before
```

**- [ ] Step 7.2: 运行**

Run: `uv run pytest tests/office/test_word_formula_preservation.py -v`

Expected: 2 个测试通过。

**- [ ] Step 7.3: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。

---

## Task 8: Word handler — translate() 事件流实装

**Files:**
- Modify: `translator/format/word.py`（从 NotImplementedError 的 stub 改为真实实现）
- Test: `tests/office/test_word_handler.py`

**- [ ] Step 8.1: 写集成测试**

Create `tests/office/test_word_handler.py`:

```python
"""Integration test: WordFormatHandler.translate() full pipeline with MockTranslator."""
import asyncio
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from docx import Document

from translator.format.word import WordFormatHandler
from tests.office.helpers import MockTranslator

FIXTURES = Path(__file__).parent / "fixtures"


def _make_settings(output_dir: Path, qps=4, pool=4):
    """Minimal settings object for handler.translate()."""
    from translator.config.model import SettingsModel
    s = SettingsModel()
    s.translation.lang_in = "en"
    s.translation.lang_out = "zh"
    s.translation.qps = qps
    s.translation.pool_max_workers = pool
    s.translation.output = str(output_dir)
    return s


def test_word_handler_full_pipeline(tmp_path):
    src = FIXTURES / "plain.docx"
    work = tmp_path / "plain.docx"
    shutil.copy(src, work)

    settings = _make_settings(tmp_path)
    mock_t = MockTranslator()

    with patch("translator.format.word.get_translator", return_value=mock_t):
        handler = WordFormatHandler()

        async def run():
            events = []
            async for ev in handler.translate(work, settings):
                events.append(ev)
            return events

        events = asyncio.run(run())

    # Must emit progress + finish
    event_types = [e["type"] for e in events]
    assert "progress" in event_types
    assert event_types[-1] == "finish"

    # Translator must have been called for each translatable paragraph
    assert len(mock_t.calls) >= 1

    # Output file exists and contains translated text
    finish = events[-1]
    out_path = Path(finish["translate_result"].translated_path)
    assert out_path.exists()
    assert out_path.name == "plain.zh.docx"

    d2 = Document(out_path)
    all_text = "\n".join(p.text for p in d2.paragraphs)
    assert "[zh]" in all_text


def test_word_handler_doc_format_rejected(tmp_path):
    """.doc files should be rejected at validate_file(). handler.translate() for doc path
    is also a no-op guarded by validate_file returning False in detect."""
    handler = WordFormatHandler()
    fake_doc = tmp_path / "legacy.doc"
    fake_doc.write_bytes(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1" + b"\x00" * 100)
    assert handler.detect_format(fake_doc) is False
    assert handler.validate_file(fake_doc) is False
```

**- [ ] Step 8.2: 运行验证失败**

Run: `uv run pytest tests/office/test_word_handler.py -v`

Expected: AssertionError 或 NotImplementedError（stub 仍在）。

**- [ ] Step 8.3: 实现 translate()**

Overwrite `translator/format/word.py` (完整替换 Plan 1 的 stub 实现):

```python
"""Word document format handler - full pipeline (docx -> docx)."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from translator.format.base import DocumentFormat
from translator.format.base import FormatHandler
from translator.format.word_pipeline.collector import collect_translation_units
from translator.format.word_pipeline.writer import apply_translations
from translator.office.batch_translator import OfficeBatchTranslator

if TYPE_CHECKING:
    from translator.config.model import SettingsModel

logger = logging.getLogger(__name__)


@dataclass
class WordTranslateResult:
    """Mimics babeldoc TranslationResult shape for event consumers."""
    original_path: str
    translated_path: str
    total_seconds: float
    mono_pdf_path: str | None = None  # for GUI/CLI compatibility
    dual_pdf_path: str | None = None


# Lazy import so tests can patch translator.format.word.get_translator easily
from translator.engines import get_translator  # noqa: E402


class WordFormatHandler(FormatHandler):
    """.docx handler: paragraph-level translation with dominant-run writeback."""

    def get_format(self) -> DocumentFormat:
        return DocumentFormat.DOCX

    def detect_format(self, file_path: Path) -> bool:
        if not file_path.exists():
            return False
        if file_path.suffix.lower() != ".docx":
            return False
        try:
            import zipfile
            with zipfile.ZipFile(file_path, "r") as zf:
                return any(n.startswith("word/") for n in zf.namelist())
        except Exception:
            return False

    def validate_file(self, file_path: Path) -> bool:
        if not self.detect_format(file_path):
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
        import docx
        start = time.perf_counter()

        # Stage: reading
        yield {"type": "progress", "overall_progress": 0.05, "stage": "reading"}
        doc = docx.Document(input_file)

        # Stage: collecting
        yield {"type": "progress", "overall_progress": 0.10, "stage": "collecting"}
        units = collect_translation_units(doc)
        texts = [u.text for u in units]
        logger.info(f"Collected {len(texts)} translation units from {input_file}")

        # Stage: translating (fan out via OfficeBatchTranslator)
        translator_obj = get_translator(settings)
        bt = OfficeBatchTranslator(
            translator_obj,
            qps=settings.translation.qps,
            max_workers=settings.translation.pool_max_workers,
        )

        progress_queue: list[tuple[int, int]] = []

        def on_progress(done: int, total: int) -> None:
            progress_queue.append((done, total))

        # Run the batch (await once, then we'll emit progress post-hoc from the queue)
        # NB: for fine-grained streaming progress, future work can refactor this to
        # an async queue. Stage 1 emits coarse progress at start/end of translating.
        if texts:
            translations = await bt.translate_batch(texts, progress_cb=on_progress)
        else:
            translations = []

        # Emit a single translating-done progress event (simple Stage-1 approach)
        yield {"type": "progress", "overall_progress": 0.85, "stage": "translating"}

        # Stage: writing
        yield {"type": "progress", "overall_progress": 0.95, "stage": "writing"}
        apply_translations(units, translations)

        output_dir = Path(settings.translation.output) if settings.translation.output else input_file.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{input_file.stem}.zh.docx"
        doc.save(output_path)

        elapsed = time.perf_counter() - start
        result = WordTranslateResult(
            original_path=str(input_file),
            translated_path=str(output_path),
            total_seconds=elapsed,
        )

        yield {
            "type": "finish",
            "translate_result": result,
            "token_usage": {},  # Office handlers don't track LLM tokens directly
        }
```

**- [ ] Step 8.4: 运行验证**

Run: `uv run pytest tests/office/test_word_handler.py -v`

Expected: 2 个测试全部通过。

**- [ ] Step 8.5: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。

---

## Task 9: Word 端到端健全测试

**Files:** （无新代码）

**- [ ] Step 9.1: 验证 `do_translate_async_stream` 接通 Word handler**

Create `tests/office/test_word_high_level.py`:

```python
"""Verify high_level.do_translate_async_stream dispatches to WordFormatHandler."""
import asyncio
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from translator.format.base import DocumentFormat
from translator.high_level import do_translate_async_stream
from tests.office.helpers import MockTranslator

FIXTURES = Path(__file__).parent / "fixtures"


def _make_settings(output_dir: Path):
    from translator.config.model import SettingsModel
    s = SettingsModel()
    s.translation.lang_in = "en"
    s.translation.lang_out = "zh"
    s.translation.qps = 4
    s.translation.pool_max_workers = 4
    s.translation.output = str(output_dir)
    s.basic.input_format = DocumentFormat.AUTO
    s.basic.input_files = set()
    # Use a translate engine that won't fail on construction;
    # we mock the actual translator object via get_translator patch.
    return s


def test_do_translate_async_stream_dispatches_to_word_handler(tmp_path, monkeypatch):
    src = FIXTURES / "plain.docx"
    work = tmp_path / "plain.docx"
    shutil.copy(src, work)

    settings = _make_settings(tmp_path)

    with patch("translator.format.word.get_translator", return_value=MockTranslator()):
        # validate_settings() may require a real translator config; bypass if needed
        with patch.object(type(settings), "validate_settings", lambda self: None):

            async def run():
                events = []
                async for ev in do_translate_async_stream(settings, work):
                    events.append(ev)
                return events

            events = asyncio.run(run())

    assert events[-1]["type"] == "finish"
    out = Path(events[-1]["translate_result"].translated_path)
    assert out.exists()
    assert out.name == "plain.zh.docx"
```

**- [ ] Step 9.2: 运行**

Run: `uv run pytest tests/office/test_word_high_level.py -v`

Expected: 通过。

**- [ ] Step 9.3: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。

---

## Task 10: Excel fixtures

**Files:**
- Create: `tests/office/fixtures/build_xlsx.py`
- Create: `tests/office/fixtures/single_sheet.xlsx`
- Create: `tests/office/fixtures/multi_sheet.xlsx`
- Create: `tests/office/fixtures/with_formulas.xlsx`
- Create: `tests/office/fixtures/with_merged.xlsx`

**- [ ] Step 10.1: 写生成脚本**

Create `tests/office/fixtures/build_xlsx.py`:

```python
"""Generate Excel fixture files."""

from datetime import date
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font

HERE = Path(__file__).parent


def build_single_sheet():
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    rows = [
        ["Apple", "Banana", "Cherry"],
        ["Dog", "Elephant", "Fox"],
        ["Hello", "World", "!"],
    ]
    for row in rows:
        ws.append(row)
    # a pure-number row
    ws.append([1, 2, 3])
    wb.save(HERE / "single_sheet.xlsx")


def build_multi_sheet():
    wb = Workbook()
    wb.active.title = "Sheet A"
    wb.active["A1"] = "Hello"
    wb.active["B1"] = "World"

    s2 = wb.create_sheet("Sheet B")
    s2["A1"] = "Another text"
    s2["A2"] = "More text"

    s3 = wb.create_sheet("Sheet C")
    s3["A1"] = "Third"

    wb.save(HERE / "multi_sheet.xlsx")


def build_with_formulas():
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Label"
    ws["A2"] = 10
    ws["A3"] = 20
    ws["A4"] = "=SUM(A2:A3)"   # formula
    ws["B1"] = "Also a label"
    wb.save(HERE / "with_formulas.xlsx")


def build_with_merged():
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Merged Title"
    ws.merge_cells("A1:C1")
    ws["A2"] = "Col1"
    ws["B2"] = "Col2"
    ws["C2"] = "Col3"
    ws["A3"] = date(2026, 1, 1)
    ws["B3"] = 42
    ws["C3"] = "Some text"
    wb.save(HERE / "with_merged.xlsx")


if __name__ == "__main__":
    build_single_sheet()
    build_multi_sheet()
    build_with_formulas()
    build_with_merged()
    print("XLSX fixtures generated in:", HERE)
```

**- [ ] Step 10.2: 生成**

Run: `uv run python tests/office/fixtures/build_xlsx.py`

Expected: 4 个 `.xlsx` 文件生成。

---

## Task 11: Excel handler — translate() 实装

**Files:**
- Modify: `translator/format/excel.py`（替换 Plan 1 stub）
- Test: `tests/office/test_excel_handler.py`

**- [ ] Step 11.1: 写测试**

Create `tests/office/test_excel_handler.py`:

```python
"""Integration tests for XlsxFormatHandler."""
import asyncio
import shutil
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from openpyxl import load_workbook

from translator.format.excel import XlsxFormatHandler
from tests.office.helpers import MockTranslator

FIXTURES = Path(__file__).parent / "fixtures"


def _make_settings(output_dir):
    from translator.config.model import SettingsModel
    s = SettingsModel()
    s.translation.lang_in = "en"
    s.translation.lang_out = "zh"
    s.translation.qps = 4
    s.translation.pool_max_workers = 4
    s.translation.output = str(output_dir)
    return s


def test_single_sheet_strings_translated(tmp_path):
    src = FIXTURES / "single_sheet.xlsx"
    work = tmp_path / "single_sheet.xlsx"
    shutil.copy(src, work)

    mt = MockTranslator()
    settings = _make_settings(tmp_path)
    with patch("translator.format.excel.get_translator", return_value=mt):
        handler = XlsxFormatHandler()

        async def run():
            events = []
            async for ev in handler.translate(work, settings):
                events.append(ev)
            return events

        events = asyncio.run(run())

    assert events[-1]["type"] == "finish"
    out = Path(events[-1]["translate_result"].translated_path)
    assert out.exists()
    assert out.name == "single_sheet.zh.xlsx"

    wb = load_workbook(out)
    ws = wb.active
    assert ws["A1"].value == "[zh]Apple"
    # Number rows should NOT be translated
    assert ws["A4"].value == 1
    assert ws["B4"].value == 2


def test_formulas_preserved(tmp_path):
    src = FIXTURES / "with_formulas.xlsx"
    work = tmp_path / "with_formulas.xlsx"
    shutil.copy(src, work)

    mt = MockTranslator()
    settings = _make_settings(tmp_path)
    with patch("translator.format.excel.get_translator", return_value=mt):
        handler = XlsxFormatHandler()

        async def run():
            async for _ in handler.translate(work, settings):
                pass

        asyncio.run(run())

    out = tmp_path / "with_formulas.zh.xlsx"
    wb = load_workbook(out)
    ws = wb.active
    # Label got translated
    assert ws["A1"].value == "[zh]Label"
    # Formula cell preserved as formula string
    assert ws["A4"].value == "=SUM(A2:A3)"
    # Numbers untouched
    assert ws["A2"].value == 10


def test_multi_sheet(tmp_path):
    src = FIXTURES / "multi_sheet.xlsx"
    work = tmp_path / "multi_sheet.xlsx"
    shutil.copy(src, work)

    mt = MockTranslator()
    settings = _make_settings(tmp_path)
    with patch("translator.format.excel.get_translator", return_value=mt):
        handler = XlsxFormatHandler()
        async def run():
            async for _ in handler.translate(work, settings):
                pass
        asyncio.run(run())

    out = tmp_path / "multi_sheet.zh.xlsx"
    wb = load_workbook(out)
    assert wb["Sheet A"]["A1"].value == "[zh]Hello"
    assert wb["Sheet B"]["A1"].value == "[zh]Another text"
    assert wb["Sheet C"]["A1"].value == "[zh]Third"


def test_merged_cells_and_date_preserved(tmp_path):
    src = FIXTURES / "with_merged.xlsx"
    work = tmp_path / "with_merged.xlsx"
    shutil.copy(src, work)

    mt = MockTranslator()
    settings = _make_settings(tmp_path)
    with patch("translator.format.excel.get_translator", return_value=mt):
        handler = XlsxFormatHandler()
        async def run():
            async for _ in handler.translate(work, settings):
                pass
        asyncio.run(run())

    out = tmp_path / "with_merged.zh.xlsx"
    wb = load_workbook(out)
    ws = wb.active
    # merged title translated
    assert ws["A1"].value == "[zh]Merged Title"
    # merged range preserved
    assert "A1:C1" in [str(r) for r in ws.merged_cells.ranges]
    # Date preserved as date object
    assert ws["A3"].value == date(2026, 1, 1)
    # Number preserved
    assert ws["B3"].value == 42
    # String translated
    assert ws["C3"].value == "[zh]Some text"
```

**- [ ] Step 11.2: 运行失败**

Run: `uv run pytest tests/office/test_excel_handler.py -v`

Expected: 失败或 NotImplementedError（Plan 1 stub 仍在）。

**- [ ] Step 11.3: 实装**

Overwrite `translator/format/excel.py`:

```python
"""Excel format handler (.xlsx) - full pipeline."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from translator.format.base import DocumentFormat
from translator.format.base import FormatHandler
from translator.office.batch_translator import OfficeBatchTranslator
from translator.office.text_utils import should_translate

if TYPE_CHECKING:
    from translator.config.model import SettingsModel

logger = logging.getLogger(__name__)


@dataclass
class ExcelTranslateResult:
    original_path: str
    translated_path: str
    total_seconds: float
    mono_pdf_path: str | None = None
    dual_pdf_path: str | None = None


from translator.engines import get_translator  # noqa: E402


class XlsxFormatHandler(FormatHandler):
    """.xlsx handler. .xls (legacy binary) is NOT supported."""

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
        if not self.detect_format(file_path):
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
        import openpyxl
        start = time.perf_counter()

        # Stage: reading
        yield {"type": "progress", "overall_progress": 0.05, "stage": "reading"}
        wb = openpyxl.load_workbook(input_file)

        # Stage: collecting
        yield {"type": "progress", "overall_progress": 0.10, "stage": "collecting"}
        # collected: list of (sheet_name, cell_coord, original_text)
        targets: list[tuple[str, str, str]] = []
        for ws_name in wb.sheetnames:
            ws = wb[ws_name]
            for row in ws.iter_rows():
                for cell in row:
                    v = cell.value
                    if not isinstance(v, str):
                        continue
                    if v.startswith("="):  # formula
                        continue
                    if not should_translate(v):
                        continue
                    targets.append((ws_name, cell.coordinate, v))

        # Stage: translating
        translator_obj = get_translator(settings)
        bt = OfficeBatchTranslator(
            translator_obj,
            qps=settings.translation.qps,
            max_workers=settings.translation.pool_max_workers,
        )
        texts = [t[2] for t in targets]
        if texts:
            translations = await bt.translate_batch(texts)
        else:
            translations = []
        yield {"type": "progress", "overall_progress": 0.85, "stage": "translating"}

        # Stage: writing (write back)
        yield {"type": "progress", "overall_progress": 0.95, "stage": "writing"}
        for (ws_name, coord, _original), translated in zip(targets, translations, strict=True):
            wb[ws_name][coord].value = translated

        output_dir = Path(settings.translation.output) if settings.translation.output else input_file.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{input_file.stem}.zh.xlsx"
        wb.save(output_path)

        elapsed = time.perf_counter() - start
        result = ExcelTranslateResult(
            original_path=str(input_file),
            translated_path=str(output_path),
            total_seconds=elapsed,
        )

        yield {
            "type": "finish",
            "translate_result": result,
            "token_usage": {},
        }
```

**- [ ] Step 11.4: 运行通过**

Run: `uv run pytest tests/office/test_excel_handler.py -v`

Expected: 4 个测试全部通过。

**- [ ] Step 11.5: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。

---

## Task 12: Excel high_level 调度测试

**Files:**
- Test: `tests/office/test_excel_high_level.py`

**- [ ] Step 12.1: 写测试**

Create `tests/office/test_excel_high_level.py`:

```python
"""Verify do_translate_async_stream dispatches to XlsxFormatHandler."""
import asyncio
import shutil
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from translator.format.base import DocumentFormat
from translator.high_level import do_translate_async_stream
from tests.office.helpers import MockTranslator

FIXTURES = Path(__file__).parent / "fixtures"


def _make_settings(output_dir):
    from translator.config.model import SettingsModel
    s = SettingsModel()
    s.translation.lang_in = "en"
    s.translation.lang_out = "zh"
    s.translation.qps = 4
    s.translation.pool_max_workers = 4
    s.translation.output = str(output_dir)
    s.basic.input_format = DocumentFormat.AUTO
    s.basic.input_files = set()
    return s


def test_xlsx_dispatched_through_high_level(tmp_path):
    src = FIXTURES / "single_sheet.xlsx"
    work = tmp_path / "single_sheet.xlsx"
    shutil.copy(src, work)

    settings = _make_settings(tmp_path)

    with patch("translator.format.excel.get_translator", return_value=MockTranslator()):
        with patch.object(type(settings), "validate_settings", lambda self: None):
            async def run():
                events = []
                async for ev in do_translate_async_stream(settings, work):
                    events.append(ev)
                return events
            events = asyncio.run(run())

    assert events[-1]["type"] == "finish"
    out = Path(events[-1]["translate_result"].translated_path)
    assert out.name == "single_sheet.zh.xlsx"
    wb = load_workbook(out)
    assert wb.active["A1"].value == "[zh]Apple"
```

**- [ ] Step 12.2: 运行**

Run: `uv run pytest tests/office/test_excel_high_level.py -v`

Expected: 通过。

**- [ ] Step 12.3: Checkpoint**

Run: `uv run pytest tests/ -x -q`

Expected: 全部通过。

---

## Task 13: 全量回归 + 手工 e2e 验证

**- [ ] Step 13.1: 全量 pytest**

Run: `uv run pytest tests/ test/ -v`

Expected: 全部通过，包含：
- 所有 PDF 回归测试
- 所有 `tests/office/` 新测试

**- [ ] Step 13.2: Ruff 检查**

Run:
```
uv run ruff check translator/office/ translator/format/word.py translator/format/word_pipeline/ translator/format/excel.py tests/office/
```

Expected: 无 `error`。

**- [ ] Step 13.3: CLI 端到端（手工跑一个真实 docx）**

用户自行准备一个 `sample.docx`，然后：

Run:
```
uv run translator sample.docx --translate-engine openai --openai-api-key <your_key>
```

Expected:
- 控制台输出 `Translating via WordFormatHandler`
- 生成 `sample.zh.docx`
- 用 Word 打开后：正文段落翻译、表格单元格翻译、段落级样式保留、公式/图片/页眉脚原样保留

**- [ ] Step 13.4: CLI 端到端 XLSX 同上**

Run:
```
uv run translator sample.xlsx --translate-engine openai --openai-api-key <your_key>
```

**- [ ] Step 13.5: 最终 Plan 2 Checkpoint**

Plan 2 验收：
- ✅ `translator/office/` 共享组件到位（text_utils、batch_translator）
- ✅ `translator/format/word_pipeline/` 模块化完整（collector、writer）
- ✅ `WordFormatHandler.translate()` 实装，端到端测试通过
- ✅ `XlsxFormatHandler.translate()` 实装，端到端测试通过
- ✅ 通过 `do_translate_async_stream` 调度正常
- ✅ PDF 管线零回归
- ✅ 所有新增 pytest 全绿
- ✅ Ruff 无 error
- ✅ 手工 e2e 成功（如果用户有 LLM key 可跑）

---

## Task 14: 最终统一 Commit（用户执行）

用户执行一次性提交。建议命令：

```
git add -A
git commit -m "feat: rename pdf2zh_next -> translator, add Word/Excel translation pipelines"
```

或拆成两个 commit（git add -p）：
1. `refactor: rename package pdf2zh_next to translator; sink babeldoc into pdf_backend/; FormatHandler.translate() contract`
2. `feat(office): add Word and Excel translation pipelines (stage 1)`

---

## 附录 A — 已知的 Stage-1 限制（由 spec 第 11 节强制）

以下行为是**预期**的，测试**不应断言相反**：
- 段落内部混排样式（bold/italic/color 切换）丢失，统一使用 dominant run 的样式
- 页眉、页脚、脚注、文本框、批注不翻译（测试 fixture 不构造此类内容）
- Word 的 OMML 数学公式整段跳过
- Excel 的图表标题、sheet name、绘图对象文本不翻译
- `.doc` / `.xls` 不被处理（`validate_file` 返回 False，测试已覆盖）
- 进度事件 stage-1 是"粗粒度"（reading → collecting → translating → writing），不是逐条 progress

## 附录 B — 若 Stage 2 要继续

Stage 2 典型增量：
- Word：占位符替换法恢复 run 级样式；页眉/页脚/脚注；OMML 翻译
- Excel：sheet name、chart title、drawing 内文本
- 双语对照输出（dual）
- 逐单元 progress 事件流

这些均在本 plan 外，后续各自独立 spec+plan。
