"""Base classes for document format handling."""

import enum
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DocumentFormat(enum.Enum):
    """Supported document formats."""
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    AUTO = "auto"  # Auto-detect format


class FormatHandler(ABC):
    """Abstract base class for document format handlers."""

    @abstractmethod
    def get_format(self) -> DocumentFormat:
        """Get the document format this handler supports."""
        pass

    @abstractmethod
    def detect_format(self, file_path: Path) -> bool:
        """Detect if a file is of this format.

        Args:
            file_path: Path to the file to check

        Returns:
            True if the file matches this format
        """
        pass

    @abstractmethod
    def validate_file(self, file_path: Path) -> bool:
        """Validate that a file is a valid document of this format.

        Args:
            file_path: Path to the file to validate

        Returns:
            True if the file is valid
        """
        pass

    @abstractmethod
    async def convert_to_pdf(self, file_path: Path, output_path: Optional[Path] = None) -> Path:
        """Convert a document to PDF format.

        Args:
            file_path: Path to the source document
            output_path: Optional output path for PDF. If None, creates a temporary file.

        Returns:
            Path to the converted PDF file

        Raises:
            ValueError: If conversion fails
            ImportError: If required dependencies are missing
        """
        pass

    @abstractmethod
    def get_babeldoc_processor(self, config: Any) -> Any:
        """Get a babeldoc-compatible processor for this format.

        Args:
            config: Configuration for the processor

        Returns:
            A babeldoc processor instance
        """
        pass

    @abstractmethod
    def cleanup(self, temp_files: list[Path]) -> None:
        """Clean up temporary files created during processing.

        Args:
            temp_files: List of temporary file paths to clean up
        """
        pass