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
