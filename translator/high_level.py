from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from babeldoc.format.pdf.translation_config import TranslationConfig as BabelDOCConfig
from babeldoc.main import create_progress_handler

from translator.config.model import SettingsModel
from translator.format import DocumentFormat
from translator.format import detect_document_format
from translator.format import get_format_handler
from translator.pdf_backend import BabeldocError
from translator.pdf_backend import IPCError  # noqa: F401  (re-exported)
from translator.pdf_backend import SubprocessCrashError  # noqa: F401
from translator.pdf_backend import SubprocessError
from translator.pdf_backend import TranslationError
from translator.pdf_backend import create_babeldoc_config  # noqa: F401  (re-exported)
from translator.pdf_backend import translate_in_subprocess  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)


async def do_translate_async_stream(
    settings: SettingsModel, file: Path | str
) -> AsyncGenerator[dict, None]:
    settings.validate_settings()
    if isinstance(file, str):
        file = Path(file)

    if settings.basic.input_files and len(settings.basic.input_files):
        logger.warning(
            "settings.basic.input_files is for cli & config, "
            "translator.highlevel.do_translate_async_stream will ignore this field "
            "and only translate the file pointed to by the file parameter."
        )

    if not file.exists():
        raise FileNotFoundError(f"file {file} not found")

    # Determine document format
    if settings.basic.input_format == DocumentFormat.AUTO:
        try:
            detected_format = detect_document_format(file)
            logger.debug(f"Auto-detected format for {file}: {detected_format}")
            format_type = detected_format
        except ValueError as e:
            raise ValueError(f"Could not detect format for {file}: {e}") from e
    else:
        format_type = settings.basic.input_format

    # Dispatch to format handler
    handler = get_format_handler(format_type)
    logger.info(f"Translating via {handler.__class__.__name__}: {file}")

    try:
        async for event in handler.translate(file, settings):
            yield event
            if settings.basic.debug:
                logger.debug(event)
            if event["type"] == "finish":
                break
    except TranslationError as e:
        logger.error(f"Translation error: {e}")
        if isinstance(e, BabeldocError) and e.original_error:
            logger.error(f"Original babeldoc error: {e.original_error}")
        elif isinstance(e, SubprocessError) and e.traceback_str:
            logger.error(f"Subprocess traceback: {e.traceback_str}")
        error_event = {
            "type": "error",
            "error": str(e) if not isinstance(e, SubprocessError) else e.raw_message,
            "error_type": e.__class__.__name__,
            "details": getattr(e, "original_error", "")
            or getattr(e, "traceback_str", "")
            or "",
        }
        yield error_event
        raise


async def do_translate_file_async(
    settings: SettingsModel, ignore_error: bool = False
) -> int:
    rich_pbar_config = BabelDOCConfig(
        translator=None,
        lang_in=None,
        lang_out=None,
        input_file=None,
        font=None,
        pages=None,
        output_dir=None,
        doc_layout_model=1,
        use_rich_pbar=True,
    )
    progress_context, progress_handler = create_progress_handler(rich_pbar_config)
    input_files = settings.basic.input_files
    assert len(input_files) >= 1, "At least one input file is required"
    settings.basic.input_files = set()

    error_count = 0

    for file in input_files:
        logger.info(f"translate file: {file}")
        with progress_context:
            try:
                async for event in do_translate_async_stream(settings, file):
                    progress_handler(event)
                    if settings.basic.debug:
                        logger.debug(event)
                    if event["type"] == "finish":
                        result = event["translate_result"]
                        logger.info("Translation Result:")
                        logger.info(f"  Original PDF: {result.original_pdf_path}")
                        logger.info(f"  Time Cost: {result.total_seconds:.2f}s")
                        logger.info(f"  Mono PDF: {result.mono_pdf_path or 'None'}")
                        logger.info(f"  Dual PDF: {result.dual_pdf_path or 'None'}")

                        token_usage = event.get("token_usage", {})
                        if token_usage:
                            logger.info("Token Usage:")
                            total_usage = {
                                "total": 0,
                                "prompt": 0,
                                "cache_hit_prompt": 0,
                                "completion": 0,
                            }
                            if "main" in token_usage:
                                main_usage = token_usage["main"]
                                logger.info(
                                    f"  Main Translator: Total {main_usage['total']}, "
                                    f"Prompt {main_usage['prompt']}, "
                                    f"Cache Hit Prompt {main_usage['cache_hit_prompt']}, "
                                    f"Completion {main_usage['completion']}"
                                )
                                total_usage["total"] += main_usage["total"]
                                total_usage["prompt"] += main_usage["prompt"]
                                total_usage["cache_hit_prompt"] += main_usage[
                                    "cache_hit_prompt"
                                ]
                                total_usage["completion"] += main_usage["completion"]
                            if "term" in token_usage:
                                term_usage = token_usage["term"]
                                logger.info(
                                    f"  Term Translator: Total {term_usage['total']}, "
                                    f"Prompt {term_usage['prompt']}, "
                                    f"Cache Hit Prompt {term_usage['cache_hit_prompt']}, "
                                    f"Completion {term_usage['completion']}"
                                )
                                total_usage["total"] += term_usage["total"]
                                total_usage["prompt"] += term_usage["prompt"]
                                total_usage["cache_hit_prompt"] += term_usage[
                                    "cache_hit_prompt"
                                ]
                                total_usage["completion"] += term_usage["completion"]
                            logger.info(
                                f"  Total Token Usage: Total {total_usage['total']}, "
                                f"Prompt {total_usage['prompt']}, "
                                f"Cache Hit Prompt {total_usage['cache_hit_prompt']}, "
                                f"Completion {total_usage['completion']}"
                            )
                        break
                    if event["type"] == "error":
                        error_msg = event.get("error", "Unknown error")
                        error_type = event.get("error_type", "UnknownError")
                        details = event.get("details", "")

                        logger.error(f"Error translating file {file}: {error_msg}")
                        logger.error(f"Error type: {error_type}")
                        if details:
                            logger.error(f"Error details: {details}")

                        error_count += 1
                        if not ignore_error:
                            raise RuntimeError(f"Translation error: {error_msg}")
                        break
            except TranslationError as e:
                error_count += 1
                if not ignore_error:
                    raise
            except Exception as e:
                logger.error(f"Error translating file {file}: {e}")
                error_count += 1
                if not ignore_error:
                    raise

    return error_count


def do_translate_file(settings: SettingsModel, ignore_error: bool = False) -> int:
    """Translate files synchronously, returning the number of errors encountered.

    Args:
        settings: Translation settings
        ignore_error: If True, continue translating other files when an error occurs

    Returns:
        Number of errors encountered during translation

    Raises:
        TranslationError: If a translation error occurs and ignore_error is False
        Exception: For other errors if ignore_error is False
    """
    try:
        return asyncio.run(do_translate_file_async(settings, ignore_error))
    except KeyboardInterrupt:
        logger.info("Translation interrupted by user (Ctrl+C)")
        return 1
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            loop = asyncio.get_event_loop()
            try:
                return loop.run_until_complete(
                    do_translate_file_async(settings, ignore_error)
                )
            except KeyboardInterrupt:
                logger.info("Translation interrupted by user (Ctrl+C) in event loop")
                return 1
        else:
            raise
