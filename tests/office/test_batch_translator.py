"""Tests for translator.office.batch_translator.OfficeBatchTranslator."""
import asyncio
import time

import pytest
from tests.office.helpers import MockTranslator
from translator.office.batch_translator import OfficeBatchTranslator


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
    bt = OfficeBatchTranslator(mock_translator, qps=4, max_workers=4)
    inputs = ["same", "diff", "same", "same"]
    result = asyncio.run(bt.translate_batch(inputs))
    assert result == ["[zh]same", "[zh]diff", "[zh]same", "[zh]same"]
    assert sorted(mock_translator.calls) == sorted(["same", "diff"])


def test_concurrency_faster_than_sequential():
    mt = MockTranslator(delay_ms=100)
    bt = OfficeBatchTranslator(mt, qps=4, max_workers=4)
    inputs = [f"t{i}" for i in range(8)]

    start = time.perf_counter()
    result = asyncio.run(bt.translate_batch(inputs))
    elapsed = time.perf_counter() - start

    assert len(result) == 8
    assert elapsed < 0.6, f"Expected concurrency, took {elapsed:.2f}s"


def test_progress_callback(mock_translator):
    progress_log: list[tuple[int, int]] = []

    bt = OfficeBatchTranslator(mock_translator, qps=4, max_workers=4)
    inputs = [f"t{i}" for i in range(5)]
    asyncio.run(
        bt.translate_batch(
            inputs, progress_cb=lambda c, t: progress_log.append((c, t))
        )
    )

    assert progress_log[-1] == (5, 5)
    assert len(progress_log) == 5


def test_translator_exception_propagates():
    class BoomTranslator:
        name = "boom"

        def translate(self, text, **kwargs):
            raise RuntimeError("kaboom")

    bt = OfficeBatchTranslator(BoomTranslator(), qps=4, max_workers=4)
    with pytest.raises(RuntimeError, match="kaboom"):
        asyncio.run(bt.translate_batch(["x", "y"]))
