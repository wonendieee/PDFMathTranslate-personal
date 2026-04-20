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
