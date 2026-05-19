"""Wide-table CSV export.

One row per (element/alias, import-source category). Multi-category sheets
like antimony emit one row per category (Ore and concentrates / Oxide /
Unwrought metal and powder / Total metal and oxide); single-category sheets
like bismuth emit one row with `import_category=""`. The UX viewer still
shows one detail panel per element (it reads the JSON, which keeps one record
per element).

Columns are grouped into sections:

  identity              name, kind, source_url, edition, captured_at,
                        units_note, price_unit_note, latest_year,
                        import_sources_range, world_production_label,
                        import_category
                        (slug, symbol, parent_slug, edition_date,
                        pdf_sha256, and pdf_page_count are intentionally
                        omitted from the CSV — they're still in elements.json
                        for anyone who needs the traceback metadata.)
  latest-year summary   mined_production_latest, primary_smelting_latest,
                        secondary_smelting_latest, imports_total_latest,
                        exports_total_latest, apparent_consumption_latest,
                        price_usd_per_pound_latest, net_import_reliance_pct_latest
                        + matching *_sentinel columns for "W"/"E"/">N"
  per-form salient      salient__<section>__<label>__<year>  (+ _raw)
                        — e.g. antimony's "Imports - Oxide - 2025e" round-trips
  per-form price        price__<form>__<year>  (+ _raw)

  --- per-country columns (filled across all elements with N/A for missing) ---
  imports share         <country>_imports_share_pct
                        Each row's share reflects the row's `import_category`
                        only. Countries not in that category render as "N/A".
                        The country axis is the alphabetical union across
                        every category of every element.
  production            <country>_production_<year>     (+ <country>_production_<year>_raw)
                        Years come straight from the PDF's world-production
                        table sub-header (e.g. "2024" / "2025" for MCS 2026).
                        Elements with different year pairs get their own
                        column set; the other rows fall to N/A. Duplicated
                        across an element's category rows because USGS does
                        not categorise world production.
  capacity              <country>_capacity
  reserves              <country>_reserves              (+ <country>_reserves_raw)

The country axis sorts "World *" aggregate rows to the end of each section.
Cells where the country isn't tabulated for a given element are filled with
"N/A" so the CSV is rectangular and pandas-friendly. Em-dash (zero) keeps
"0"; USGS-reported "NA" also renders as "N/A".

That's many columns — explicitly OK'd. Expect 1000+ when run on the full
registry.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Iterable, Optional

from .models import ElementRecord, ImportSourceCategory, YEAR_COLUMNS

log = logging.getLogger(__name__)


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(s: str) -> str:
    return _NON_ALNUM.sub("_", s.lower()).strip("_")


def _val(v: Optional[float]) -> str:
    """Numeric formatter — 'N/A' for None.

    Per user instruction: never leave a missing value blank. USGS-reported
    em-dash "—" is converted to 0.0 upstream (USGS convention for "produced
    zero") and renders as "0" here. Only genuinely missing values become N/A.
    """
    if v is None:
        return "N/A"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v}"


def _text(v: Optional[str]) -> str:
    """Text formatter — 'N/A' for None or empty.

    Used for identity/text fields (symbol, parent_slug, price_unit_note, etc.).
    Empty source values are treated as missing.
    """
    if v is None or v == "":
        return "N/A"
    return str(v)


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


def _collect_country_axes(records: list[ElementRecord]) -> dict:
    """Pre-pass: build the union of countries for each section.

    Run before column registration so per-country columns are stable: every
    element gets the same imports / world-prod / reserves columns in the same
    order, regardless of which element appears first in the input.

    Imports country axis is flat now (no category dimension) — the long-format
    rows carry the category in their own `import_category` column.

    Also detects which countries have non-trivial `_raw` cells so we only
    emit `_raw` columns where they'll carry information.
    """
    imports_countries: set[str] = set()
    world_countries: set[str] = set()
    world_latest_raw_countries: set[str] = set()
    reserves_countries: set[str] = set()
    reserves_raw_countries: set[str] = set()

    for rec in records:
        for cat in rec.import_sources_by_category:
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
        "imports_countries": _sorted_countries(imports_countries),
        "world_countries": _sorted_countries(world_countries),
        "world_latest_raw_countries": world_latest_raw_countries,
        "reserves_countries": _sorted_countries(reserves_countries),
        "reserves_raw_countries": reserves_raw_countries,
    }


def _category_rows_for(rec: ElementRecord) -> list[Optional[ImportSourceCategory]]:
    """Return the list of import-source categories that should each become a CSV row.

    - Multi-category sheets (antimony, molybdenum, abrasives, …) → one entry
      per `ImportSourceCategory`.
    - Single-category sheets (bismuth) → one entry with `category=None`.
    - Sheets with only a flat list and no `by_category` → wrap the flat list
      into a synthetic category entry.
    - Sheets with no import sources at all → one `None` entry so the element
      still appears in the CSV.
    """
    if rec.import_sources_by_category:
        return list(rec.import_sources_by_category)
    if rec.import_sources_flat:
        return [ImportSourceCategory(category=None, countries=list(rec.import_sources_flat))]
    return [None]


def build_rows(records: list[ElementRecord]) -> tuple[list[str], list[dict[str, str]]]:
    """Build (header columns in order, list of row dicts).

    Emits one row per (element, import-source category). All identity / salient /
    price / world-production columns are duplicated across an element's rows;
    only the `imports__<country>` columns vary, reflecting the row's category.
    """
    columns: list[str] = []
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    # Parallel to `rows`: (record, category) for the country-fill pass.
    row_meta: list[tuple[ElementRecord, Optional[ImportSourceCategory]]] = []

    def col(name: str) -> str:
        """Register a column on first sight; preserves discovery order."""
        if name not in seen:
            columns.append(name)
            seen.add(name)
        return name

    # Stable identity columns first so the CSV is readable at a glance.
    # `slug`, `symbol`, `parent_slug`, `edition_date`, `pdf_sha256`, and
    # `pdf_page_count` were removed in favour of a leaner header — they
    # remain in `elements.json` for anyone who needs them, but the CSV is
    # tuned for human/Sheets consumers who already get the same identity
    # from `name` + `kind` + `edition`.
    for name in (
        "name", "kind", "source_url", "edition",
        "captured_at", "units_note", "price_unit_note",
        "latest_year", "import_sources_range", "world_production_label",
        "import_category",
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
        for cat in _category_rows_for(rec):
            row: dict[str, str] = {}
            row["name"] = rec.name
            row["kind"] = rec.kind
            row["source_url"] = rec.source_url
            row["edition"] = rec.edition
            row["captured_at"] = rec.captured_at
            row["units_note"] = _text(rec.units_note)
            row["price_unit_note"] = _text(rec.price_unit_note)
            row["latest_year"] = rec.latest_year
            row["import_sources_range"] = _text(rec.import_sources_range)
            row["world_production_label"] = _text(rec.world_production_label)
            # import_category is structural — "" means "this row covers the
            # element's only (uncategorized) import line"; not missing data.
            row["import_category"] = (cat.category if cat and cat.category else "")

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
            row_meta.append((rec, cat))

    # ---- Country sections — registered after a pre-pass so columns are stable
    # across the full record set, and every cell is filled (N/A if absent) so
    # the CSV is rectangular for pandas / sheets consumers.
    axes = _collect_country_axes(records)

    imports_col_names: dict[str, str] = {}
    for country in axes["imports_countries"]:
        imports_col_names[country] = col(f"{_slugify(country)}_imports_share_pct")

    # Production columns are keyed by (country, year), so two elements with
    # different year pairs (e.g. "2024"/"2025" vs "2023"/"2024") get separate
    # column sets and neither stomps on the other. Years come from each
    # element's `world_production_year_{prev,latest}` (captured verbatim from
    # the PDF's year-sub-header band). Elements missing the headers (rare —
    # currently only germanium and scandium, neither of which has world rows)
    # fall back to "prev"/"latest" so the data still lands somewhere.
    # Maps: (country, year_label) -> column name
    world_prev_cols: dict[tuple[str, str], str] = {}
    world_latest_cols: dict[tuple[str, str], str] = {}
    world_latest_raw_cols: dict[tuple[str, str], str] = {}
    world_capacity_cols: dict[str, str] = {}

    def _years_for(rec: ElementRecord) -> tuple[str, str]:
        yp = rec.world_production_year_prev or "prev"
        yl = rec.world_production_year_latest or "latest"
        return yp, yl

    for rec in records:
        yp, yl = _years_for(rec)
        for wp in rec.world_production:
            c = wp.country
            c_slug = _slugify(c)
            if (c, yp) not in world_prev_cols:
                world_prev_cols[(c, yp)] = col(f"{c_slug}_production_{yp}")
            if (c, yl) not in world_latest_cols:
                world_latest_cols[(c, yl)] = col(f"{c_slug}_production_{yl}")
            # Only register a _raw column where some element actually carries
            # a non-redundant raw token (W / E / >N / etc.) for that cell.
            if c in axes["world_latest_raw_countries"] and (c, yl) not in world_latest_raw_cols:
                world_latest_raw_cols[(c, yl)] = col(f"{c_slug}_production_{yl}_raw")
            if c not in world_capacity_cols:
                world_capacity_cols[c] = col(f"{c_slug}_capacity")

    reserves_cols: dict[str, str] = {}
    reserves_raw_cols: dict[str, str] = {}
    for country in axes["reserves_countries"]:
        c_slug = _slugify(country)
        reserves_cols[country] = col(f"{c_slug}_reserves")
        if country in axes["reserves_raw_countries"]:
            reserves_raw_cols[country] = col(f"{c_slug}_reserves_raw")

    # Second pass to fill the country cells. Imports vary per row (one category
    # each); world production and reserves are duplicated across an element's
    # category rows because they aren't categorized by USGS.
    for (rec, cat), row in zip(row_meta, rows):
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

        # Imports — only the row's own category fills cells.
        if cat is not None:
            for cs in cat.countries:
                cname = imports_col_names.get(cs.country)
                if cname is not None:
                    row[cname] = _country_val(cs.share_pct)

        # World production — full table on every row of an element.
        yp, yl = _years_for(rec)
        for wp in rec.world_production:
            country = wp.country
            prev_key = (country, yp)
            latest_key = (country, yl)
            if prev_key in world_prev_cols:
                row[world_prev_cols[prev_key]] = _country_val(wp.production_prev_year)
            if latest_key in world_latest_cols:
                row[world_latest_cols[latest_key]] = _country_val(wp.production_latest_year)
                raw_col = world_latest_raw_cols.get(latest_key)
                if raw_col and wp.production_latest_raw and wp.production_latest_raw != _val(wp.production_latest_year):
                    row[raw_col] = wp.production_latest_raw
            if country in world_capacity_cols:
                row[world_capacity_cols[country]] = _country_val(wp.capacity)
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
    """Render with 'N/A' as the default for any column we didn't explicitly fill.

    Salient-stats and price columns are discovered lazily during the row loop —
    any element whose schema lacks that column falls to this default. Per the
    user's instruction (never blank, never fake), missing data renders as N/A.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "N/A") for c in columns})
    return buf.getvalue()
