"""Subprocess runner for babeldoc PDF translation.

Migrated from translator/high_level.py. Behavior is unchanged; only
location and one public name (_translate_in_subprocess -> translate_in_subprocess)
are adjusted.
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import multiprocessing
import multiprocessing.connection
import multiprocessing.queues
import queue
import threading
import traceback
from logging.handlers import QueueHandler
from pathlib import Path

from babeldoc.format.pdf.high_level import async_translate as babeldoc_translate
from rich.logging import RichHandler

from translator.config.model import SettingsModel
from translator.pdf_backend.babeldoc_config import create_babeldoc_config
from translator.utils import asynchronize

logger = logging.getLogger(__name__)


# --- Error classes ---


class TranslationError(Exception):
    """Base class for all translation-related errors."""

    def __reduce__(self):
        return self.__class__, (str(self),)


class BabeldocError(TranslationError):
    """Error originating from the babeldoc library."""

    def __init__(self, message, original_error=None):
        super().__init__(message)
        self.original_error = original_error

    def __reduce__(self):
        return self.__class__, (str(self), self.original_error)

    def __str__(self):
        if self.original_error:
            return f"{super().__str__()} - Original error: {self.original_error}"
        return super().__str__()


class SubprocessError(TranslationError):
    """Error occurring in the translation subprocess outside of babeldoc."""

    def __init__(self, message, traceback_str=None):
        self.raw_message = message
        super().__init__(message)
        self.traceback_str = traceback_str

    def __reduce__(self):
        return (self.__class__, (self.raw_message, self.traceback_str))

    def __str__(self):
        if self.traceback_str:
            return f"{super().__str__()}\nTraceback: {self.traceback_str}"
        return super().__str__()


class IPCError(TranslationError):
    """Error in inter-process communication."""

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details

    def __reduce__(self):
        return self.__class__, (str(self), self.details)

    def __str__(self):
        if self.details:
            return f"{super().__str__()} - Details: {self.details}"
        return super().__str__()


class SubprocessCrashError(TranslationError):
    """Error occurring when the subprocess crashes unexpectedly."""

    def __init__(self, message, exit_code=None):
        super().__init__(message)
        self.exit_code = exit_code

    def __reduce__(self):
        return self.__class__, (str(self), self.exit_code)

    def __str__(self):
        if self.exit_code is not None:
            return f"{super().__str__()} (exit code: {self.exit_code})"
        return super().__str__()


# --- Subprocess worker ---


def _translate_wrapper(
    settings: SettingsModel,
    file: Path,
    pipe_progress_send: multiprocessing.connection.Connection,
    pipe_cancel_message_recv: multiprocessing.connection.Connection,
    logger_queue: multiprocessing.Queue,
):
    logger = logging.getLogger(__name__)
    cancel_event = threading.Event()
    try:
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("pdfminer").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("peewee").setLevel(logging.WARNING)

        queue_handler = QueueHandler(logger_queue)
        logging.basicConfig(level=logging.INFO, handlers=[queue_handler])

        config = create_babeldoc_config(settings, file)

        def cancel_recv_thread():
            try:
                pipe_cancel_message_recv.recv()
                logger.debug("Cancel signal received in subprocess")
                cancel_event.set()
                config.cancel_translation()
            except Exception as e:
                logger.error(f"Error in cancel_recv_thread: {e}")

        cancel_t = threading.Thread(target=cancel_recv_thread, daemon=True)
        cancel_t.start()

        async def translate_wrapper_async():
            try:
                async for event in babeldoc_translate(config):
                    logger.debug(f"sub process generate event: {event}")
                    if event["type"] == "error":
                        error_msg = str(event.get("error", "Unknown babeldoc error"))
                        error = BabeldocError(
                            message=f"Babeldoc translation error: {error_msg}",
                            original_error=error_msg,
                        )
                        pipe_progress_send.send(error)
                        break
                    if event["type"] == "finish":
                        token_usage = {}

                        if hasattr(config.translator, "token_count"):
                            token_usage["main"] = {
                                "total": config.translator.token_count.value
                                if hasattr(config.translator, "token_count")
                                else 0,
                                "prompt": config.translator.prompt_token_count.value
                                if hasattr(config.translator, "prompt_token_count")
                                else 0,
                                "completion": config.translator.completion_token_count.value
                                if hasattr(config.translator, "completion_token_count")
                                else 0,
                                "cache_hit_prompt": config.translator.cache_hit_prompt_token_count.value
                                if hasattr(
                                    config.translator, "cache_hit_prompt_token_count"
                                )
                                else 0,
                            }

                        if (
                            hasattr(config.term_extraction_translator, "token_count")
                            and config.term_extraction_translator != config.translator
                        ):
                            token_usage["term"] = {
                                "total": config.term_extraction_translator.token_count.value
                                if hasattr(
                                    config.term_extraction_translator, "token_count"
                                )
                                else 0,
                                "prompt": config.term_extraction_translator.prompt_token_count.value
                                if hasattr(
                                    config.term_extraction_translator,
                                    "prompt_token_count",
                                )
                                else 0,
                                "completion": config.term_extraction_translator.completion_token_count.value
                                if hasattr(
                                    config.term_extraction_translator,
                                    "completion_token_count",
                                )
                                else 0,
                                "cache_hit_prompt": config.term_extraction_translator.cache_hit_prompt_token_count.value
                                if hasattr(
                                    config.term_extraction_translator,
                                    "cache_hit_prompt_token_count",
                                )
                                else 0,
                            }
                        elif config.term_extraction_token_usage:
                            token_usage["term"] = {
                                "total": config.term_extraction_token_usage[
                                    "total_tokens"
                                ],
                                "prompt": config.term_extraction_token_usage[
                                    "prompt_tokens"
                                ],
                                "completion": config.term_extraction_token_usage[
                                    "completion_tokens"
                                ],
                                "cache_hit_prompt": config.term_extraction_token_usage[
                                    "cache_hit_prompt_tokens"
                                ],
                            }
                            if sum(token_usage["term"].values()) == 0:
                                token_usage.pop("term")
                        if (
                            "main" in token_usage
                            and "term" in token_usage
                            and config.term_extraction_translator
                            and config.term_extraction_translator == config.translator
                        ):
                            # 如果术语翻译器和主翻译器是同一个实例，避免重复计算
                            term_usage = token_usage["term"]
                            main_usage = token_usage["main"]
                            main_usage["total"] -= term_usage["total"]
                            main_usage["prompt"] -= term_usage["prompt"]
                            main_usage["completion"] -= term_usage["completion"]
                            main_usage["cache_hit_prompt"] -= term_usage[
                                "cache_hit_prompt"
                            ]

                        event["token_usage"] = token_usage
                        pipe_progress_send.send(event)
                        break
                    pipe_progress_send.send(event)
            except Exception as e:
                tb_str = traceback.format_exc()
                if not cancel_event.is_set():
                    logger.error(f"Error in translate_wrapper_async: {e}\n{tb_str}")
                error = SubprocessError(
                    message=f"Error during translation process: {e}",
                    traceback_str=tb_str,
                )
                try:
                    pipe_progress_send.send(error)
                except Exception as pipe_err:
                    if not cancel_event.is_set():
                        logger.error(f"Failed to send error through pipe: {pipe_err}")

        try:
            asyncio.run(translate_wrapper_async())
        except Exception as e:
            tb_str = traceback.format_exc()
            if not cancel_event.is_set():
                logger.error(f"Error running async translation: {e}\n{tb_str}")
            error = SubprocessError(
                message=f"Failed to run translation process: {e}", traceback_str=tb_str
            )
            try:
                pipe_progress_send.send(error)
            except Exception as pipe_err:
                if not cancel_event.is_set():
                    logger.error(f"Failed to send error through pipe: {pipe_err}")
    except Exception as e:
        tb_str = traceback.format_exc()
        logger.error(f"Subprocess initialization error: {e}\n{tb_str}")
        try:
            error = SubprocessError(
                message=f"Translation subprocess initialization error: {e}",
                traceback_str=tb_str,
            )
            pipe_progress_send.send(error)
        except Exception as pipe_err:
            if not cancel_event.is_set():
                logger.error(f"Failed to send error through pipe: {pipe_err}")
    finally:
        logger.debug("sub process send close")
        try:
            pipe_progress_send.send(None)
            pipe_progress_send.close()
            logger.debug("sub process close pipe progress send")
        except Exception as e:
            if not cancel_event.is_set():
                logger.error(f"Error closing progress pipe: {e}")

        try:
            logging.getLogger().removeHandler(queue_handler)
            logging.getLogger().addHandler(RichHandler())
            logger_queue.put(None)
            logger_queue.close()
        except Exception as e:
            if not cancel_event.is_set():
                logger.error(f"Error closing logger queue: {e}")


# --- Async runner ---


async def translate_in_subprocess(
    settings: SettingsModel,
    file: Path,
):
    # 30 minutes timeout
    cb = asynchronize.AsyncCallback(timeout=30 * 60)

    (pipe_progress_recv, pipe_progress_send) = multiprocessing.Pipe(duplex=False)
    (pipe_cancel_message_recv, pipe_cancel_message_send) = multiprocessing.Pipe(
        duplex=False
    )
    logger_queue = multiprocessing.Queue()
    cancel_event = threading.Event()

    def recv_thread():
        while True:
            if cancel_event.is_set():
                break
            try:
                event = pipe_progress_recv.recv()
                if event is None:
                    logger.debug("recv none event")
                    cb.finished_callback_without_args()
                    break

                if isinstance(event, TranslationError):
                    logger.error(f"Received error from subprocess: {event}")
                    cb.error_callback(event)
                    break
                elif isinstance(event, dict):
                    cb.step_callback(event)
                else:
                    logger.warning(
                        f"Unexpected message type from subprocess: {type(event)}"
                    )
                    error = IPCError(f"Unexpected message type: {type(event)}")
                    cb.error_callback(error)
                    break
            except EOFError:
                logger.debug("recv eof error")
                error = IPCError("Connection to subprocess was closed unexpectedly")
                cb.error_callback(error)
                break
            except Exception as e:
                if not cancel_event.is_set():
                    logger.error(f"Error receiving event: {e}")
                error = IPCError(f"IPC error: {e}", details=str(e))
                cb.error_callback(error)
                break

    def log_thread():
        while True:
            try:
                record = logger_queue.get()
                if record is None:
                    logger.info("Listener stopped.")
                    break
                logger.handle(record)
            except KeyboardInterrupt:
                logger.info("Listener stopped.")
                break
            except queue.Empty:
                logger.info("Listener stopped.")
                break
            except Exception:
                logger.error("Failure in listener_process")
                break

    recv_t = threading.Thread(target=recv_thread)
    recv_t.start()
    log_t = threading.Thread(target=log_thread)
    log_t.start()

    translate_process = multiprocessing.Process(
        target=_translate_wrapper,
        args=(
            settings,
            file,
            pipe_progress_send,
            pipe_cancel_message_recv,
            logger_queue,
        ),
    )
    translate_process.start()
    cancel_flag = False
    try:
        async for event in cb:
            if cb.has_error():
                break
            yield event.args[0]
    except asyncio.CancelledError:
        cancel_flag = True
        logger.info("Process Translation cancelled")
        raise
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received in main process")
    finally:
        logger.debug("send cancel message")
        try:
            pipe_cancel_message_send.send(True)
        except (OSError, BrokenPipeError) as e:
            logger.debug(f"Failed to send cancel message: {e}")
        logger.debug("close pipe cancel message")
        try:
            pipe_cancel_message_send.close()
        except Exception as e:
            logger.debug(f"Failed to close pipe_cancel_message_send: {e}")

        try:
            pipe_progress_send.send(None)
        except (OSError, BrokenPipeError) as e:
            logger.debug(f"Failed to send None to pipe_progress_send: {e}")

        logger.debug("set cancel event")
        cancel_event.set()

        try:
            pipe_progress_recv.close()
            logger.debug("closed pipe_progress_recv")
        except Exception as e:
            logger.debug(f"Failed to close pipe_progress_recv: {e}")

        translate_process.join(timeout=2)
        logger.debug("join translate process")
        if translate_process.is_alive():
            logger.info("Translate process did not finish in time, terminate it")
            translate_process.terminate()
            translate_process.join(timeout=1)
        if translate_process.is_alive():
            logger.info("Translate process did not finish in time, killing it")
            try:
                translate_process.kill()
                translate_process.join(timeout=1)
                logger.info("Translate process killed")
            except Exception as e:
                logger.exception(f"Error killing translate process: {e}")

        logger.debug("join recv thread")
        recv_t.join(timeout=2)
        if recv_t.is_alive():
            logger.warning("Recv thread did not finish in time")

        log_t.join(timeout=1)
        if log_t.is_alive():
            logger.warning("Log thread did not finish in time")

        try:
            logger_queue.put(None)
            logger_queue.close()
        except Exception as e:
            logger.debug(f"Failed to close logger_queue: {e}")

        logger.debug("translate process exit code: %s", translate_process.exitcode)
        if not cancel_flag:
            if translate_process.exitcode not in (0, None) and not cb.has_error():
                error = SubprocessCrashError(
                    f"Translation subprocess crashed with exit code "
                    f"{translate_process.exitcode}",
                    exit_code=translate_process.exitcode,
                )
                raise error
            elif cb.has_error():
                raise cb.error
