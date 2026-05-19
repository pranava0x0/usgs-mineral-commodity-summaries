"""Wide-table CSV export.

One row per element/alias. Columns are flat snake_case and include:

  identity              slug, name, symbol, parent_slug, source_url, units_note
  per-year US summary   {field}_{year} for every salient-stats row, with both
                        the numeric and the raw token (e.g. "W", ">95")
  computed aggregates   imports_total_<year>, exports_total_<year>,
                        mined_production_<year>, primary_smelting_<year>, etc.
  per-form salient      {section}_{form}_{year} so antimony's
                        "Imports for consumption - Oxide - 2025e" round-trips
  per-category imports  import_share_{category}_{country} (multi-category sheets)
  per-country world     world_{country}_{prev|latest|reserves}

That's many columns — the user explicitly OK'd "many columns is fine."
"""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Iterable, Optional

from .models import ElementRecord, YEAR_COLUMNS

log = logging.getLogger(__name__)


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(s: str) -> str:
    return _NON_ALNUM.sub("_", s.lower()).strip("_")


def _val(v: Optional[float]) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v}"


def build_rows(records: list[ElementRecord]) -> tuple[list[str], list[dict[str, str]]]:
    """Build (header columns in order, list of row dicts)."""
    columns: list[str] = []
    seen: set[str] = set()
    rows: list[dict[str, str]] = []

    def col(name: str) -> str:
        """Register a column on first sight; preserves discovery order."""
        if name not in seen:
            columns.append(name)
            seen.add(name)
        return name

    # Stable identity columns first so the CSV is readable at a glance.
    for name in (
        "slug", "name", "symbol", "parent_slug", "source_url", "edition", "edition_date",
        "captured_at", "pdf_sha256", "pdf_page_count", "units_note", "price_unit_note",
        "latest_year", "import_sources_range", "world_production_label",
    ):
        col(name)
    # User-requested top-level columns
    for name in (
        "mined_production_latest", "primary_smelting_latest", "secondary_smelting_latest",
        "imports_total_latest", "exports_total_latest", "apparent_consumption_latest",
        "price_usd_per_pound_latest", "net_import_reliance_pct_latest",
    ):
        col(name)
    for sk in ("mined_production", "primary_smelting", "secondary_smelting",
               "apparent_consumption", "net_import_reliance"):
        col(f"{sk}_latest_sentinel")

    for rec in records:
        row: dict[str, str] = {}
        row["slug"] = rec.slug
        row["name"] = rec.name
        row["symbol"] = rec.symbol or ""
        row["parent_slug"] = ""  # filled by caller for alias records
        row["source_url"] = rec.source_url
        row["edition"] = rec.edition
        row["edition_date"] = rec.edition_date
        row["captured_at"] = rec.captured_at
        row["pdf_sha256"] = rec.pdf_sha256
        row["pdf_page_count"] = str(rec.pdf_page_count)
        row["units_note"] = rec.units_note
        row["price_unit_note"] = rec.price_unit_note or ""
        row["latest_year"] = rec.latest_year
        row["import_sources_range"] = rec.import_sources_range or ""
        row["world_production_label"] = rec.world_production_label or ""

        # Latest-year user columns
        row["mined_production_latest"] = _val(rec.mined_production_latest)
        row["primary_smelting_latest"] = _val(rec.primary_smelting_latest)
        row["secondary_smelting_latest"] = _val(rec.secondary_smelting_latest)
        row["imports_total_latest"] = _val(rec.imports_total_latest)
        row["exports_total_latest"] = _val(rec.exports_total_latest)
        row["apparent_consumption_latest"] = _val(rec.apparent_consumption_latest)
        row["price_usd_per_pound_latest"] = _val(rec.price_usd_per_pound_latest)
        row["net_import_reliance_pct_latest"] = _val(rec.net_import_reliance_pct_latest)
        for sk in ("mined_production", "primary_smelting", "secondary_smelting",
                   "apparent_consumption", "net_import_reliance"):
            row[f"{sk}_latest_sentinel"] = rec.latest_year_sentinels.get(sk, "")

        # Per-year, per-row salient stats. Column name format:
        #   salient__<section_slug>__<label_slug>__<year>          (numeric)
        #   salient__<section_slug>__<label_slug>__<year>_raw      (literal token)
        for yr in YEAR_COLUMNS:
            for rec_row in rec.salient_stats:
                sec = _slugify(rec_row.section or "")
                lbl = _slugify(rec_row.label)
                col_name = col(f"salient__{sec}__{lbl}__{yr}")
                row[col_name] = _val(rec_row.values.get(yr))
                raw = (rec_row.raw_values or {}).get(yr)
                if raw is not None and raw != "":
                    raw_col = col(f"salient__{sec}__{lbl}__{yr}_raw")
                    row[raw_col] = str(raw)

        # Price quotes
        for yr in YEAR_COLUMNS:
            for pq in rec.price_quotes:
                form = _slugify(pq.form)
                col_name = col(f"price__{form}__{yr}")
                row[col_name] = _val(pq.values.get(yr))
                raw = (pq.raw_values or {}).get(yr)
                if raw not in (None, ""):
                    row[col(f"price__{form}__{yr}_raw")] = str(raw)

        # Import sources (multi-category supported)
        for cat in rec.import_sources_by_category:
            cat_slug = _slugify(cat.category) if cat.category else "all"
            for cs in cat.countries:
                row[col(f"import_share__{cat_slug}__{_slugify(cs.country)}")] = _val(cs.share_pct)

        # World production rows
        for wp in rec.world_production:
            c_slug = _slugify(wp.country)
            row[col(f"world__{c_slug}__production_prev")] = _val(wp.production_prev_year)
            row[col(f"world__{c_slug}__production_latest")] = _val(wp.production_latest_year)
            row[col(f"world__{c_slug}__capacity")] = _val(wp.capacity)
            row[col(f"world__{c_slug}__reserves")] = _val(wp.reserves)
            if wp.production_latest_raw and wp.production_latest_raw not in {"", _val(wp.production_latest_year)}:
                row[col(f"world__{c_slug}__production_latest_raw")] = wp.production_latest_raw
            if wp.reserves_raw and wp.reserves_raw not in {"", _val(wp.reserves)}:
                row[col(f"world__{c_slug}__reserves_raw")] = wp.reserves_raw

        rows.append(row)

    return columns, rows


def write_csv(records: list[ElementRecord], out_path) -> None:
    """Write CSV with discovery-order columns; missing cells are empty."""
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
