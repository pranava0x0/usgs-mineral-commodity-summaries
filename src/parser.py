"""Parse the line stream from `extractor.iter_lines` into an `ElementRecord`.

The MCS sheet layout is consistent across commodities (Klochko-prepared sheets
in 2026 share boilerplate), so a generic state-machine parser handles bismuth
and is expected to handle most other elements with minor per-section tweaks.

State machine sections (in PDF order):
  HEADER           — title + units note
  DOMESTIC_USE     — "Domestic Production and Use:" prose
  SALIENT_STATS    — the 5-year US table
  RECYCLING        — "Recycling:" prose
  IMPORT_SOURCES   — "Import Sources (YYYY-YY):" inline list (sometimes multi-category)
  TARIFF           — "Tariff:" + HTS table (skipped — not in requested columns)
  EVENTS           — "Events, Trends, and Issues:" prose
  WORLD_PROD       — "World ... Production and Capacity:" / Mine Production table
  WORLD_RESOURCES  — prose
  SUBSTITUTES      — prose
  FOOTNOTES        — small-print numbered glossary

Sentinel tokens we preserve verbatim alongside the coerced floats:
  "—"   zero            (USGS convention; em-dash)
  "NA"  not available
  "W"   withheld to protect proprietary data
  "E"   net exporter (only in NIR cells)
  ">N"  greater than N  (we coerce to N for math, keep raw string for display)
  "<N"  less than N     (same)
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from typing import Optional

from . import config, extractor, fetcher
from .models import (
    CountryShare,
    ElementRecord,
    ImportSourceCategory,
    PriceQuote,
    WorldProductionRow,
    YEAR_COLUMNS,
    YearSeries,
)

log = logging.getLogger(__name__)

# --- section headers: a line is "in section X" when it starts with one of these
# *prefix* strings. World-production sheets use a wide variety of names, so
# in addition to the explicit prefixes we accept anything matching a regex
# (see `_detect_section`).
SECTION_STARTS: dict[str, str] = {
    "Domestic Production and Use:": "DOMESTIC_USE",
    "Salient Statistics—United States:": "SALIENT_STATS",
    "Recycling:": "RECYCLING",
    "Import Sources": "IMPORT_SOURCES",     # "Import Sources (2021–24):"
    "Tariff:": "TARIFF",
    "Depletion Allowance:": "DEPLETION",
    "Government Stockpile:": "STOCKPILE",
    "Events, Trends, and Issues:": "EVENTS",
    "World Resources:": "WORLD_RESOURCES",
    "Substitutes:": "SUBSTITUTES",
}

# Any "World ... :" line that mentions production / reserves / capacity is the
# world-production table. We skip "World Resources:" because that's prose.
_WORLD_PROD_PATTERN = re.compile(
    r"^World [^:]*?(?:Production|Reserves|Capacity)[^:]*:",
    re.IGNORECASE,
)

NUMERIC = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
GT_LT = re.compile(r"^([<>])\s*([\d,]+(?:\.\d+)?)$")
# Some MCS price rows quote a range with an en-dash, e.g. "890–1,000" or "820–880".
# We coerce to the midpoint for numeric purposes and keep the raw range string.
RANGE = re.compile(r"^([\d,]+(?:\.\d+)?)\s*[–-]\s*([\d,]+(?:\.\d+)?)$")

DASH_VARIANTS = {"—"}  # em-dash (U+2014) = USGS zero. Hyphens and en-dashes are NOT zero.
WITHHELD = {"W"}                  # withheld to protect proprietary data
NET_EXPORTER = {"E"}              # only appears in NIR cells


def _to_float(token: str) -> tuple[Optional[float], str]:
    """Coerce a single MCS table token to (numeric_value, raw_clean_text).

    `numeric_value` is None for non-numeric sentinels; the raw form is always
    returned so downstream code can render ">95" or "W" verbatim.
    """
    s = token.strip()
    if not s:
        return None, ""
    if s.upper() == "NA":
        return None, "NA"
    if s in DASH_VARIANTS:
        return 0.0, "—"
    if s in WITHHELD:
        return None, "W"
    if s in NET_EXPORTER:
        return None, "E"
    m = GT_LT.match(s)
    if m:
        # ">95" / "<5" — keep approximation in float, preserve operator in raw
        op, num = m.group(1), m.group(2)
        try:
            return float(num.replace(",", "")), f"{op}{num}"
        except ValueError:
            return None, s
    m = RANGE.match(s)
    if m:
        # "890–1,000" — midpoint as a numeric approximation, raw kept verbatim.
        try:
            lo = float(m.group(1).replace(",", ""))
            hi = float(m.group(2).replace(",", ""))
            return (lo + hi) / 2, s
        except ValueError:
            return None, s
    if NUMERIC.match(s):
        try:
            return float(s.replace(",", "")), s.replace(",", "")
        except ValueError:
            pass
    # Trailing "e" estimation marker (rare — usually it's a column header)
    if s.endswith("e") and NUMERIC.match(s[:-1]):
        return float(s[:-1].replace(",", "")), s[:-1]
    log.warning("could not coerce token to float: %r", token)
    return None, s


def _looks_like_value(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    if s.upper() == "NA":
        return True
    if s in DASH_VARIANTS:
        return True
    if s in WITHHELD or s in NET_EXPORTER:
        return True
    if GT_LT.match(s):
        return True
    if RANGE.match(s):
        return True
    return bool(NUMERIC.match(s))


def _detect_section(text: str) -> Optional[str]:
    for prefix, name in SECTION_STARTS.items():
        if text.startswith(prefix):
            return name
    # World production / refinery / mine / capacity table — many variant titles.
    # We need to anchor before "World Resources:" which is prose.
    if text.startswith("World ") and not text.startswith("World Resources"):
        if _WORLD_PROD_PATTERN.match(text):
            return "WORLD_PROD"
    return None


FOOTNOTES_LEFT_MARGIN_MAX = 70.0  # footnote-section bodies sit at x≈45pt on the left edge


def _take_section(lines: list[extractor.TextLine], start_idx: int) -> tuple[list[extractor.TextLine], int]:
    """Return (lines belonging to this section, index of the next section header).

    Stops at the first line that begins another known section, OR at the
    first *left-margin* footnote-definition line — that marks the start of
    the small-print glossary at the bottom of page 2. We check the left
    margin to avoid catching superscript-prefixed value cells in the world
    production table (e.g. Laos's `⁷492` value cell sits mid-page, not in
    the footnote column).
    """
    out: list[extractor.TextLine] = []
    i = start_idx + 1
    while i < len(lines):
        line = lines[i]
        if _detect_section(line.text):
            break
        if line.leading_footnote is not None and line.bbox[0] < FOOTNOTES_LEFT_MARGIN_MAX:
            break
        out.append(line)
        i += 1
    return out, i


# ---------------------------------------------------------------------------
# Header / prose
# ---------------------------------------------------------------------------


def _parse_header(lines: list[extractor.TextLine]) -> tuple[str, str]:
    """Find the title (e.g. 'BISMUTH', 'RARE EARTHS') and the bracketed units note.

    The title is the first all-caps line near the top of page 1 — it may be
    multi-word ("RARE EARTHS") and may carry a trailing footnote superscript
    (e.g. 'RARE EARTHS¹'). The units note follows on the next non-empty line,
    wrapped in parentheses or brackets.
    """
    title = ""
    units_note = ""
    for i, line in enumerate(lines):
        if line.page != 1:
            continue
        t = line.text
        if not t:
            continue
        # Skip the prepared-by attribution and other long lines
        if t.startswith("Prepared by"):
            continue
        # The title is all-uppercase letters (allowing spaces, digits, and footnote markers stripped)
        stripped = t.rstrip()
        compact = stripped.replace(" ", "").replace(",", "")
        if compact.isupper() and any(c.isalpha() for c in compact) and len(compact) >= 4:
            title = stripped
            # Next non-empty line should be the units note in parens or brackets
            for j in range(i + 1, min(i + 6, len(lines))):
                t2 = lines[j].text
                if not t2:
                    continue
                if (t2.startswith("(") and t2.endswith(")")) or (t2.startswith("[") and t2.endswith("]")):
                    units_note = t2
                    return title, units_note
                if t2.startswith("(") and "specified" in t2:
                    units_note = t2
                    return title, units_note
                break
            return title, units_note
    return title, units_note


def _join_prose(
    section_header_line: Optional[extractor.TextLine],
    section_lines: list[extractor.TextLine],
    header_prefix: str,
) -> str:
    """Concatenate prose, including any text the header line carries after the colon.

    The MCS sheet often opens a section like
        "Domestic Production and Use: The United States ceased production ..."
    where the first sentence sits *on* the header line. `_take_section` starts
    one line later, so we must splice the header's own tail (everything past
    the section label) back in.
    """
    head_tail = ""
    if section_header_line is not None and header_prefix in section_header_line.text:
        idx = section_header_line.text.find(header_prefix)
        head_tail = section_header_line.text[idx + len(header_prefix):].strip()
    body = " ".join(line.text for line in section_lines if line.text)
    full = (head_tail + " " + body).strip() if head_tail else body.strip()
    return full


# ---------------------------------------------------------------------------
# Salient Statistics
# ---------------------------------------------------------------------------

# Section labels that introduce a *block* (not a data row) in the Salient
# Statistics table. Treating them as headers lets us tag every following row
# with its parent section, which disambiguates labels like "Ore and concentrates"
# that appear under both Imports and Exports for antimony.
SECTION_HEADER_KEYWORDS = (
    "production",
    "imports for consumption",
    "imports",
    "exports",
    "consumption",
    "price",
    "net import reliance",
    "stocks",
    "shipments from government stockpile",
    "employment",
)


def _is_section_header_label(label: str) -> bool:
    """Detect 'Production:', 'Imports for consumption:', 'Net import reliance ... :' etc."""
    s = label.strip().rstrip(":").lower()
    return any(s.startswith(kw) or s == kw for kw in SECTION_HEADER_KEYWORDS)


import dataclasses


def _expand_packed_value_lines(section_lines: list[extractor.TextLine]) -> list[extractor.TextLine]:
    """Split lines whose text contains multiple whitespace-separated value tokens.

    PyMuPDF occasionally merges multiple table cells into one span when the
    visual whitespace between them is small. We detect "all tokens look like
    values" and split into one TextLine per token, interpolating bboxes so
    later x-position checks still work approximately.
    """
    out: list[extractor.TextLine] = []
    for line in section_lines:
        parts = line.text.split()
        if len(parts) <= 1 or not all(_looks_like_value(p) for p in parts):
            out.append(line)
            continue
        x0, y0, x1, y1 = line.bbox
        width = max(x1 - x0, 1.0)
        step = width / len(parts)
        for k, p in enumerate(parts):
            bbox = (x0 + k * step, y0, x0 + (k + 1) * step, y1)
            out.append(dataclasses.replace(line, text=p, bbox=bbox))
    return out


def _parse_salient_stats(section_lines: list[extractor.TextLine]) -> tuple[list[YearSeries], list[PriceQuote]]:
    """Return (data rows, price quotes).

    Walks the linearized cell stream. Each "row" is one label line followed by
    exactly 5 value cells (one per year). Any label line that doesn't have 5
    valid-looking cells immediately after it is treated as a section header
    that scopes the rows beneath it.

    Price rows are forked into `price_quotes` so the viewer can show the
    full per-form price table without polluting the main salient stats list.
    """
    # PyMuPDF sometimes packs multiple value cells into a single text span when
    # the gaps between them are small (seen on scandium's price rows). Split
    # any such packed line into one cell per token so the row-extraction
    # heuristic can find its 5 values.
    section_lines = _expand_packed_value_lines(section_lines)

    # Skip the year header tokens at the top of the section.
    i = 0
    seen_years = 0
    while i < len(section_lines) and seen_years < len(YEAR_COLUMNS):
        if section_lines[i].text.replace("e", "") in {y.rstrip("e") for y in YEAR_COLUMNS}:
            seen_years += 1
        i += 1

    rows: list[YearSeries] = []
    prices: list[PriceQuote] = []

    current_section: Optional[str] = None
    current_subsection: Optional[str] = None
    in_price_section = False

    while i < len(section_lines):
        label_line = section_lines[i]
        i += 1
        if not label_line.text:
            continue

        # Multi-line label support: when the label wraps across two visual
        # lines (e.g. "Net import reliance ... as a percentage of apparent /
        # consumption") the values sit on the second physical line. Look
        # ahead: if the next line is itself a label (no values follow it
        # immediately) we merge them up to a small budget. If after the
        # budget we still don't see data, REWIND i to its original position
        # so we don't burn through lines that belong to a different row.
        start_i = i
        label_text = label_line.text.rstrip(":").strip()
        label_fn = (
            label_line.trailing_footnote
            if label_line.trailing_footnote and label_line.trailing_footnote.isdigit()
            else None
        )

        peek = section_lines[i : i + len(YEAR_COLUMNS)]
        looks_like_data = (
            len(peek) == len(YEAR_COLUMNS)
            and all(_looks_like_value(p.text) for p in peek)
        )

        # A label is *definitely* a section header (not a wrapped-label start)
        # if its original line text ended in a colon. We use that as the
        # discriminator between rare-earths' NIR group header (ends ":") and
        # scandium's wrapped NIR label (continues onto the next line).
        ends_in_colon = label_line.text.rstrip().endswith(":")

        if not looks_like_data and not ends_in_colon:
            # Try ONE label-continuation merge. Multi-line labels in MCS
            # essentially never wrap to 3+ lines, so we cap at one extension.
            if i < len(section_lines):
                cand_line = section_lines[i]
                cand = cand_line.text.strip()
                if cand and not _looks_like_value(cand):
                    new_label = f"{label_text} {cand.rstrip(':')}".strip()
                    new_peek = section_lines[i + 1 : i + 1 + len(YEAR_COLUMNS)]
                    new_looks_like_data = (
                        len(new_peek) == len(YEAR_COLUMNS)
                        and all(_looks_like_value(p.text) for p in new_peek)
                    )
                    if new_looks_like_data:
                        label_text = new_label
                        if not label_fn and cand_line.trailing_footnote and cand_line.trailing_footnote.isdigit():
                            label_fn = cand_line.trailing_footnote
                        i += 1
                        looks_like_data = True
                        peek = new_peek
                    # else: don't commit the merge — keep start_i, label_text unchanged.

        if not looks_like_data:
            # Section / subsection header. Decide which level by keyword.
            if _is_section_header_label(label_text):
                current_section = label_text
                current_subsection = None
                in_price_section = label_text.lower().startswith("price")
            else:
                # A label that isn't a known top-level section becomes a subsection
                # (e.g. "Smelter:" under "Production:").
                current_subsection = label_text
            continue

        # A *data* row may itself open a new section: rows like
        # "Consumption, apparent³", "Price, metal, average, dollars per pound³",
        # or "Net import reliance⁴ as a percentage of apparent consumption" sit
        # on a single line with their own values, but conceptually each is its
        # own section. Detect and switch context before recording the row.
        if _is_section_header_label(label_text):
            current_section = label_text
            current_subsection = None
            in_price_section = label_text.lower().startswith("price")

        # It's a real data row.
        values: dict[str, Optional[float]] = {}
        raws: dict[str, Optional[str]] = {}
        for col, p in zip(YEAR_COLUMNS, peek):
            v, raw = _to_float(p.text)
            values[col] = v
            raws[col] = raw or None

        if in_price_section and not _looks_like_value(label_text):
            # Price sub-row: capture in price_quotes (and also as a salient row for completeness)
            prices.append(PriceQuote(
                form=label_text,
                unit_note=current_section,
                values=values,
                raw_values=raws,
            ))

        rows.append(YearSeries(
            label=label_text,
            footnote=label_fn,
            section=current_section,
            subsection=current_subsection,
            values=values,
            raw_values=raws,
        ))
        i += len(YEAR_COLUMNS)

    return rows, prices


# ---------------------------------------------------------------------------
# Import Sources — supports multi-category sheets (antimony, tungsten, etc.)
# ---------------------------------------------------------------------------

# Each category is a phrase ending in ":", containing 1-6 words, after which
# the country / share pairs follow. Categories are delimited by sentence-ending
# periods — semicolons separate countries *within* a category, not categories.
# We additionally require the label to not contain "%" (which would mean we
# accidentally matched a tail like "9%; and other, 5%. Oxide").
_CATEGORY_HEAD = re.compile(
    r"(?:^|(?<=\.\s))"           # start of body, or after ". "
    r"([A-Z][^:%]{1,80}):\s*"    # category label up to ":" without "%" inside
)


def _parse_import_sources(
    header_line: extractor.TextLine,
    section_lines: list[extractor.TextLine],
) -> tuple[list[CountryShare], list[ImportSourceCategory], Optional[str]]:
    """Parse the Import Sources block.

    Returns (flat list, by-category list, date_range).
    - `flat list` is populated when there is exactly one category (bismuth style).
    - `by-category list` always lists every category, even the single case.

    Multi-category example (antimony):
        Ore and concentrates: Mexico, 86%; Italy, 9%; and other, 5%.
        Oxide: China, 66%; Belgium, 16%; ...
    """
    parts = [header_line.text] + [l.text for l in section_lines]
    full = " ".join(p for p in parts if p)

    m = re.match(r"Import Sources\s*\(([0-9\-–]+)\):\s*(.*)", full)
    date_range: Optional[str] = None
    body = full
    if m:
        date_range = m.group(1).replace("–", "-")
        body = m.group(2)
    body = body.strip()

    # Detect category labels by scanning for "<Phrase>:" segments.
    matches = list(_CATEGORY_HEAD.finditer(body))

    categories: list[ImportSourceCategory] = []
    if matches:
        # Each match defines a category starting at the match end.
        for k, mch in enumerate(matches):
            cat = mch.group(1).strip()
            seg_start = mch.end()
            seg_end = matches[k + 1].start() if k + 1 < len(matches) else len(body)
            segment = body[seg_start:seg_end].rstrip(". ")
            countries = _parse_country_share_list(segment)
            if countries:
                categories.append(ImportSourceCategory(category=cat, countries=countries))

    if not categories:
        # Single uncategorized list — bismuth pattern.
        countries = _parse_country_share_list(body.rstrip(". "))
        if countries:
            categories.append(ImportSourceCategory(category=None, countries=countries))

    flat = categories[0].countries if len(categories) == 1 and categories[0].category is None else []
    return flat, categories, date_range


def _parse_country_share_list(segment: str) -> list[CountryShare]:
    """Parse 'Mexico, 86%; Italy, 9%; and other, 5%' -> list of CountryShare.

    The last chunk frequently has trailing prose after the period (e.g. the
    rare-earths sheet runs "...other, 6%. Compounds and metals imported from
    Estonia, Japan, and Malaysia were derived from..."), so we anchor on
    "country, NN%" without requiring end-of-chunk to follow.
    """
    shares: list[CountryShare] = []
    for chunk in segment.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        chunk = re.sub(r"^and\s+", "", chunk)
        m2 = re.match(r"(.+?),\s*(\d+(?:\.\d+)?)\s*%", chunk)
        if not m2:
            continue
        country = m2.group(1).strip().rstrip(",")
        # Strip a trailing footnote-digit attached to a country, e.g. "China,8" -> "China"
        country = re.sub(r"\s*,\s*\d+$", "", country).strip()
        # Some sheets terminate the segment with a period inside the country word
        country = country.rstrip(".")
        shares.append(CountryShare(country=country, share_pct=float(m2.group(2))))
    return shares


# ---------------------------------------------------------------------------
# World Production / Reserves
# ---------------------------------------------------------------------------


def _parse_world_production(
    header_line: extractor.TextLine,
    section_lines: list[extractor.TextLine],
    words: list[extractor.Word],
    all_lines: list[extractor.TextLine],
) -> tuple[str, list[WorldProductionRow], Optional[str], Optional[str]]:
    """Parse the World Production table using per-word bboxes.

    PyMuPDF's line-level extraction sometimes merges two column values that
    are visually separated only by whitespace (e.g. antimony's Vietnam row
    where the prev-year "220" and latest-year "220" land in one span). The
    word-level extractor gives each numeric a separate bbox, which we then
    cluster by y-coordinate into table rows.

    Falls back to line-level grouping if for some reason no words land in the
    section's y-range (e.g. an unusually shaped sheet).
    """
    section_label = header_line.text.split(":")[0]

    # Confine ourselves to the world-prod section's y-range on each page.
    pages = sorted({l.page for l in section_lines if l.text.strip()} | {header_line.page})
    y_min = header_line.bbox[3]  # below the header line
    y_max = max((l.bbox[3] for l in section_lines if l.text.strip()), default=y_min + 600.0)

    in_range = [w for w in words if w.page in pages and y_min <= w.bbox[1] <= y_max + 2]
    if not in_range:
        return section_label, [], None, None

    rows_by_y: list[tuple[float, list[extractor.Word]]] = []
    for w in in_range:
        y = w.bbox[1]
        placed = False
        for band in rows_by_y:
            if abs(band[0] - y) < 2.5 and band[1] and band[1][0].page == w.page:
                band[1].append(w)
                placed = True
                break
        if not placed:
            rows_by_y.append((y, [w]))

    for _, band in rows_by_y:
        band.sort(key=lambda b: b.bbox[0])
    rows_by_y.sort(key=lambda kv: (kv[1][0].page, kv[0]))

    # Cluster adjacent words in the same band into "cells" — a cell is a group
    # of words whose bboxes touch or nearly touch (gap ≤ 4pt). This keeps
    # "United States" together while separating it from the next column.
    def _cluster_to_cells(band: list[extractor.Word]) -> list[tuple[str, tuple[float, float, float, float]]]:
        cells: list[tuple[str, tuple[float, float, float, float]]] = []
        cur_words: list[extractor.Word] = []
        for w in band:
            if not cur_words:
                cur_words.append(w)
                continue
            last = cur_words[-1]
            gap = w.bbox[0] - last.bbox[2]
            if gap <= 4.0:
                cur_words.append(w)
            else:
                cells.append(_cell_from_words(cur_words))
                cur_words = [w]
        if cur_words:
            cells.append(_cell_from_words(cur_words))
        return cells

    # Convert each band of words into cells, then classify rows
    column_titles: list[str] = []
    sub_metals: list[str] = []
    data_bands: list[list[tuple[str, tuple[float, float, float, float]]]] = []
    saw_year_header = False
    year_header_tokens: list[str] = []  # verbatim year tokens captured from the year-sub-header band

    def _is_header_token(t: str) -> bool:
        s = t.strip().lower()
        # PGM uses "PGM reserves"; Indium uses "Refinery capacity" — accept
        # any " reserves" / " capacity" suffix so the column gets classified.
        return (
            s.endswith("production")
            or s.startswith("production capacity")
            or s == "capacity"
            or s.endswith(" capacity")
            or s in {"reserves", "reserve base"}
            or s.endswith(" reserves")
        )

    # USGS year tokens are "2024" or "2025" plain — sometimes "2025e" or "2025ᵉ"
    # when the estimated marker is rendered inline (rare in the world-prod band).
    _YEAR_RE = re.compile(r"^20\d\d[eᵉ]?$")

    def _looks_like_submetal_row(texts: list[str]) -> bool:
        """A sub-metal header row sits between the column-titles row and the
        year-sub-header row when USGS splits a column by commodity sub-type
        (PGM splits Mine Production into Palladium + Platinum). Identified by:
        ≥2 cells, every cell is a short alphabetical label (no digits, no
        section keywords, no country commas)."""
        if len(texts) < 2:
            return False
        for t in texts:
            s = t.strip()
            if not s or len(s) > 24:
                return False
            if NUMERIC.match(s) or _YEAR_RE.match(s):
                return False
            if not all(c.isalpha() or c.isspace() or c == "-" for c in s):
                return False
            if _is_header_token(s):
                return False
        return True

    for _, band in rows_by_y:
        cells = _cluster_to_cells(band)
        texts = [c[0] for c in cells]
        if not cells:
            continue
        # Multi-cell column-header row: e.g. ["Mine production", "Reserves"]
        if all(_is_header_token(t) for t in texts):
            for t in texts:
                column_titles.append(t)
            continue
        # Single-cell header
        if len(cells) == 1 and _is_header_token(texts[0]):
            column_titles.append(texts[0])
            continue
        # Sub-metal header row (PGM-style) — must come after we've seen a
        # production column-title, before the year row, and have ≥2
        # alphabetical-only cells.
        if (
            column_titles
            and not saw_year_header
            and any(c.lower().endswith("production") for c in column_titles)
            and _looks_like_submetal_row(texts)
        ):
            for t in texts:
                sub_metals.append(t.strip())
            continue
        # Year sub-header row — capture the verbatim tokens so downstream
        # consumers (CSV exporter, viewer) can use the PDF's actual column
        # labels in column names instead of "prev"/"latest".
        # A band counts as the year-sub-header if it contains at least two
        # year tokens; some sheets place reserves-unit annotations on the
        # same y as the year tokens (chromium: "Ore / Cr O / content";
        # molybdenum: "(thousand metric tons)"), so we don't require the
        # *whole* band to be year tokens — just that two or more years are
        # present and that no cell looks like a data row (a country name).
        year_matches = [t.strip() for t in texts if _YEAR_RE.match(t.strip())]
        if len(year_matches) >= 2:
            saw_year_header = True
            for t in year_matches:
                year_header_tokens.append(t)
            continue
        if not saw_year_header and not column_titles:
            continue
        data_bands.append(cells)

    kinds = _infer_column_kinds(column_titles, sub_metals)

    rows: list[WorldProductionRow] = []
    for cells in data_bands:
        country = cells[0][0].strip().rstrip(":")
        if not country:
            continue
        # Pull row-level footnote markers from the line-level data at this y.
        row_y = cells[0][1][1]
        row_page = pages[0] if len(pages) == 1 else _page_for_y(pages, row_y, section_lines)
        note = _row_footnotes_at(all_lines, row_page, row_y)

        value_cells = cells[1:]
        prev = latest = capacity = reserves = None
        prev_raw = latest_raw = reserves_raw = None
        sub_metal_latest: dict[str, Optional[float]] = {}
        for idx, (text, _bbox) in enumerate(value_cells):
            kind = kinds[idx] if idx < len(kinds) else None
            val, raw = _to_float(text)
            if kind == "prev":
                prev, prev_raw = val, raw
            elif kind == "latest":
                latest, latest_raw = val, raw
            elif kind == "capacity":
                capacity = val
            elif kind == "reserves":
                reserves, reserves_raw = val, raw
            elif kind and kind.startswith("submetal:"):
                # `submetal:<name>:prev` / `submetal:<name>:latest`
                _, name, slot = kind.split(":", 2)
                if slot == "latest":
                    sub_metal_latest[name] = val
                    # Mirror the first sub-metal into the legacy prev/latest
                    # fields so consumers that don't know about sub-metals
                    # still see *some* production value for the country.
                    if latest is None:
                        latest, latest_raw = val, raw
                elif slot == "prev":
                    if prev is None:
                        prev, prev_raw = val, raw

        rows.append(WorldProductionRow(
            country=country,
            production_prev_year=prev,
            production_latest_year=latest,
            capacity=capacity,
            reserves=reserves,
            production_prev_raw=prev_raw or None,
            production_latest_raw=latest_raw or None,
            reserves_raw=reserves_raw or None,
            note=note,
            sub_metal_production_latest=sub_metal_latest,
        ))

        if country.lower().startswith("world total"):
            break

    # Pull the two year labels in left-to-right order if both were captured.
    # Most MCS 2026 sheets carry exactly two (prev / latest); a sheet with only
    # one or none falls back to None.
    year_prev: Optional[str] = year_header_tokens[0] if len(year_header_tokens) >= 1 else None
    year_latest: Optional[str] = year_header_tokens[1] if len(year_header_tokens) >= 2 else None
    return section_label, rows, year_prev, year_latest


def _row_footnotes_at(lines: list[extractor.TextLine], page: int, y: float) -> Optional[str]:
    """Find any footnote markers attached to any line within ~2pt of y on the given page."""
    fns: list[str] = []
    for ln in lines:
        if ln.page != page:
            continue
        if abs(ln.bbox[1] - y) > 2.5:
            continue
        for f in ln.footnotes_in_line:
            if f.isdigit() and f not in fns:
                fns.append(f)
    return ("footnote " + ",".join(fns)) if fns else None


def _page_for_y(pages: list[int], y: float, section_lines: list[extractor.TextLine]) -> int:
    """Pick the most likely page number for a given y given the section's lines."""
    best = pages[0]
    best_d = float("inf")
    for ln in section_lines:
        if ln.page in pages:
            d = abs(ln.bbox[1] - y)
            if d < best_d:
                best_d = d
                best = ln.page
    return best


def _cell_from_words(words: list[extractor.Word]) -> tuple[str, tuple[float, float, float, float]]:
    """Merge a list of contiguous words into a single (text, bbox) cell.

    Words that begin with a footnote-digit prefix attached to a number (e.g.
    "⁷492" extracted as a single word "7492") need stripping; we drop a leading
    1-2 digit footnote when it isn't separated by punctuation and the value
    *with* it has more digits than typical for a real number in the table.
    """
    bbox = (
        min(w.bbox[0] for w in words),
        min(w.bbox[1] for w in words),
        max(w.bbox[2] for w in words),
        max(w.bbox[3] for w in words),
    )
    text = " ".join(w.text for w in words)
    return text, bbox


def _infer_column_kinds(column_titles: list[str], sub_metals: list[str] | None = None) -> list[str]:
    """Map header strings to per-cell column kinds in data rows.

    When `sub_metals` is non-empty (PGM's "Palladium" / "Platinum"), the
    production column expands into one (prev, latest) pair per sub-metal,
    encoded as `submetal:<name>:prev` / `submetal:<name>:latest`. The
    data-row mapper unpacks those into `sub_metal_production_latest` on
    the WorldProductionRow.
    """
    titles_lower = [t.lower() for t in column_titles]
    kinds: list[str] = []
    saw_production = False
    for t in titles_lower:
        if t.endswith("production"):
            if sub_metals:
                # One (prev, latest) pair per sub-metal — preserves PDF order.
                for m in sub_metals:
                    kinds.append(f"submetal:{m}:prev")
                    kinds.append(f"submetal:{m}:latest")
            else:
                kinds += ["prev", "latest"]
            saw_production = True
        elif t.startswith("production capacity") or t == "capacity" or t.endswith(" capacity"):
            kinds.append("capacity")
        elif t in {"reserves", "reserve base"} or t.endswith(" reserves"):
            kinds.append("reserves")
    if not saw_production:
        kinds = ["prev", "latest"] + kinds
    return kinds


# ---------------------------------------------------------------------------
# Government Stockpile — small table with FY 2025 / FY 2026 columns
# ---------------------------------------------------------------------------


def _parse_government_stockpile(
    header_line: Optional[extractor.TextLine],
    section_lines: list[extractor.TextLine],
) -> Optional[float]:
    """Sum FY 2025 Potential Acquisitions across all material rows.

    Layout (typical):
        FY 2025                    FY 2026
        Material   Potential       Potential       Potential       Potential
                   acquisitions    disposals       acquisitions    disposals
        <row 1>    <value>         <value>         <value>         <value>
        <row 2>    ...

    Some sheets break the column headers across multiple physical lines
    ("Potential" / "acquisitions" on two separate text spans). We walk the
    line stream, find any line that follows the header band and starts with
    a non-numeric material label, then take its first numeric cell as the
    FY 2025 Potential Acquisitions value. Em-dash "—" counts as 0 (USGS
    convention); "NA" / "W" / "E" / non-numeric tokens count as missing.

    Returns the sum across material rows, or None if the section says
    "Not available" or has no parseable rows.
    """
    if header_line and "not available" in header_line.text.lower():
        return None

    # Stockpile tables always sit on the same page as their header. The
    # generic section extractor walks past page boundaries until it finds
    # the next section header; for sheets whose stockpile is at the bottom
    # of page 1, that means we accidentally pick up page 2's page-header
    # ("COBALT") and citation line ("...February 2026") — the "2026" tokens
    # parse as numbers and pollute the sum. Confine to the header's page.
    header_page = header_line.page if header_line else None
    if header_page is not None:
        section_lines = [l for l in section_lines if l.page == header_page]

    # Skip header tokens. The header band ends after we've seen any of
    # "Potential", "acquisitions", "disposals", or "Material" — once a
    # following line starts with a value-looking word, we're into data.
    HEADER_TOKENS = {"fy", "fy 2025", "fy 2026", "material", "potential",
                     "acquisitions", "disposals"}

    def _is_header_band(t: str) -> bool:
        s = t.strip().lower()
        return s in HEADER_TOKENS or s.startswith("fy ")

    total: Optional[float] = None
    seen_header = False
    i = 0
    while i < len(section_lines):
        line = section_lines[i]
        t = line.text.strip()
        if not t:
            i += 1
            continue
        if _is_header_band(t):
            seen_header = True
            i += 1
            continue
        if not seen_header:
            # Prose lines that come BEFORE the header band (rare-earths-style
            # narrative) — skip without considering as data.
            i += 1
            continue
        # Data row: <label> <value> <value> <value> <value>. Some PDFs
        # split the row across lines (label alone, then values on the next).
        # We accept either: a single line with label + 4 values, or
        # label-only followed by a values-only line.
        parts = t.split()
        # Find the first value-looking token in the line. Anything before
        # it is the material label; anything from it onward is the values row.
        first_val_idx = next(
            (k for k, p in enumerate(parts) if _looks_like_value(p)),
            None,
        )
        if first_val_idx is None or first_val_idx == 0:
            # label-only line — peek ahead for a values line
            if i + 1 < len(section_lines):
                next_t = section_lines[i + 1].text.strip()
                next_parts = next_t.split()
                if next_parts and all(_looks_like_value(p) for p in next_parts):
                    first_val = next_parts[0]
                    v, _ = _to_float(first_val)
                    if v is not None:
                        total = (total or 0.0) + v
                    i += 2
                    continue
            i += 1
            continue
        # Single line with label + values
        first_val = parts[first_val_idx]
        v, _ = _to_float(first_val)
        if v is not None:
            total = (total or 0.0) + v
        i += 1

    return total


# ---------------------------------------------------------------------------
# Footnotes
# ---------------------------------------------------------------------------


def _parse_footnotes(lines: list[extractor.TextLine]) -> dict[str, str]:
    """Pull numbered footnotes from the small-print tail of page 2."""
    out: dict[str, str] = {}
    in_block = False
    current_key: Optional[str] = None
    buf: list[str] = []
    for line in lines:
        if line.page < 2:
            continue
        if line.leading_footnote is not None and line.bbox[0] < FOOTNOTES_LEFT_MARGIN_MAX:
            if current_key is not None:
                out[current_key] = " ".join(buf).strip()
            current_key = line.leading_footnote
            buf = [line.text]
            in_block = True
        elif in_block:
            buf.append(line.text)
    if current_key is not None:
        out[current_key] = " ".join(buf).strip()
    return out


# ---------------------------------------------------------------------------
# Latest-year aggregations
# ---------------------------------------------------------------------------


def _latest_value_by_section(salient: list[YearSeries], section_keyword: str, year: str) -> tuple[Optional[float], dict[str, str]]:
    """Sum the latest-year values of all rows whose `section` starts with `section_keyword`.

    Used for "Imports for consumption" / "Exports" totals when the sheet doesn't
    have an explicit "Total" row. Returns (sum, latest_year_sentinels) where
    sentinels record any "W" / "E" / ">N" tokens we encountered while summing,
    so the viewer can flag the total as approximate.
    """
    total = 0.0
    found_any = False
    sentinels: dict[str, str] = {}
    for row in salient:
        if not row.section:
            continue
        if not row.section.lower().startswith(section_keyword):
            continue
        v = row.values.get(year)
        raw = row.raw_values.get(year) if row.raw_values else None
        if v is not None:
            total += v
            found_any = True
        if raw in {"W", "E"} or (raw and raw.startswith((">", "<"))):
            sentinels.setdefault(row.label, raw)
    return (total if found_any else None), sentinels


def _explicit_total(salient: list[YearSeries], section_keyword: str, year: str) -> Optional[float]:
    """An explicit 'Total' row tagged with the given section."""
    for row in salient:
        if row.label.strip().lower() != "total":
            continue
        if row.section and row.section.lower().startswith(section_keyword):
            return row.values.get(year)
    return None


def _find_row(salient: list[YearSeries], section_keyword: Optional[str], label_substr: str) -> Optional[YearSeries]:
    """Find the first row whose label contains `label_substr` (optionally under a section)."""
    label_substr = label_substr.lower()
    for row in salient:
        if section_keyword and (not row.section or not row.section.lower().startswith(section_keyword.lower())):
            continue
        if label_substr in row.label.lower():
            return row
    return None


def _latest_or_none(row: Optional[YearSeries], year: str) -> Optional[float]:
    return row.values.get(year) if row else None


# ---------------------------------------------------------------------------
# Top-level: parse a whole PDF into an ElementRecord
# ---------------------------------------------------------------------------


def parse_element_pdf(slug: str) -> ElementRecord:
    """Run the full pipeline for one registered element.

    Failures raise — fail loud, never silent (CLAUDE.md §Error resilience).
    Individual element failures are caught by `pipeline.py` so that one bad
    sheet doesn't break the batch.
    """
    el = config.all_known()[slug]
    pdf_path = fetcher.fetch_pdf(el.mcs_url)
    lines = extractor.all_lines(pdf_path)
    words = extractor.iter_words(pdf_path)

    title, units_note = _parse_header(lines)
    log.info("[%s] title=%r units=%r", slug, title, units_note)

    sections: dict[str, list[extractor.TextLine]] = {}
    section_header_lines: dict[str, extractor.TextLine] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        section = _detect_section(line.text)
        if section is not None:
            section_lines, j = _take_section(lines, i)
            sections.setdefault(section, []).extend(section_lines)
            section_header_lines.setdefault(section, line)
            i = j
        else:
            i += 1

    salient, price_quotes = _parse_salient_stats(sections.get("SALIENT_STATS", []))

    flat_shares: list[CountryShare] = []
    by_category: list[ImportSourceCategory] = []
    import_range: Optional[str] = None
    if "IMPORT_SOURCES" in sections:
        flat_shares, by_category, import_range = _parse_import_sources(
            section_header_lines["IMPORT_SOURCES"], sections["IMPORT_SOURCES"]
        )

    world_label = None
    world_rows: list[WorldProductionRow] = []
    world_year_prev: Optional[str] = None
    world_year_latest: Optional[str] = None
    if "WORLD_PROD" in sections:
        world_label, world_rows, world_year_prev, world_year_latest = _parse_world_production(
            section_header_lines["WORLD_PROD"], sections["WORLD_PROD"], words, lines,
        )

    stockpile_fy2025: Optional[float] = None
    if "STOCKPILE" in sections:
        stockpile_fy2025 = _parse_government_stockpile(
            section_header_lines.get("STOCKPILE"), sections["STOCKPILE"],
        )

    footnotes = _parse_footnotes(lines)

    latest_year = YEAR_COLUMNS[-1]

    import fitz  # cheap re-open just for page_count
    pdf_doc = fitz.open(pdf_path)
    try:
        page_count = pdf_doc.page_count
    finally:
        pdf_doc.close()

    # Prose blocks
    domestic = _join_prose(section_header_lines.get("DOMESTIC_USE"), sections.get("DOMESTIC_USE", []), "Domestic Production and Use:")
    events = _join_prose(section_header_lines.get("EVENTS"), sections.get("EVENTS", []), "Events, Trends, and Issues:")
    resources = _join_prose(section_header_lines.get("WORLD_RESOURCES"), sections.get("WORLD_RESOURCES", []), "World Resources:")
    substitutes = _join_prose(section_header_lines.get("SUBSTITUTES"), sections.get("SUBSTITUTES", []), "Substitutes:")
    recycling = _join_prose(section_header_lines.get("RECYCLING"), sections.get("RECYCLING", []), "Recycling:")

    # The price-label is the line whose label starts with "Price" — its section gives the unit
    price_label: Optional[str] = None
    for row in salient:
        if row.label.lower().startswith("price"):
            price_label = row.label
            break
    if not price_label and price_quotes:
        # Some sheets only emit the "Price ... :" line as a section header, not a row
        price_label = price_quotes[0].unit_note or price_quotes[0].form

    # Latest-year aggregations
    mine_row = (
        _find_row(salient, "Production", "mine")
        or _find_row(salient, None, "mine production")
        or _find_row(salient, None, "production, mine")
        or _find_row(salient, "Production", "mineral concentrates")  # rare-earths: REO mineral concentrates
    )
    refinery_row = (
        _find_row(salient, "Production", "refinery")
        or _find_row(salient, "Production", "primary")
        or _find_row(salient, "Production", "compounds and metals")  # rare-earths: refined REO product
        or _find_row(salient, "Production", "refined")
    )
    secondary_row = _find_row(salient, "Production", "secondary") or _find_row(salient, None, "secondary")

    imports_total = _explicit_total(salient, "imports", latest_year)
    sentinels_acc: dict[str, str] = {}
    if imports_total is None:
        imports_total, s = _latest_value_by_section(salient, "imports", latest_year)
        sentinels_acc.update(s)
    exports_total = _explicit_total(salient, "exports", latest_year)
    if exports_total is None:
        exports_total, s = _latest_value_by_section(salient, "exports", latest_year)
        sentinels_acc.update(s)

    apparent_row = _find_row(salient, None, "apparent")
    apparent = _latest_or_none(apparent_row, latest_year)

    # NIR: pick the row whose label is "Net import reliance ..." with values, or
    # if multi-row (rare earths), the first sub-row under that header.
    nir_row = _find_row(salient, None, "net import reliance")
    if nir_row is None:
        # Look for a row under a section starting with "Net import reliance"
        for row in salient:
            if row.section and row.section.lower().startswith("net import reliance"):
                nir_row = row
                break
    nir = _latest_or_none(nir_row, latest_year)
    nir_raw = nir_row.raw_values.get(latest_year) if nir_row and nir_row.raw_values else None
    if nir_raw and nir_raw not in {"NA"} and (nir_raw in {"W", "E"} or nir_raw.startswith((">", "<"))):
        sentinels_acc["net_import_reliance"] = nir_raw

    # Price: prefer the first price row that actually has the latest-year value.
    # On sheets where the Price section breaks out *separate commodities* rather
    # than alternative quotes for the same commodity (rare earths quotes 9 REE
    # oxides; abrasives quotes 4 abrasive types), picking the first row is
    # arbitrary — but it is at least faithful to the parsed PDF and lets the
    # detail panel show the full per-commodity price table.
    price_row = None
    for row in salient:
        if row.label.lower().startswith("price") and row.values.get(latest_year) is not None:
            price_row = row
            break
    if price_row is None and price_quotes:
        for pq in price_quotes:
            if pq.values.get(latest_year) is not None:
                price_row = YearSeries(label=pq.form, values=pq.values, raw_values=pq.raw_values, section=pq.unit_note)
                break
    price = _latest_or_none(price_row, latest_year)

    # Capture latest-year sentinels for the user-requested columns
    if mine_row:
        raw = mine_row.raw_values.get(latest_year) if mine_row.raw_values else None
        if raw in {"W", "E"} or (raw and raw.startswith((">", "<"))):
            sentinels_acc["mined_production"] = raw
    if refinery_row:
        raw = refinery_row.raw_values.get(latest_year) if refinery_row.raw_values else None
        if raw in {"W", "E"} or (raw and raw.startswith((">", "<"))):
            sentinels_acc["primary_smelting"] = raw
    if secondary_row:
        raw = secondary_row.raw_values.get(latest_year) if secondary_row.raw_values else None
        if raw in {"W", "E"} or (raw and raw.startswith((">", "<"))):
            sentinels_acc["secondary_smelting"] = raw
    if apparent_row:
        raw = apparent_row.raw_values.get(latest_year) if apparent_row.raw_values else None
        if raw in {"W", "E"} or (raw and raw.startswith((">", "<"))):
            sentinels_acc["apparent_consumption"] = raw

    record = ElementRecord(
        slug=el.slug,
        name=el.name,
        symbol=el.symbol,
        kind=el.kind,
        parent_slug=el.parent_slug,
        source_url=el.mcs_url,
        edition=config.MCS_EDITION,
        edition_date=config.MCS_DATE,
        captured_at=_dt.date.today().isoformat(),
        pdf_sha256=fetcher.sha256_of(pdf_path),
        pdf_page_count=page_count,
        units_note=units_note,
        price_unit_note=price_label,
        price_footnote_text=_find_price_footnote(footnotes),
        domestic_use_summary=domestic or None,
        events_trends_summary=events or None,
        world_resources_summary=resources or None,
        substitutes_summary=substitutes or None,
        recycling_summary=recycling or None,
        salient_stats=salient,
        price_quotes=price_quotes,
        latest_year=latest_year,
        mined_production_latest=_latest_or_none(mine_row, latest_year),
        primary_smelting_latest=_latest_or_none(refinery_row, latest_year),
        secondary_smelting_latest=_latest_or_none(secondary_row, latest_year),
        imports_total_latest=imports_total,
        exports_total_latest=exports_total,
        apparent_consumption_latest=apparent,
        price_usd_per_pound_latest=price,
        net_import_reliance_pct_latest=nir,
        latest_year_sentinels=sentinels_acc,
        import_sources_flat=flat_shares,
        import_sources_by_category=by_category,
        import_sources_range=import_range,
        world_production_label=world_label,
        world_production_year_prev=world_year_prev,
        world_production_year_latest=world_year_latest,
        world_production=world_rows,
        stockpile_fy2025_potential_acquisitions=stockpile_fy2025,
        footnotes=footnotes,
    )
    log.info("[%s] %d salient rows | %d price quotes | %d import categories | %d world rows",
             slug, len(salient), len(price_quotes), len(by_category), len(world_rows))
    return record


def _find_price_footnote(footnotes: dict[str, str]) -> Optional[str]:
    """Heuristic: pick the footnote whose body mentions a price source.

    Different sheets use different footnote numbers for the price source
    (Fastmarkets / Argus / etc.), so we scan all footnotes for relevant keywords
    rather than hardcoding "footnote 4".
    """
    for k, v in footnotes.items():
        v_low = v.lower()
        if any(needle in v_low for needle in ("fastmarkets", "argus", "metal bulletin", "platts", "asian metal", "per pound", "per kilogram", "per metric ton", "in-warehouse", "in warehouse")):
            return v
    return None
