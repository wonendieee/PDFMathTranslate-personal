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
        return (text, "", "")
    leading = text[: len(text) - len(lstripped)]
    core = lstripped.rstrip()
    trailing = lstripped[len(core):]
    return (leading, core, trailing)
