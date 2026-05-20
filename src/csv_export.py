"""Wide-table CSV export — public spec, May 2026.

Shape: ~140 rows × ~1,032 cols. One row per (element/alias, import-source
category). Multi-category sheets like antimony emit one row per category;
single-category sheets like bismuth emit one row with `import_category=""`.

Column layout (left to right):

  IDENTITY (8)
    name, kind, source_url, units_note, price_unit_note,
    import_sources_range, world_production_label, import_category

  SUMMARY (9)
    usgs_2025_total_mined_production
    usgs_2025_total_primary_smelting
    usgs_2025_total_secondary_smelting
    imports_for_consumption_total
    exports_total
    consumption_apparent
    price_metal_average_dollars_per_pound
    net_import_reliance_pct
    government_stockpile_fy2025_potential_acquisitions

  IMPORT SOURCES (203)   — per-country % share for this row's category
  MINE PRODUCTION (203)  — latest-year production value where the element
                           belongs to the Mine Production block
  REFINERY PRODUCTION (203) — same, for Refinery-block elements
  CAPACITY (203)         — refinery / production capacity where reported
  RESERVES (203)         — per-country reserves

Block placement per element is hardcoded in `ELEMENT_PRODUCTION_BLOCK`
(see comment there for the why). Elements with no world-production table
(scandium, abrasives, titanium) leave all country blocks at N/A but still
have a row so identity + summary columns are visible.

Country mapping: USGS names → canonical 203-country list via
`src.countries.map_country`. EU member states roll up into "European
Union". The 4 priority entries (Canada, China, Mexico, European Union)
sit at the head of every block, then regional alphabetical to Vatican City.

Mixed-type cells. Each numeric cell carries either a number or one of
USGS's non-numeric markers (W/E/>N/<N/NA) verbatim. Pandas users coerce
with `pd.to_numeric(col, errors="coerce")` to turn sentinels into NaN.
Cells where the country is missing from the element's table render as
"N/A" so the CSV stays rectangular.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Iterable, Optional

from .countries import CANONICAL_COUNTRIES, canonical_slugs, map_country
from .models import ElementRecord, ImportSourceCategory

log = logging.getLogger(__name__)


# --- Block placement --------------------------------------------------------
#
# Which country block this element's world_production fills. Hardcoded
# per element because USGS uses varying section titles ("World Production",
# "Mine Production and Reserves", "Refinery Production and Capacity") that
# don't carry a clean machine-readable mine-vs-refinery signal.
#
#   "mine"        Mine Production block; world_production[*].production_latest_year
#                 fills the country cell. Reserves block fills from `.reserves`.
#   "refinery"    Refinery Production block; same field, different block.
#                 Capacity block fills from `.capacity`.
#   None          Element has no per-country world table (titanium, scandium,
#                 abrasives). All country blocks fall to N/A for these.
#
# Per user (2026-05-19):
#   - Iron and Steel pig iron & raw steel both → Refinery Production (PDF
#     label is just "World Production"; user override placed both in Refinery).
#   - Gallium → Refinery (USGS calls it "Primary Low-Purity Production",
#     a smelter-stage byproduct).
#   - Bismuth → Refinery + Capacity (capacity all-NA in the source).
#   - Indium / Tellurium → Refinery + Capacity.
#   - Germanium → Refinery (prose-only — no world table).
ELEMENT_PRODUCTION_BLOCK: dict[str, str | None] = {
    # Mine + Reserves
    "antimony": "mine", "aluminum": "mine", "chromium": "mine", "cobalt": "mine",
    "copper": "mine", "diamond": "mine", "graphite": "mine", "lithium": "mine",
    "magnesium": "mine", "manganese": "mine", "molybdenum": "mine", "nickel": "mine",
    "niobium": "mine", "rare-earths": "mine", "silver": "mine", "tantalum": "mine",
    "tin": "mine", "tungsten": "mine", "vanadium": "mine", "zinc": "mine",
    "zirconium-and-hafnium": "mine",
    # Refinery + Capacity
    "bismuth": "refinery", "indium": "refinery", "tellurium": "refinery",
    "germanium": "refinery", "gallium": "refinery",
    "iron-and-steel": "refinery",
    # Grouped parent — reserves only (per BACKLOG); PGM aliases handled by alias inheritance.
    "platinum-group-metals": "mine",
    # No per-country world table
    "rhenium": None,
    "silicon": None,
    "titanium": None,
    "abrasives": None,
    "scandium": None,
}


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(s: str) -> str:
    return _NON_ALNUM.sub("_", s.lower()).strip("_")


def _val(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v}"


def _text(v: Optional[str]) -> str:
    if v is None or v == "":
        return "N/A"
    return str(v)


def _cell(v: Optional[float], raw: Optional[str]) -> str:
    """Mixed-type formatter — verbatim USGS sentinel if present, else numeric."""
    if raw and (raw in ("W", "E", "NA") or raw.startswith((">", "<"))):
        return raw
    return _val(v)


# --- Identity / summary column lists ---------------------------------------

IDENTITY_COLUMNS: tuple[str, ...] = (
    "name", "kind", "source_url",
    "units_note", "price_unit_note",
    "import_sources_range", "world_production_label",
    "import_category",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "usgs_2025_total_mined_production",
    "usgs_2025_total_primary_smelting",
    "usgs_2025_total_secondary_smelting",
    "imports_for_consumption_total",
    "exports_total",
    "consumption_apparent",
    "price_metal_average_dollars_per_pound",
    "net_import_reliance_pct",
    "government_stockpile_fy2025_potential_acquisitions",
)


def _country_column_slugs() -> list[str]:
    """One slug per CANONICAL_COUNTRIES entry. Duplicates (China, Syria)
    get a `__2` suffix on the second occurrence so dict keys stay unique."""
    return canonical_slugs()


def _block_columns(block_suffix: str) -> list[str]:
    return [f"{c}__{block_suffix}" for c in _country_column_slugs()]


def _category_rows_for(rec: ElementRecord) -> list[Optional[ImportSourceCategory]]:
    """One CSV row per import-source category — bismuth-style single-list
    sheets emit one row with `category=None`; sheets with no import data
    emit one bare row so identity/summary cells are still visible.

    Special case: the PGM grouped parent (`platinum-group-metals`) collapses
    to a single bare row even though the source PDF lists Pd and Pt as
    separate import categories. Per-metal data lives on the individual
    PGM aliases (palladium, platinum, …); the grouped parent represents
    the aggregate, so splitting it twice was double-counting visual
    information.

    Same logic for the titanium parent: its two import categories ("Sponge
    metal" / "TiO pigment") move to the titanium-sponge-metal /
    titanium-dioxide sub-rows, so the de-blended parent collapses to one
    bare row.
    """
    if rec.slug in ("platinum-group-metals", "titanium"):
        return [None]
    if rec.import_sources_by_category:
        return list(rec.import_sources_by_category)
    if rec.import_sources_flat:
        return [ImportSourceCategory(category=None, countries=list(rec.import_sources_flat))]
    return [None]


def _aggregate_country_values(
    items: Iterable[tuple[str, Optional[float], Optional[str]]],
) -> dict[str, tuple[Optional[float], Optional[str]]]:
    """Map USGS country rows to canonical names, summing values where the
    canonical entry collapses multiple USGS rows (e.g. EU rollup combines
    Germany + France + Belgium).

    Sentinel handling: when EVERY contributing USGS row carries the same
    sentinel (W / E / NA), surface that sentinel verbatim — summing
    sentinels is meaningless. If contributors mix numeric + sentinels, the
    numeric portion wins (sentinel is dropped); this errs toward "show
    some number" rather than "hide the only data we have".
    """
    out: dict[str, tuple[Optional[float], Optional[str]]] = {}
    seen_sentinels: dict[str, set[str]] = {}
    seen_numeric: dict[str, bool] = {}

    for usgs_name, value, raw in items:
        canonical = map_country(usgs_name)
        if canonical is None:
            continue
        is_sentinel = raw and (
            raw in ("W", "E", "NA") or raw.startswith((">", "<"))
        )
        if is_sentinel:
            seen_sentinels.setdefault(canonical, set()).add(raw)
            if canonical not in seen_numeric:
                seen_numeric[canonical] = False
                out.setdefault(canonical, (None, raw))
        else:
            # numeric
            prev_v, prev_raw = out.get(canonical, (None, None))
            new_v = (prev_v or 0.0) + (value or 0.0) if value is not None else prev_v
            out[canonical] = (new_v, None)
            seen_numeric[canonical] = True

    # If a canonical entry saw ONLY sentinels (no numeric), keep the sentinel
    # token in the raw slot. The caller's formatter renders it verbatim.
    for canonical in list(out.keys()):
        if not seen_numeric.get(canonical) and seen_sentinels.get(canonical):
            tokens = seen_sentinels[canonical]
            # One sentinel: surface it; multiple distinct: leave a generic NA.
            tok = next(iter(tokens)) if len(tokens) == 1 else "NA"
            out[canonical] = (None, tok)

    return out


def build_rows(records: list[ElementRecord]) -> tuple[list[str], list[dict[str, str]]]:
    """Build (header columns in order, list of row dicts)."""
    # Pre-compute the country axis once — it's fixed by the spec.
    country_slugs = _country_column_slugs()
    imports_cols = _block_columns("imports_share_pct")
    mine_cols = _block_columns("mine_production")
    refinery_cols = _block_columns("refinery_production")
    capacity_cols = _block_columns("capacity")
    reserves_cols = _block_columns("reserves")

    columns: list[str] = (
        list(IDENTITY_COLUMNS)
        + list(SUMMARY_COLUMNS)
        + imports_cols
        + mine_cols
        + refinery_cols
        + capacity_cols
        + reserves_cols
    )

    rows: list[dict[str, str]] = []

    for rec in records:
        block = ELEMENT_PRODUCTION_BLOCK.get(rec.slug)
        # Aliases inherit their parent slug's placement. The parent_slug is
        # the registry parent (rare-earths / platinum-group-metals /
        # iron-and-steel / etc.). REEs map to "mine" (REO content); PGM
        # aliases inherit "mine" too. Sub-products take the parent's block.
        if block is None and rec.parent_slug:
            block = ELEMENT_PRODUCTION_BLOCK.get(rec.parent_slug)

        # PGM grouped parent: per-country mine/refinery/capacity is
        # metal-specific (Pd ≠ Pt), so it's meaningless at the group level.
        # Reserves are group-level in the PDF and stay populated.
        if rec.slug == "platinum-group-metals":
            block = None  # blanks mine + refinery + capacity blocks
            # (reserves are filled from world_production[*].reserves regardless of block)

        # Pre-aggregate world production once per record (same across an
        # element's category rows). Reserves get aggregated independent of
        # the mine/refinery block decision so the PGM grouped parent (which
        # has block=None) still shows per-country reserves — USGS reports
        # PGM reserves at the group level and they're the only meaningful
        # per-country figure for the parent row.
        prod_by_canonical: dict[str, tuple[Optional[float], Optional[str]]] = {}
        capacity_by_canonical: dict[str, tuple[Optional[float], Optional[str]]] = {}
        reserves_by_canonical: dict[str, tuple[Optional[float], Optional[str]]] = {}

        if rec.world_production:
            res_items = [
                (wp.country, wp.reserves, wp.reserves_raw)
                for wp in rec.world_production
            ]
            reserves_by_canonical = _aggregate_country_values(res_items)

        if block is not None and rec.world_production:
            prod_items = [
                (wp.country, wp.production_latest_year, wp.production_latest_raw)
                for wp in rec.world_production
            ]
            cap_items = [
                (wp.country, wp.capacity, None)
                for wp in rec.world_production
            ]
            prod_by_canonical = _aggregate_country_values(prod_items)
            capacity_by_canonical = _aggregate_country_values(cap_items)

        cat_rows = _category_rows_for(rec)
        annotate_name = len(cat_rows) > 1

        for cat in cat_rows:
            row: dict[str, str] = {}

            # Identity
            if annotate_name and cat and cat.category:
                row["name"] = f"{rec.name} ({cat.category})"
            else:
                row["name"] = rec.name
            row["kind"] = rec.kind
            row["source_url"] = rec.source_url
            row["units_note"] = _text(rec.units_note)
            row["price_unit_note"] = _text(rec.price_unit_note)
            row["import_sources_range"] = _text(rec.import_sources_range)
            row["world_production_label"] = _text(rec.world_production_label)
            row["import_category"] = (cat.category if cat and cat.category else "")

            # Summary
            row["usgs_2025_total_mined_production"] = _cell(
                rec.mined_production_latest,
                rec.latest_year_sentinels.get("mined_production"),
            )
            row["usgs_2025_total_primary_smelting"] = _cell(
                rec.primary_smelting_latest,
                rec.latest_year_sentinels.get("primary_smelting"),
            )
            row["usgs_2025_total_secondary_smelting"] = _cell(
                rec.secondary_smelting_latest,
                rec.latest_year_sentinels.get("secondary_smelting"),
            )
            row["imports_for_consumption_total"] = _val(rec.imports_total_latest)
            row["exports_total"] = _val(rec.exports_total_latest)
            row["consumption_apparent"] = _cell(
                rec.apparent_consumption_latest,
                rec.latest_year_sentinels.get("apparent_consumption"),
            )
            row["price_metal_average_dollars_per_pound"] = _val(rec.price_usd_per_pound_latest)
            row["net_import_reliance_pct"] = _cell(
                rec.net_import_reliance_pct_latest,
                rec.latest_year_sentinels.get("net_import_reliance"),
            )
            row["government_stockpile_fy2025_potential_acquisitions"] = _val(
                rec.stockpile_fy2025_potential_acquisitions
            )

            # Default every country cell to N/A across all 5 blocks.
            for cname in imports_cols:
                row[cname] = "N/A"
            for cname in mine_cols:
                row[cname] = "N/A"
            for cname in refinery_cols:
                row[cname] = "N/A"
            for cname in capacity_cols:
                row[cname] = "N/A"
            for cname in reserves_cols:
                row[cname] = "N/A"

            # Import Sources — varies per row (one category each).
            if cat is not None:
                imports_agg = _aggregate_country_values(
                    (cs.country, cs.share_pct, None) for cs in cat.countries
                )
                for canonical, (v, raw) in imports_agg.items():
                    # Multiple canonical entries can share a single name (China
                    # at priority position + China in Asia block). Write the
                    # value to every column whose canonical name matches.
                    for slug, name in zip(country_slugs, CANONICAL_COUNTRIES):
                        if name == canonical:
                            row[f"{slug}__imports_share_pct"] = _cell(v, raw)

            # Production / Capacity / Reserves — same across an element's rows.
            if block == "mine":
                for canonical, (v, raw) in prod_by_canonical.items():
                    for slug, name in zip(country_slugs, CANONICAL_COUNTRIES):
                        if name == canonical:
                            row[f"{slug}__mine_production"] = _cell(v, raw)
            elif block == "refinery":
                for canonical, (v, raw) in prod_by_canonical.items():
                    for slug, name in zip(country_slugs, CANONICAL_COUNTRIES):
                        if name == canonical:
                            row[f"{slug}__refinery_production"] = _cell(v, raw)
                for canonical, (v, raw) in capacity_by_canonical.items():
                    for slug, name in zip(country_slugs, CANONICAL_COUNTRIES):
                        if name == canonical:
                            row[f"{slug}__capacity"] = _cell(v, raw)

            # Reserves are populated for any element whose USGS table has
            # them — independent of the mine/refinery placement decision.
            for canonical, (v, raw) in reserves_by_canonical.items():
                for slug, name in zip(country_slugs, CANONICAL_COUNTRIES):
                    if name == canonical:
                        row[f"{slug}__reserves"] = _cell(v, raw)

            rows.append(row)

    return columns, rows


def write_csv(records: list[ElementRecord], out_path) -> None:
    columns, rows = build_rows(records)
    out_path.write_text(_render(columns, rows), encoding="utf-8")
    log.info("wrote csv -> %s (%d rows × %d cols)", out_path, len(rows), len(columns))


def _render(columns: list[str], rows: list[dict[str, str]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "N/A") for c in columns})
    return buf.getvalue()
