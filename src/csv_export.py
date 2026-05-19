"""Wide-table CSV export.

One row per element/alias. Columns are grouped into sections:

  identity              slug, name, symbol, kind, parent_slug, source_url,
                        edition, edition_date, captured_at, pdf_sha256,
                        pdf_page_count, units_note, price_unit_note,
                        latest_year, import_sources_range, world_production_label
  latest-year summary   mined_production_latest, primary_smelting_latest,
                        secondary_smelting_latest, imports_total_latest,
                        exports_total_latest, apparent_consumption_latest,
                        price_usd_per_pound_latest, net_import_reliance_pct_latest
                        + matching *_sentinel columns for "W"/"E"/">N"
  per-form salient      salient__<section>__<label>__<year>  (+ _raw)
                        — e.g. antimony's "Imports - Oxide - 2025e" round-trips
  per-form price        price__<form>__<year>  (+ _raw)

  --- country sections (filled across all elements with N/A for missing) ---
  imports               imports__<category>__<country>
                        Category is "all" for single-list sheets (bismuth)
                        or the USGS category name (antimony's Ore / Oxide / ...)
  world production      world_prod__<country>__prev
                        world_prod__<country>__latest   (+ _raw)
                        world_prod__<country>__capacity
  world reserves        world_reserves__<country>  (+ _raw)

The country axis is the alphabetical union of every country appearing in any
element's USGS table, with "World *" aggregate rows pushed to the end of each
section. Cells where the country isn't tabulated for a given element are
filled with "N/A" so the CSV is rectangular and pandas-friendly. Cells where
USGS reported an em-dash (zero) keep "0"; cells where USGS reported "NA"
also render as "N/A".

That's many columns — explicitly OK'd. Expect 1000+ when run on the full
registry.
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
    """Numeric formatter — '' for None.

    Used for non-country cells where 'missing' is a different concept from
    'reported NA' and we don't want to force a value.
    """
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v}"


def _country_val(v: Optional[float]) -> str:
    """Numeric formatter for country cells — 'N/A' for None.

    Every country column is filled for every element so the CSV is rectangular;
    'N/A' covers both 'USGS reported NA' and 'country not tabulated for this
    element'. Em-dash (zero) is preserved as '0' because USGS uses em-dash to
    mean "produced zero", not "unknown".
    """
    if v is None:
        return "N/A"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v}"


def _sorted_countries(countries: Iterable[str]) -> list[str]:
    """Alphabetical ordering; 'World *' aggregates pushed to the end.

    USGS rows like 'World total (rounded)' aren't real countries but DO carry
    useful summary numbers. Keeping them at the tail of the country axis means
    the alphabetical block reads naturally and totals are easy to find.
    """
    primary = sorted(c for c in countries if not c.lower().startswith("world"))
    aggregates = sorted(c for c in countries if c.lower().startswith("world"))
    return primary + aggregates


def _cat_slug(name: Optional[str]) -> str:
    """Normalize an import-source category name to a slug.

    `None` (bismuth-style flat list) becomes 'all'.
    """
    if name is None:
        return "all"
    return _slugify(name) or "all"


def _collect_country_axes(records: list[ElementRecord]) -> dict:
    """Pre-pass: build the union of (category × country) for each section.

    Run before column registration so per-country columns are stable: every
    element gets the same imports / world-prod / reserves columns in the same
    order, regardless of which element appears first in the input.

    Also detects which countries have non-trivial `_raw` cells so we only
    emit `_raw` columns where they'll carry information.
    """
    import_categories: set[str] = set()
    imports_countries: set[str] = set()
    world_countries: set[str] = set()
    world_latest_raw_countries: set[str] = set()
    reserves_countries: set[str] = set()
    reserves_raw_countries: set[str] = set()

    for rec in records:
        for cat in rec.import_sources_by_category:
            import_categories.add(_cat_slug(cat.category))
            for cs in cat.countries:
                imports_countries.add(cs.country)
        # bismuth-style flat list is normally also in by_category as category=None,
        # but include it as a backup in case the parser populated only the flat list.
        for cs in rec.import_sources_flat:
            imports_countries.add(cs.country)
        for wp in rec.world_production:
            world_countries.add(wp.country)
            if wp.production_latest_raw and wp.production_latest_raw != _val(wp.production_latest_year):
                world_latest_raw_countries.add(wp.country)
            if wp.reserves is not None or wp.reserves_raw not in (None, ""):
                reserves_countries.add(wp.country)
            if wp.reserves_raw and wp.reserves_raw != _val(wp.reserves):
                reserves_raw_countries.add(wp.country)

    return {
        "import_categories": sorted(import_categories),
        "imports_countries": _sorted_countries(imports_countries),
        "world_countries": _sorted_countries(world_countries),
        "world_latest_raw_countries": world_latest_raw_countries,
        "reserves_countries": _sorted_countries(reserves_countries),
        "reserves_raw_countries": reserves_raw_countries,
    }


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
        "slug", "name", "symbol", "kind", "parent_slug", "source_url", "edition", "edition_date",
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

    # Salient-stats + price columns are still discovered lazily during the row
    # loop (their column space is shaped by per-element schemas, not unioned).
    for rec in records:
        row: dict[str, str] = {}
        row["slug"] = rec.slug
        row["name"] = rec.name
        row["symbol"] = rec.symbol or ""
        row["kind"] = rec.kind
        row["parent_slug"] = rec.parent_slug or ""
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

        rows.append(row)

    # ---- Country sections — registered after a pre-pass so columns are stable
    # across the full record set, and every cell is filled (N/A if absent) so
    # the CSV is rectangular for pandas / sheets consumers.
    axes = _collect_country_axes(records)

    imports_col_names: dict[tuple[str, str], str] = {}
    for cat_slug in axes["import_categories"]:
        for country in axes["imports_countries"]:
            cname = col(f"imports__{cat_slug}__{_slugify(country)}")
            imports_col_names[(cat_slug, country)] = cname

    world_prev_cols: dict[str, str] = {}
    world_latest_cols: dict[str, str] = {}
    world_latest_raw_cols: dict[str, str] = {}
    world_capacity_cols: dict[str, str] = {}
    for country in axes["world_countries"]:
        c_slug = _slugify(country)
        world_prev_cols[country] = col(f"world_prod__{c_slug}__prev")
        world_latest_cols[country] = col(f"world_prod__{c_slug}__latest")
        if country in axes["world_latest_raw_countries"]:
            world_latest_raw_cols[country] = col(f"world_prod__{c_slug}__latest_raw")
        world_capacity_cols[country] = col(f"world_prod__{c_slug}__capacity")

    reserves_cols: dict[str, str] = {}
    reserves_raw_cols: dict[str, str] = {}
    for country in axes["reserves_countries"]:
        c_slug = _slugify(country)
        reserves_cols[country] = col(f"world_reserves__{c_slug}")
        if country in axes["reserves_raw_countries"]:
            reserves_raw_cols[country] = col(f"world_reserves__{c_slug}_raw")

    # Second pass to fill the country cells.
    for rec, row in zip(records, rows):
        # Default every country cell to N/A; values overwrite as we find them.
        for cname in imports_col_names.values():
            row[cname] = "N/A"
        for cname in world_prev_cols.values():
            row[cname] = "N/A"
        for cname in world_latest_cols.values():
            row[cname] = "N/A"
        for cname in world_capacity_cols.values():
            row[cname] = "N/A"
        for cname in world_latest_raw_cols.values():
            row[cname] = ""  # raw is genuinely empty if no sentinel
        for cname in reserves_cols.values():
            row[cname] = "N/A"
        for cname in reserves_raw_cols.values():
            row[cname] = ""

        # Imports
        for cat in rec.import_sources_by_category:
            cs_slug = _cat_slug(cat.category)
            for cs in cat.countries:
                cname = imports_col_names.get((cs_slug, cs.country))
                if cname is not None:
                    row[cname] = _country_val(cs.share_pct)

        # World production
        for wp in rec.world_production:
            country = wp.country
            if country in world_prev_cols:
                row[world_prev_cols[country]] = _country_val(wp.production_prev_year)
                row[world_latest_cols[country]] = _country_val(wp.production_latest_year)
                row[world_capacity_cols[country]] = _country_val(wp.capacity)
                raw_col = world_latest_raw_cols.get(country)
                if raw_col and wp.production_latest_raw and wp.production_latest_raw != _val(wp.production_latest_year):
                    row[raw_col] = wp.production_latest_raw
            if country in reserves_cols:
                row[reserves_cols[country]] = _country_val(wp.reserves)
                raw_col = reserves_raw_cols.get(country)
                if raw_col and wp.reserves_raw and wp.reserves_raw != _val(wp.reserves):
                    row[raw_col] = wp.reserves_raw

    return columns, rows


def write_csv(records: list[ElementRecord], out_path) -> None:
    """Write CSV with grouped columns; country cells are filled with N/A
    when the country isn't in this element's USGS table.
    """
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
