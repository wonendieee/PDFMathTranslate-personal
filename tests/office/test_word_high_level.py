"""Verify high_level.do_translate_async_stream dispatches to WordFormatHandler."""
import asyncio
import shutil
from pathlib import Path
from unittest.mock import patch

from tests.office.helpers import MockTranslator
from translator.format.base import DocumentFormat
from translator.high_level import do_translate_async_stream

FIXTURES = Path(__file__).parent / "fixtures"


def _make_settings(output_dir: Path):
    from translator.config.model import SettingsModel
    from translator.config.translate_engine_model import GoogleSettings

    s = SettingsModel(translate_engine_settings=GoogleSettings())
    s.translation.lang_in = "en"
    s.translation.lang_out = "zh"
    s.translation.qps = 4
    s.translation.pool_max_workers = 4
    s.translation.output = str(output_dir)
    s.basic.input_format = DocumentFormat.AUTO
    s.basic.input_files = set()
    return s


def test_do_translate_async_stream_dispatches_to_word_handler(tmp_path):
    src = FIXTURES / "plain.docx"
    work = tmp_path / "plain.docx"
    shutil.copy(src, work)

    settings = _make_settings(tmp_path)

    with patch("translator.format.word.get_translator", return_value=MockTranslator()):
        with patch.object(type(settings), "validate_settings", lambda _self: None):

            async def run():
                events = []
                async for ev in do_translate_async_stream(settings, work):
                    events.append(ev)
                return events

            events = asyncio.run(run())

    assert events[-1]["type"] == "finish"
    out = Path(events[-1]["translate_result"].translated_path)
    assert out.exists()
    assert out.name == "plain.zh.docx"
