"""Document format abstraction layer for PDFMathTranslate."""

import importlib
import logging
from pathlib import Path
from typing import Dict, Optional, Type

from .base import DocumentFormat, FormatHandler

logger = logging.getLogger(__name__)

# Registry of format handlers
_FORMAT_HANDLERS: Dict[DocumentFormat, Type[FormatHandler]] = {}


def register_format_handler(format_type: DocumentFormat, handler_class: Type[FormatHandler]) -> None:
    """Register a format handler for a document format.

    Args:
        format_type: The document format
        handler_class: The handler class
    """
    _FORMAT_HANDLERS[format_type] = handler_class
    logger.debug(f"Registered format handler for {format_type}: {handler_class.__name__}")


def get_format_handler(format_type: DocumentFormat) -> FormatHandler:
    """Get a format handler instance for the specified format.

    Args:
        format_type: The document format

    Returns:
        A format handler instance

    Raises:
        ValueError: If no handler is registered for the format
        ImportError: If required dependencies are missing
    """
    if format_type not in _FORMAT_HANDLERS:
        raise ValueError(f"No format handler registered for {format_type}")

    handler_class = _FORMAT_HANDLERS[format_type]
    return handler_class()


def detect_document_format(file_path: Path) -> DocumentFormat:
    """Detect the format of a document file.

    Args:
        file_path: Path to the document file

    Returns:
        The detected document format

    Raises:
        ValueError: If format cannot be detected
    """
    if not file_path.exists():
        raise ValueError(f"File does not exist: {file_path}")

    # First check by file extension
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return DocumentFormat.PDF
    elif suffix == ".docx":
        return DocumentFormat.DOCX
    elif suffix == ".doc":
        return DocumentFormat.DOC

    # If no handler recognizes it, try to detect by content
    for format_type, handler_class in _FORMAT_HANDLERS.items():
        try:
            handler = handler_class()
            if handler.detect_format(file_path):
                return format_type
        except Exception as e:
            logger.debug(f"Handler {handler_class.__name__} failed to detect format: {e}")
            continue

    raise ValueError(f"Could not detect document format for: {file_path}")


def validate_file_format(file_path: Path, format_type: DocumentFormat) -> bool:
    """Validate that a file matches the specified format.

    Args:
        file_path: Path to the file
        format_type: Expected format

    Returns:
        True if the file is valid for the format

    Raises:
        ValueError: If no handler is registered for the format
    """
    handler = get_format_handler(format_type)
    return handler.validate_file(file_path)


# Auto-register available format handlers
def _register_available_handlers() -> None:
    """Register all available format handlers."""
    try:
        from .pdf import PDFFormatHandler
        register_format_handler(DocumentFormat.PDF, PDFFormatHandler)
    except ImportError as e:
        logger.warning(f"Failed to import PDF format handler: {e}")

    try:
        from .word import WordFormatHandler
        register_format_handler(DocumentFormat.DOCX, WordFormatHandler)
        register_format_handler(DocumentFormat.DOC, WordFormatHandler)
    except ImportError as e:
        logger.debug(f"Word format handler not available: {e}")


# Initialize on module import
_register_available_handlers()


__all__ = [
    "DocumentFormat",
    "FormatHandler",
    "register_format_handler",
    "get_format_handler",
    "detect_document_format",
    "validate_file_format",
]