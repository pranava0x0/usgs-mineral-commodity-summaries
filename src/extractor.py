"""Text extraction with footnote-superscript awareness.

PyMuPDF distinguishes superscripts in two ways: by `span['flags'] & 1` and by
a smaller font size (typically 6.5pt vs 10pt body). We use the flag because
it's the documented signal; size is the fallback if the bit is unset.

Each line of text is returned with its superscript markers stripped from the
content but recorded separately. That lets us recognize `Total¹` as "Total"
with footnote "1", and `7492` (Laos refinery production with footnote 7) as
the value 492 with footnote "7".
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Iterator

import fitz  # PyMuPDF

log = logging.getLogger(__name__)

BODY_SIZE_PT = 10.0
# Empirical thresholds from MCS 2026 sheets:
#   main body:        10.02pt
#   inline footnote:   6.50pt (flag bit 0 also set)
#   footnote-section body: 7.98pt (flag bit 0 NOT set — has to be excluded by size)
#   footnote-section marker digit: 4.98pt (flag bit 0 NOT set on this PDF)
# Anything <= 7pt is treated as a footnote marker.
SUPERSCRIPT_SIZE_MAX_PT = 7.0
SUPERSCRIPT_FLAG = 1           # bit 0 of span['flags']


@dataclasses.dataclass(frozen=True)
class TextLine:
    """One visual line of text, with body text and any leading/trailing footnotes split out."""

    page: int                   # 1-indexed page number, matches what a human sees
    bbox: tuple[float, float, float, float]
    text: str                   # body text only (superscripts removed), whitespace-collapsed
    footnotes_in_line: list[str]  # footnote markers found anywhere on the line, in reading order
    leading_footnote: str | None  # superscript at the very start, before any body text (footnote-definition line)
    trailing_footnote: str | None  # the most-recent superscript at end of body text, if any
    raw_text: str               # original line text with superscripts inline (for debugging)


def _is_superscript(span: dict) -> bool:
    if span.get("flags", 0) & SUPERSCRIPT_FLAG:
        return True
    # fallback: some PDFs (e.g. the MCS footnote section) encode the
    # superscript marker only via font size, with flag bit cleared.
    return span.get("size", BODY_SIZE_PT) <= SUPERSCRIPT_SIZE_MAX_PT


def iter_lines(pdf_path: Path) -> Iterator[TextLine]:
    """Yield every visual line in the PDF with superscripts identified."""
    doc = fitz.open(pdf_path)
    try:
        for page_idx, page in enumerate(doc):
            data = page.get_text("dict")
            for block in data["blocks"]:
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    yield _line_from_spans(page_idx + 1, line)
    finally:
        doc.close()


def _line_from_spans(page_no: int, line: dict) -> TextLine:
    body_parts: list[str] = []
    footnotes: list[str] = []
    trailing: str | None = None
    leading: str | None = None
    body_started = False
    raw_parts: list[str] = []

    for span in line["spans"]:
        text = span["text"]
        raw_parts.append(text)
        has_content = bool(text.strip())
        if _is_superscript(span):
            stripped = text.strip()
            if stripped:
                footnotes.append(stripped)
                trailing = stripped
                if not body_started and leading is None:
                    leading = stripped
        else:
            body_parts.append(text)
            if has_content:
                body_started = True
                trailing = None  # body text broke the trailing-footnote chain

    body = "".join(body_parts).strip()
    # collapse internal whitespace so "Korea, Republic of  " == "Korea, Republic of"
    body = " ".join(body.split())
    return TextLine(
        page=page_no,
        bbox=tuple(line["bbox"]),
        text=body,
        footnotes_in_line=footnotes,
        leading_footnote=leading,
        trailing_footnote=trailing,
        raw_text="".join(raw_parts),
    )


def all_lines(pdf_path: Path) -> list[TextLine]:
    """Convenience: materialize all lines into a list."""
    return list(iter_lines(pdf_path))


@dataclasses.dataclass(frozen=True)
class Word:
    """A single whitespace-delimited token with its own bbox.

    Used by the world-production parser, where PyMuPDF's line-level extraction
    sometimes merges two adjacent column values (separated only by visual
    whitespace) into a single span. Words give reliable per-cell coordinates.
    """

    page: int
    bbox: tuple[float, float, float, float]
    text: str


def iter_words(pdf_path: Path) -> "list[Word]":
    """Return whitespace-delimited words with footnote superscripts stripped.

    We can't use the convenient page.get_text("words") shortcut because it
    ignores font size, so "⁷492" comes back as the single word "7492" with
    no way to tell that the "7" was a superscript footnote marker. Instead
    we walk rawdict's per-character stream, emit a word whenever we see a
    space or a font-size change, and drop any leading characters whose font
    size puts them in the footnote band.
    """
    doc = fitz.open(pdf_path)
    out: list[Word] = []
    try:
        for page_idx, page in enumerate(doc):
            for word in _words_from_page(page, page_idx + 1):
                out.append(word)
    finally:
        doc.close()
    return out


def _words_from_page(page, page_no: int) -> "list[Word]":
    """Reconstruct words from char-level info, stripping superscripts."""
    data = page.get_text("rawdict")
    words: list[Word] = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                is_super = (span.get("flags", 0) & SUPERSCRIPT_FLAG) or (
                    span.get("size", BODY_SIZE_PT) <= SUPERSCRIPT_SIZE_MAX_PT
                )
                # Skip an entire superscript span — these are footnote markers
                # like "⁷" in front of "492" or " ⁶" after a country name.
                if is_super:
                    continue
                # Within this body-sized span, split on whitespace chars to
                # produce one Word per token. Each token's bbox is the union of
                # its character bboxes.
                token_chars: list[dict] = []
                for ch in span.get("chars", []):
                    if ch["c"].isspace():
                        if token_chars:
                            words.append(_word_from_chars(token_chars, page_no))
                            token_chars = []
                    else:
                        token_chars.append(ch)
                if token_chars:
                    words.append(_word_from_chars(token_chars, page_no))
    return words


def _word_from_chars(chars: list[dict], page_no: int) -> Word:
    text = "".join(ch["c"] for ch in chars)
    bbox = (
        min(ch["bbox"][0] for ch in chars),
        min(ch["bbox"][1] for ch in chars),
        max(ch["bbox"][2] for ch in chars),
        max(ch["bbox"][3] for ch in chars),
    )
    return Word(page=page_no, bbox=bbox, text=text)
