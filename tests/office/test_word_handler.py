"""Integration test: WordFormatHandler.translate() full pipeline with MockTranslator."""
import asyncio
import shutil
from pathlib import Path
from unittest.mock import patch

from docx import Document
from tests.office.helpers import MockTranslator
from translator.format.word import WordFormatHandler

FIXTURES = Path(__file__).parent / "fixtures"


def _make_settings(output_dir: Path, qps=4, pool=4):
    from translator.config.model import SettingsModel
    from translator.config.translate_engine_model import GoogleSettings

    s = SettingsModel(translate_engine_settings=GoogleSettings())
    s.translation.lang_in = "en"
    s.translation.lang_out = "zh"
    s.translation.qps = qps
    s.translation.pool_max_workers = pool
    s.translation.output = str(output_dir)
    return s


def test_word_handler_full_pipeline(tmp_path):
    src = FIXTURES / "plain.docx"
    work = tmp_path / "plain.docx"
    shutil.copy(src, work)

    settings = _make_settings(tmp_path)
    mock_t = MockTranslator()

    with patch("translator.format.word.get_translator", return_value=mock_t):
        handler = WordFormatHandler()

        async def run():
            events = []
            async for ev in handler.translate(work, settings):
                events.append(ev)
            return events

        events = asyncio.run(run())

    event_types = [e["type"] for e in events]
    assert "progress" in event_types
    assert event_types[-1] == "finish"

    assert len(mock_t.calls) >= 1

    finish = events[-1]
    out_path = Path(finish["translate_result"].translated_path)
    assert out_path.exists()
    assert out_path.name == "plain.zh.docx"

    d2 = Document(out_path)
    all_text = "\n".join(p.text for p in d2.paragraphs)
    assert "[zh]" in all_text


def test_word_handler_doc_format_rejected(tmp_path):
    handler = WordFormatHandler()
    fake_doc = tmp_path / "legacy.doc"
    fake_doc.write_bytes(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1" + b"\x00" * 100)
    assert handler.detect_format(fake_doc) is False
    assert handler.validate_file(fake_doc) is False
