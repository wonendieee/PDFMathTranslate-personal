"""Build babeldoc TranslationConfig from translator SettingsModel.

Migrated from translator/high_level.py (_get_glossaries, create_babeldoc_config).
Behavior unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path

from babeldoc.format.pdf.translation_config import TranslationConfig as BabelDOCConfig
from babeldoc.format.pdf.translation_config import (
    WatermarkOutputMode as BabelDOCWatermarkMode,
)
from babeldoc.glossary import Glossary

from translator.config.model import SettingsModel
from translator.engines import get_term_translator
from translator.engines import get_translator

logger = logging.getLogger(__name__)


def _get_glossaries(settings: SettingsModel) -> list[Glossary] | None:
    glossaries = []
    if not settings.translation.glossaries:
        return None
    for file in settings.translation.glossaries.split(","):
        glossaries.append(
            Glossary.from_csv(Path(file), target_lang_out=settings.translation.lang_out)
        )
    return glossaries


def create_babeldoc_config(settings: SettingsModel, file: Path) -> BabelDOCConfig:
    if not isinstance(settings, SettingsModel):
        raise ValueError(f"{type(settings)} is not SettingsModel")
    translator = get_translator(settings)
    if translator is None:
        raise ValueError("No translator found")

    if (
        settings.term_extraction_engine_settings == settings.translate_engine_settings
        and settings.translation.term_qps == settings.translation.qps
    ):
        term_extraction_translator = translator
        if recommended_qps := getattr(translator, "pdf2zh_next_recommended_qps", None):
            settings.translation.term_qps = recommended_qps
            logger.info(f"Updated term qps to {recommended_qps}")
        if recommended_pool_max_workers := getattr(
            translator, "pdf2zh_next_recommended_pool_max_workers", None
        ):
            settings.translation.term_pool_max_workers = recommended_pool_max_workers
            logger.info(
                f"Updated term pool max workers to {recommended_pool_max_workers}"
            )
    else:
        term_extraction_translator = get_term_translator(settings)

    split_strategy = None
    if settings.pdf.max_pages_per_part:
        split_strategy = BabelDOCConfig.create_max_pages_per_part_split_strategy(
            settings.pdf.max_pages_per_part
        )

    watermark_output_mode_maps = {
        "no_watermark": BabelDOCWatermarkMode.NoWatermark,
        "both": BabelDOCWatermarkMode.Both,
        "watermarked": BabelDOCWatermarkMode.Watermarked,
    }

    watermark_output_mode = settings.pdf.watermark_output_mode

    watermark_mode = watermark_output_mode_maps.get(
        watermark_output_mode, BabelDOCWatermarkMode.Watermarked
    )

    table_model = None
    if settings.pdf.translate_table_text:
        from babeldoc.docvision.table_detection.rapidocr import RapidOCRModel

        table_model = RapidOCRModel()

    babeldoc_config = BabelDOCConfig(
        input_file=file,
        font=None,
        pages=settings.pdf.pages,
        output_dir=settings.translation.output,
        doc_layout_model=None,
        translator=translator,
        debug=settings.basic.debug,
        lang_in=settings.translation.lang_in,
        lang_out=settings.translation.lang_out,
        no_dual=settings.pdf.no_dual,
        no_mono=settings.pdf.no_mono,
        qps=settings.translation.qps,
        formular_font_pattern=settings.pdf.formular_font_pattern,
        formular_char_pattern=settings.pdf.formular_char_pattern,
        split_short_lines=settings.pdf.split_short_lines,
        short_line_split_factor=settings.pdf.short_line_split_factor,
        disable_rich_text_translate=settings.pdf.disable_rich_text_translate,
        dual_translate_first=settings.pdf.dual_translate_first,
        enhance_compatibility=settings.pdf.enhance_compatibility,
        use_alternating_pages_dual=settings.pdf.use_alternating_pages_dual,
        watermark_output_mode=watermark_mode,
        min_text_length=settings.translation.min_text_length,
        report_interval=settings.report_interval,
        skip_clean=settings.pdf.skip_clean,
        split_strategy=split_strategy,
        table_model=table_model,
        skip_scanned_detection=settings.pdf.skip_scanned_detection,
        ocr_workaround=settings.pdf.ocr_workaround,
        custom_system_prompt=settings.translation.custom_system_prompt,
        glossaries=_get_glossaries(settings),
        auto_enable_ocr_workaround=settings.pdf.auto_enable_ocr_workaround,
        pool_max_workers=settings.translation.pool_max_workers,
        auto_extract_glossary=not settings.translation.no_auto_extract_glossary,
        primary_font_family=settings.translation.primary_font_family,
        only_include_translated_page=settings.pdf.only_include_translated_page,
        merge_alternating_line_numbers=not settings.pdf.no_merge_alternating_line_numbers,
        remove_non_formula_lines=not settings.pdf.no_remove_non_formula_lines,
        non_formula_line_iou_threshold=settings.pdf.non_formula_line_iou_threshold,
        figure_table_protection_threshold=settings.pdf.figure_table_protection_threshold,
        skip_formula_offset_calculation=settings.pdf.skip_formula_offset_calculation,
        term_extraction_translator=term_extraction_translator,
        term_pool_max_workers=settings.translation.term_pool_max_workers,
    )
    return babeldoc_config
