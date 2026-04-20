"""PDF format handler implementation."""

import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from babeldoc.format.pdf.high_level import async_translate as babeldoc_translate
from babeldoc.format.pdf.translation_config import TranslationConfig as BabelDOCConfig

from .base import DocumentFormat, FormatHandler

logger = logging.getLogger(__name__)


class PDFFormatHandler(FormatHandler):
    """PDF document format handler."""

    def get_format(self) -> DocumentFormat:
        return DocumentFormat.PDF

    def detect_format(self, file_path: Path) -> bool:
        """Detect if a file is a PDF."""
        if not file_path.exists():
            return False

        # Check by extension
        if file_path.suffix.lower() == ".pdf":
            return True

        # TODO: Add magic byte detection for more robust detection
        try:
            with open(file_path, "rb") as f:
                header = f.read(5)
                return header.startswith(b"%PDF-")
        except Exception:
            return False

    def validate_file(self, file_path: Path) -> bool:
        """Validate that a file is a valid PDF."""
        if not file_path.exists():
            return False

        if not self.detect_format(file_path):
            return False

        # Basic validation - check if file can be opened as PDF
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            doc.close()
            return True
        except Exception as e:
            logger.debug(f"PDF validation failed for {file_path}: {e}")
            return False

    async def convert_to_pdf(
        self, file_path: Path, output_path: Optional[Path] = None
    ) -> Path:
        """PDF files don't need conversion, return the original path."""
        if not self.validate_file(file_path):
            raise ValueError(f"Invalid PDF file: {file_path}")

        return file_path

    def get_babeldoc_processor(self, config: Any) -> Any:
        """Get babeldoc PDF processor."""
        if not isinstance(config, BabelDOCConfig):
            raise TypeError(f"Expected BabelDOCConfig, got {type(config)}")

        # Return the async_translate function for PDF processing
        return babeldoc_translate

    def cleanup(self, temp_files: list[Path]) -> None:
        """Clean up temporary files."""
        for temp_file in temp_files:
            try:
                if temp_file.exists() and temp_file.is_file():
                    temp_file.unlink()
                    logger.debug(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")