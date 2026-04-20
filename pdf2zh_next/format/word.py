"""Word document format handler."""

import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from .base import DocumentFormat, FormatHandler

logger = logging.getLogger(__name__)

# Optional dependencies for Word support
try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    docx = None

try:
    import pypandoc
    HAS_PYPANDOC = True
except ImportError:
    HAS_PYPANDOC = False
    pypandoc = None


class WordFormatHandler(FormatHandler):
    """Word document format handler (.docx, .doc)."""

    def __init__(self):
        """Initialize Word format handler with optional dependencies."""
        if not HAS_DOCX:
            raise ImportError(
                "Word document support requires 'python-docx' package. "
                "Install with: pip install python-docx"
            )
        if not HAS_PYPANDOC:
            raise ImportError(
                "Word-to-PDF conversion requires 'pypandoc' package. "
                "Install with: pip install pypandoc"
            )

    def get_format(self) -> DocumentFormat:
        return DocumentFormat.DOCX

    def detect_format(self, file_path: Path) -> bool:
        """Detect if a file is a Word document."""
        if not file_path.exists():
            return False

        suffix = file_path.suffix.lower()
        if suffix in [".docx", ".doc"]:
            return True

        # TODO: Add magic byte detection for .doc and .docx files
        try:
            with open(file_path, "rb") as f:
                header = f.read(8)
                # .docx is a ZIP archive, .doc has specific signatures
                if header.startswith(b"PK\x03\x04"):  # ZIP archive
                    # Check if it contains word/ directory
                    return self._is_docx_file(file_path)
                elif header.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):  # Compound File Binary
                    return self._is_doc_file(file_path)
        except Exception:
            pass

        return False

    def _is_docx_file(self, file_path: Path) -> bool:
        """Check if a ZIP file is a .docx document."""
        try:
            import zipfile
            with zipfile.ZipFile(file_path, 'r') as zipf:
                # .docx files contain specific directories
                return any(name.startswith('word/') for name in zipf.namelist())
        except Exception:
            return False

    def _is_doc_file(self, file_path: Path) -> bool:
        """Check if a file is a .doc document."""
        # Basic check - .doc validation would require more complex logic
        return file_path.suffix.lower() == ".doc"

    def validate_file(self, file_path: Path) -> bool:
        """Validate that a file is a valid Word document."""
        if not file_path.exists():
            return False

        if not self.detect_format(file_path):
            return False

        suffix = file_path.suffix.lower()

        if suffix == ".docx" and HAS_DOCX:
            try:
                # Try to open with python-docx
                doc = docx.Document(file_path)
                # Check if we can access basic properties
                _ = doc.paragraphs
                return True
            except Exception as e:
                logger.debug(f".docx validation failed for {file_path}: {e}")
                return False
        elif suffix == ".doc":
            # .doc files are harder to validate without additional libraries
            # For now, accept based on extension and magic bytes
            try:
                with open(file_path, "rb") as f:
                    header = f.read(8)
                    return header.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1")
            except Exception:
                return False

        return False

    async def convert_to_pdf(self, file_path: Path, output_path: Optional[Path] = None) -> Path:
        """Convert a Word document to PDF.

        Args:
            file_path: Path to the Word document
            output_path: Optional output path for PDF. If None, creates a temporary file.

        Returns:
            Path to the converted PDF file

        Raises:
            ValueError: If conversion fails
            ImportError: If required dependencies are missing
        """
        import asyncio

        if not self.validate_file(file_path):
            raise ValueError(f"Invalid Word document: {file_path}")

        if output_path is None:
            # Create temporary PDF file with unique name
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                output_path = Path(tmp.name)

        # Determine input format for pandoc
        suffix = file_path.suffix.lower()
        if suffix == ".docx":
            input_format = "docx"
        elif suffix == ".doc":
            input_format = "doc"
        else:
            input_format = None  # Let pandoc auto-detect

        extra_args = [
            "--pdf-engine=xelatex",
            "--variable", "mainfont='SimSun'",
            "--variable", "monofont='Courier New'",
        ]

        try:
            # Run conversion in thread pool since pypandoc is blocking
            def _convert():
                if input_format:
                    pypandoc.convert_file(
                        str(file_path),
                        "pdf",
                        format=input_format,
                        outputfile=str(output_path),
                        extra_args=extra_args
                    )
                else:
                    pypandoc.convert_file(
                        str(file_path),
                        "pdf",
                        outputfile=str(output_path),
                        extra_args=extra_args
                    )
                return output_path

            output_path = await asyncio.to_thread(_convert)
            logger.info(f"Converted Word document to PDF: {file_path} -> {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Failed to convert Word document to PDF: {e}")
            # Clean up output file if it was created
            if output_path and output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            raise ValueError(f"Word to PDF conversion failed: {e}")

    def get_babeldoc_processor(self, config: Any) -> Any:
        """Word documents are converted to PDF first, then use PDF processor.

        Args:
            config: Configuration for the processor

        Returns:
            A babeldoc processor instance (PDF processor after conversion)
        """
        # Word documents need to be converted to PDF first
        # This method returns None since conversion happens before babeldoc processing
        return None

    def cleanup(self, temp_files: list[Path]) -> None:
        """Clean up temporary files."""
        for temp_file in temp_files:
            try:
                if temp_file.exists() and temp_file.is_file():
                    temp_file.unlink()
                    logger.debug(f"Cleaned up temporary Word conversion file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")