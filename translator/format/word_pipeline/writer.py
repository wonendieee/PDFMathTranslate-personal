"""Dominant-run writeback of translated text into python-docx paragraphs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from translator.format.word_pipeline.collector import WordTextUnit

logger = logging.getLogger(__name__)


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
        run_elements = [
            c for c in p_element
            if isinstance(c.tag, str) and c.tag.endswith("}r")
        ]
        if len(run_elements) == 0:
            logger.warning("Paragraph has no runs; skipping writeback")
            continue

        for i, r_elem in enumerate(run_elements):
            t_elements = [
                c for c in r_elem
                if isinstance(c.tag, str) and c.tag.endswith("}t")
            ]
            for t in t_elements:
                t.text = ""

            if i == unit.dominant_run_index:
                if t_elements:
                    t_elements[0].text = translated
                    t_elements[0].set(
                        "{http://www.w3.org/XML/1998/namespace}space", "preserve"
                    )
                else:
                    from lxml import etree

                    ns = r_elem.tag.split("}", 1)[0].lstrip("{")
                    new_t = etree.SubElement(r_elem, f"{{{ns}}}t")
                    new_t.text = translated
                    new_t.set(
                        "{http://www.w3.org/XML/1998/namespace}space", "preserve"
                    )
