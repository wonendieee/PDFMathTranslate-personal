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
