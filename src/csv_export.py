"""Long-format CSV export.

One row per (element, salient-stats form). The CSV is the salient-stats
table, period — every per-element fact (latest-year summary, per-country
imports, per-country world production, etc.) lives in `elements.json`,
where it isn't forced to duplicate across an element's many form rows.

Columns:

  name           Display name of the element (with import-category in
                 parens when applicable, e.g. "Antimony (Oxide)" — but
                 long-on-form rows DON'T use category since the row is
                 already disambiguated by section+label).
  kind           primary / rare_earth / grouped / sub_product
  source_url     The traceback URL — the original USGS PDF.
  units_note     Verbatim subtitle of the sheet (e.g. "(Data in metric
                 tons, antimony content, unless otherwise specified)").
  price_unit_note  Verbatim price-row unit text where this is a price form.
  section        The salient-stats section (e.g. "Production",
                 "Imports for consumption", "Price, ...").
  label          The specific form within the section (e.g. "Silicon
                 carbide", "Oxide", "Mine (recoverable antimony)").
  footnote       USGS footnote number attached to the row label, if any.
  2021..2025e    Mixed-type cells: numeric where USGS gave one, otherwise
                 the verbatim sentinel — W (withheld), E (net exporter),
                 >N / <N (approximation), NA (not available). Em-dash
                 renders as 0 (USGS convention for "produced zero").

Each row carries the data for one form across five years. An element
with no salient stats (e.g. heavy-REE aliases like Dysprosium) emits one
placeholder row with section/label/years blank so it still appears in
the CSV under its name.

Mixed-type cells: pandas users who want pure numerics can call
`pd.to_numeric(col, errors="coerce")` to turn W/E/>N/<N/NA into NaN.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Optional

from .models import ElementRecord, YEAR_COLUMNS

log = logging.getLogger(__name__)


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(s: str) -> str:
    return _NON_ALNUM.sub("_", s.lower()).strip("_")


def _val(v: Optional[float]) -> str:
    """Numeric formatter — '' for None.

    Long-format rows are dense by construction (each row is one form's
    five years), so an empty year cell means "USGS didn't print a value
    for this year on this row" — different from N/A on a wide-format
    layout. We render empty rather than N/A so the cell is obviously
    a real absence, not a sentinel.
    """
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v}"


def _text(v: Optional[str]) -> str:
    """Text formatter — '' for None or empty (instead of N/A).

    In the long-format CSV, identity-text cells like price_unit_note
    are blank on rows where the field has nothing to say (e.g. a
    Production row carries no price unit). Blank reads cleanly.
    """
    if v is None or v == "":
        return ""
    return str(v)


def _cell(v: Optional[float], raw: Optional[str]) -> str:
    """Mixed-type cell formatter — merges numeric and sentinel into one column.

    USGS uses five non-numeric markers that lose meaning if we drop them
    in favour of a clean float:

        W    Withheld (company-confidential)
        E    Net exporter (only seen in NIR cells)
        >N   Greater than N (approximation)
        <N   Less than N
        NA   Not available

    When the raw token is one of those, we surface it verbatim. Otherwise
    we use the numeric value (with em-dash → 0 as USGS convention).
    Genuinely missing data renders as an empty cell.
    """
    if raw and (raw in ("W", "E", "NA") or raw.startswith((">", "<"))):
        return raw
    return _val(v)


def build_rows(records: list[ElementRecord]) -> tuple[list[str], list[dict[str, str]]]:
    """Build (header columns in order, list of row dicts).

    Long format: one row per (element, salient-stats form). Per-element
    facts (latest-year summary, per-country tables) are NOT in this CSV
    — they live in elements.json. The CSV's job is to round-trip the
    section/label/year salient-stats matrix in a shape that's analysable
    in pandas / Sheets without 800 sparse columns.
    """
    # Stable column order — all columns are known up-front; nothing is
    # discovered lazily (in contrast to the prior wide format).
    columns: list[str] = [
        "name", "kind", "section", "label", "footnote",
        *YEAR_COLUMNS,
        "source_url", "units_note", "price_unit_note",
    ]

    rows: list[dict[str, str]] = []

    for rec in records:
        base = {
            "name": rec.name,
            "kind": rec.kind,
            "source_url": rec.source_url,
            "units_note": _text(rec.units_note),
            "price_unit_note": _text(rec.price_unit_note),
        }

        if not rec.salient_stats:
            # Aliases with no per-row data (heavy REEs that inherit the parent
            # but blank their salient_stats — Dysprosium, Erbium, Holmium, …)
            # still get one placeholder row so they're discoverable by name.
            row = dict(base)
            row["section"] = ""
            row["label"] = ""
            row["footnote"] = ""
            for yr in YEAR_COLUMNS:
                row[yr] = ""
            rows.append(row)
            continue

        for sr in rec.salient_stats:
            row = dict(base)
            row["section"] = sr.section or ""
            row["label"] = sr.label
            row["footnote"] = sr.footnote or ""
            for yr in YEAR_COLUMNS:
                row[yr] = _cell(sr.values.get(yr), (sr.raw_values or {}).get(yr))
            rows.append(row)

    return columns, rows


def write_csv(records: list[ElementRecord], out_path) -> None:
    """Write the long-format CSV."""
    columns, rows = build_rows(records)
    out_path.write_text(_render(columns, rows), encoding="utf-8")
    log.info("wrote csv -> %s (%d rows × %d cols)", out_path, len(rows), len(columns))


def _render(columns: list[str], rows: list[dict[str, str]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "") for c in columns})
    return buf.getvalue()
