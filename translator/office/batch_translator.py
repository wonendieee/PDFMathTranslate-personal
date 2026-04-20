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
        self.concurrency = max(1, min(qps, max_workers))

    async def translate_batch(
        self,
        texts: list[str],
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        if not texts:
            return []

        unique = list(dict.fromkeys(texts))
        sem = asyncio.Semaphore(self.concurrency)
        results: dict[str, str] = {}
        completed = [0]
        total = len(texts)

        async def worker(t: str) -> None:
            async with sem:
                translated = await asyncio.to_thread(self.translator.translate, t)
                results[t] = translated
                count_for_this = sum(1 for x in texts if x == t)
                completed[0] += count_for_this
                if progress_cb:
                    progress_cb(completed[0], total)

        await asyncio.gather(*(worker(t) for t in unique))

        return [results[t] for t in texts]
