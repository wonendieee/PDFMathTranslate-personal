"""Tests for FormatHandler abstract base class."""
import pytest
from translator.format.base import DocumentFormat
from translator.format.base import FormatHandler


def test_format_handler_is_abstract():
    """FormatHandler cannot be instantiated directly."""
    with pytest.raises(TypeError):
        FormatHandler()


def test_format_handler_translate_is_async_generator_method():
    """Concrete subclass must implement translate() as async generator."""
    from pathlib import Path

    class DummyHandler(FormatHandler):
        def get_format(self):
            return DocumentFormat.PDF

        def detect_format(self, p):
            return True

        def validate_file(self, p):
            return True

        async def translate(self, input_file, settings):
            yield {"type": "finish", "translate_result": None}

    h = DummyHandler()
    gen = h.translate(Path("x"), None)
    assert hasattr(gen, "__aiter__")


def test_old_convert_to_pdf_removed():
    """FormatHandler should no longer define convert_to_pdf."""
    assert not hasattr(FormatHandler, "convert_to_pdf")
    assert not hasattr(FormatHandler, "get_babeldoc_processor")
    assert not hasattr(FormatHandler, "cleanup")


def test_document_format_has_xlsx():
    """DocumentFormat enum must include XLSX and XLS (for Plan 2)."""
    assert DocumentFormat.XLSX.value == "xlsx"
    assert DocumentFormat.XLS.value == "xls"
