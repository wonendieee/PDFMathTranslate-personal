"""PDF backend - babeldoc integration for PDF translation.

Not intended for Office (docx/xlsx) consumers.
"""

from translator.pdf_backend.babeldoc_config import create_babeldoc_config
from translator.pdf_backend.subprocess_runner import BabeldocError
from translator.pdf_backend.subprocess_runner import IPCError
from translator.pdf_backend.subprocess_runner import SubprocessCrashError
from translator.pdf_backend.subprocess_runner import SubprocessError
from translator.pdf_backend.subprocess_runner import TranslationError
from translator.pdf_backend.subprocess_runner import translate_in_subprocess

__all__ = [
    "TranslationError",
    "BabeldocError",
    "SubprocessError",
    "IPCError",
    "SubprocessCrashError",
    "create_babeldoc_config",
    "translate_in_subprocess",
]
