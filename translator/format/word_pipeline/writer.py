"""Dominant-run writeback of translated text into python-docx paragraphs."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from translator.format.word_pipeline.collector import WordTextUnit

logger = logging.getLogger(__name__)


def _w_children(elem, local: str):
    """Return direct children of ``elem`` whose tag local-name == ``local``."""
    return [
        c for c in elem
        if isinstance(c.tag, str) and c.tag.endswith("}" + local)
    ]


def _set_dominant_run_text(p_elem, dominant_run_index: int, translated: str) -> None:
    """Clear every <w:t> inside <w:p>, then write ``translated`` into the
    first <w:t> of the dominant run (creating one if missing).
    """
    run_elements = _w_children(p_elem, "r")
    if not run_elements:
        return

    for r_elem in run_elements:
        for t in _w_children(r_elem, "t"):
            t.text = ""

    idx = dominant_run_index
    if idx >= len(run_elements):
        idx = 0
    target = run_elements[idx]

    t_elements = _w_children(target, "t")
    if t_elements:
        t_elements[0].text = translated
        t_elements[0].set(
            "{http://www.w3.org/XML/1998/namespace}space", "preserve"
        )
    else:
        from lxml import etree

        ns = target.tag.split("}", 1)[0].lstrip("{")
        new_t = etree.SubElement(target, f"{{{ns}}}t")
        new_t.text = translated
        new_t.set(
            "{http://www.w3.org/XML/1998/namespace}space", "preserve"
        )


def apply_translations(
    units: list[WordTextUnit],
    translations: list[str],
) -> None:
    """Write translated strings back into the underlying paragraphs.

    Rules:
      - translation goes entirely into the dominant run
      - non-dominant runs have their .text cleared to '' (run object + formatting retained)
    """
    if len(units) != len(translations):
        raise ValueError(
            f"units/translations length mismatch: {len(units)} vs {len(translations)}"
        )

    for unit, translated in zip(units, translations, strict=True):
        p_element = unit.paragraph_element
        if not _w_children(p_element, "r"):
            logger.warning("Paragraph has no runs; skipping writeback")
            continue
        _set_dominant_run_text(p_element, unit.dominant_run_index, translated)


def apply_bilingual(
    units: list[WordTextUnit],
    translations: list[str],
) -> None:
    """Insert a translated clone of each paragraph *after* the original.

    The result is a bilingual document: original paragraph first, then an
    immediate sibling with identical formatting but its text replaced by
    the translation. ``units`` must be fresh (collected from an untouched
    doc), otherwise translations would land into already-translated paragraphs.

    - Original run count + pPr/rPr are preserved via deep copy.
    - Translation is written into the dominant run of the cloned paragraph;
      all other runs of the clone have their <w:t> cleared.
    - Works for body paragraphs and paragraphs inside table cells alike,
      because addnext() inserts into the same parent element.
    """
    if len(units) != len(translations):
        raise ValueError(
            f"units/translations length mismatch: {len(units)} vs {len(translations)}"
        )

    for unit, translated in zip(units, translations, strict=True):
        p_element = unit.paragraph_element
        if not _w_children(p_element, "r"):
            logger.warning("Paragraph has no runs; skipping bilingual clone")
            continue

        clone = deepcopy(p_element)
        _set_dominant_run_text(clone, unit.dominant_run_index, translated)
        p_element.addnext(clone)
