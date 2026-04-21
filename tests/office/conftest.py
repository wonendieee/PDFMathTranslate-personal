"""Pytest session setup for Office tests.

`.docx` / `.xlsx` fixtures are not checked into git (binary, filtered by
.gitignore). Build them on demand once per test session so CI works
without any pre-generated artifacts.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_REQUIRED = {
    "plain.docx": ("build_docx.py", "build_plain"),
    "with_table.docx": ("build_docx.py", "build_with_table"),
    "mixed_runs.docx": ("build_docx.py", "build_mixed_runs"),
    "with_formula.docx": ("build_docx.py", "build_with_formula"),
    "single_sheet.xlsx": ("build_xlsx.py", "build_single_sheet"),
    "multi_sheet.xlsx": ("build_xlsx.py", "build_multi_sheet"),
    "with_formulas.xlsx": ("build_xlsx.py", "build_with_formulas"),
    "with_merged.xlsx": ("build_xlsx.py", "build_with_merged"),
}


def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_loaded: dict[str, ModuleType] = {}
for name, (script, fn_name) in _REQUIRED.items():
    target = FIXTURES_DIR / name
    if target.exists():
        continue
    mod = _loaded.get(script) or _load_module(FIXTURES_DIR / script)
    _loaded[script] = mod
    getattr(mod, fn_name)()
