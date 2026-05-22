"""CLI entry point.

Usage:
    python -m src.pipeline                     # parse every registered element + aliases
    python -m src.pipeline bismuth antimony    # specific slugs
    python -m src.pipeline --refresh           # ignore the cached PDF
    python -m src.pipeline --audit             # also render screenshots + audit.md
    python -m src.pipeline --no-aliases        # skip the alias/sub-product records

Outputs:
    data/processed/elements.json   — canonical JSON
    data/processed/elements.csv    — wide one-row-per-element CSV
    viewer/data.json               — mirror for the static viewer
    data/audit/<slug>/             — PNG screenshots + audit.md (when --audit)
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

from . import audit, config, csv_export, parser
from .models import (
    ElementBundle,
    ElementRecord,
    PriceQuote,
    WorldProductionRow,
    YearSeries,
    YEAR_COLUMNS,
)

log = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


def _process_primary(slug: str, *, refresh: bool, do_audit: bool) -> ElementRecord:
    el = config.ELEMENTS[slug]
    if refresh:
        cached = config.RAW_DIR / Path(el.mcs_url).name
        if cached.exists():
            cached.unlink()
            log.info("removed cache: %s", cached.name)
    record = parser.parse_element_pdf(slug)
    _postprocess_record(record)
    if do_audit:
        audit.audit_element(record)
    return record


def _postprocess_record(rec: ElementRecord) -> None:
    """Apply per-element corrections that the generic parser can't infer.

    Keep this list short — every entry is a vote of no-confidence in the
    generic parser. Prefer fixing the parser when the pattern recurs.
    """
    if rec.slug == "iron-and-steel":
        # Generic `_find_row(salient, "Production", "mine")` doesn't match
        # the iron-and-steel salient's "Pig iron production" / "Raw steel
        # production" rows. Sum them into primary_smelting (per user spec
        # both rows are post-mine smelting; mined stays N/A).
        pig = _first_value(rec, "Pig iron production")
        raw = _first_value(rec, "Raw steel production")
        total = None
        if pig is not None or raw is not None:
            total = (pig or 0.0) + (raw or 0.0)
        rec.primary_smelting_latest = total
        rec.mined_production_latest = None

        # The World Production table splits into Pig iron + Raw steel
        # sub-columns. The parent represents the combined entity, so its
        # per-country refinery figure is the sum of the two sub-commodities
        # (consistent with the summary primary_smelting = pig + raw). The
        # sub-metal dict is left intact so the Pig iron / Raw steel aliases
        # can still pick out their individual per-country values.
        for wp in rec.world_production:
            sm = wp.sub_metal_production_latest
            if sm:
                vals = [v for v in sm.values() if v is not None]
                wp.production_latest_year = sum(vals) if vals else None

    if rec.slug == "titanium":
        # The "TITANIUM AND TITANIUM DIOXIDE" sheet stacks two independent
        # salient sub-tables (titanium sponge metal, then TiO2 pigment). The
        # generic summary blends them: imports/exports get SUMMED across both
        # commodities (44,000 sponge + 230,000 TiO2 = 274,000) while
        # consumption/price/NIR silently take only the first sub-table. Neither
        # commodity's figure is recoverable from the blend, so null the combined
        # summary on the parent — the real per-commodity numbers live on the
        # titanium-sponge-metal / titanium-dioxide sub-product rows.
        rec.mined_production_latest = None
        rec.primary_smelting_latest = None
        rec.secondary_smelting_latest = None
        rec.imports_total_latest = None
        rec.exports_total_latest = None
        rec.apparent_consumption_latest = None
        rec.price_usd_per_pound_latest = None
        rec.price_unit_note = None
        rec.net_import_reliance_pct_latest = None
        rec.latest_year_sentinels = {}

    if rec.slug == "rare-earths":
        # The rare-earths sheet quotes 9 separate REE-oxide prices in $/kg.
        # There is no single representative "rare earths price" — picking the
        # first row (Lanthanum oxide) misled the latest-year column. Surface
        # the full per-commodity quote table in the detail panel only.
        rec.price_usd_per_pound_latest = None
        rec.latest_year_sentinels.setdefault("price", "see Price section")
        # The "Net import reliance" figure (67%) is for *compounds and metals*;
        # the mineral-concentrates NIR is "E" (net exporter). Flag this so the
        # viewer can show context rather than a bare number.
        rec.latest_year_sentinels.setdefault(
            "net_import_reliance_basis", "compounds and metals"
        )


def _first_value(rec: ElementRecord, label_prefix: str) -> Optional[float]:
    """Latest-year value of the first salient row whose label starts with `label_prefix`."""
    pfx = label_prefix.lower()
    for row in rec.salient_stats:
        if row.label.lower().startswith(pfx):
            return row.values.get(rec.latest_year)
    return None


def _titanium_salient_groups(
    salient: list[YearSeries],
) -> tuple[list[YearSeries], list[YearSeries]]:
    """Split titanium's two stacked salient sub-tables (sponge metal, TiO2).

    The USGS sheet groups its salient rows under "Titanium sponge metal:" and
    "TiO2 pigment:" headers. The generic parser drops those group headers, but
    the two sub-tables are concatenated in source order and the second one
    restarts at "Production" — so the boundary is the first row whose section
    repeats one already seen. Returns (sponge_metal_rows, dioxide_rows); the
    second list is empty if no boundary is found (defensive — keeps callers
    from blowing up if a future edition collapses the two tables).
    """
    seen: set[str] = set()
    boundary: Optional[int] = None
    for idx, row in enumerate(salient):
        key = (row.section or row.label or "").strip().lower()
        if key and key in seen:
            boundary = idx
            break
        seen.add(key)
    if boundary is None:
        return list(salient), []
    return list(salient[:boundary]), list(salient[boundary:])


def _fill_titanium_group_summary(
    rec: ElementRecord, rows: list[YearSeries], latest_year: str
) -> None:
    """Populate an alias's summary from ONE of titanium's salient sub-tables.

    Reuses the parser's section-scoped extractors on the row subset so each
    commodity's figures match how the parser would read a standalone sheet.
    Titanium production (sponge reduction / TiO2 pigment manufacture) is
    post-mine processing, so it lands in `primary_smelting_latest` — the same
    column iron-and-steel uses for its pig-iron / raw-steel output.
    """
    prod_row = parser._find_row(rows, "production", "production")
    imports_total, _ = parser._latest_value_by_section(rows, "imports", latest_year)
    exports_total, _ = parser._latest_value_by_section(rows, "exports", latest_year)
    cons_row = parser._find_row(rows, "consumption", "apparent")
    nir_row = parser._find_row(rows, "net import reliance", "net import reliance")
    price_row: Optional[YearSeries] = None
    for r in rows:
        if r.label.lower().startswith("price") and r.values.get(latest_year) is not None:
            price_row = r
            break

    rec.mined_production_latest = None
    rec.primary_smelting_latest = parser._latest_or_none(prod_row, latest_year)
    rec.secondary_smelting_latest = None
    rec.imports_total_latest = imports_total
    rec.exports_total_latest = exports_total
    rec.apparent_consumption_latest = parser._latest_or_none(cons_row, latest_year)
    rec.price_usd_per_pound_latest = parser._latest_or_none(price_row, latest_year)
    rec.price_unit_note = price_row.label if price_row else None
    rec.net_import_reliance_pct_latest = parser._latest_or_none(nir_row, latest_year)
    rec.stockpile_fy2025_potential_acquisitions = None

    # Preserve non-numeric sentinels (e.g. TiO2's NIR = "E" net exporter).
    sentinels: dict[str, str] = {}
    for key, row in (
        ("primary_smelting", prod_row),
        ("net_import_reliance", nir_row),
        ("apparent_consumption", cons_row),
    ):
        raw = (row.raw_values or {}).get(latest_year) if row else None
        if raw and (raw in {"W", "E"} or raw.startswith((">", "<"))):
            sentinels[key] = raw
    rec.latest_year_sentinels = sentinels


def _pgm_fill_per_metal_summary(
    rec: ElementRecord, parent: ElementRecord, metal_name: str
) -> None:
    """Fill alias summary fields from per-metal rows in the parent's salient stats.

    USGS lists each PGM metal as its own row under the Production / Imports /
    Exports / Apparent consumption / NIR sections of the parent's salient
    table. We pull the row whose label *equals* `metal_name` (case-insensitive)
    within each section's keyword space, then assign its latest-year value
    to the matching `*_latest` field on the alias.

    Fields explicitly *not* assigned:
      - `price_usd_per_pound_latest` — PGM prices are quoted in $/troy oz
        which doesn't match the column header's $/lb basis. Leaving at None
        is more honest than copying a unit-mismatched number.
      - `stockpile_fy2025_potential_acquisitions` — the parent's value is
        a group-level total; not attributable to a single metal. Null it.
      - `primary_smelting_latest`, `secondary_smelting_latest` — USGS
        doesn't break the smelter stages out per metal.

    Rows USGS doesn't publish for a given metal (e.g. Osmium has no
    consumption row) leave the corresponding field at None.
    """
    def _find_metal_row(predicate) -> Optional[YearSeries]:
        m = metal_name.lower()
        for row in parent.salient_stats:
            if not predicate(row):
                continue
            if row.label.strip().lower() == m:
                return row
        return None

    def _latest_v(row: Optional[YearSeries]) -> Optional[float]:
        return row.values.get(parent.latest_year) if row else None

    def _latest_raw(row: Optional[YearSeries]) -> Optional[str]:
        return (row.raw_values or {}).get(parent.latest_year) if row else None

    # Section predicates. PGM's Production section is tagged on the parser
    # side as subsection="Mine production" rather than section="Production"
    # (the parent PDF has "Mine production" as a column-style sub-header
    # under no explicit "Production:" line), so we accept either match.
    def _is_production(r) -> bool:
        return (
            (r.section or "").lower().startswith("production")
            or "production" in (r.subsection or "").lower()
        )

    prod_row = _find_metal_row(_is_production)
    imp_row = _find_metal_row(lambda r: (r.section or "").lower().startswith("imports"))
    exp_row = _find_metal_row(lambda r: (r.section or "").lower().startswith("exports"))
    cons_row = _find_metal_row(lambda r: (r.section or "").lower().startswith("consumption"))
    nir_row = _find_metal_row(lambda r: (r.section or "").lower().startswith("net import reliance"))

    rec.mined_production_latest = _latest_v(prod_row)
    rec.primary_smelting_latest = None
    rec.secondary_smelting_latest = None
    rec.imports_total_latest = _latest_v(imp_row)
    rec.exports_total_latest = _latest_v(exp_row)
    rec.apparent_consumption_latest = _latest_v(cons_row)
    rec.net_import_reliance_pct_latest = _latest_v(nir_row)
    rec.price_usd_per_pound_latest = None
    rec.price_unit_note = None

    # Drop the parent's group-level stockpile from the alias — it doesn't
    # break down per metal.
    rec.stockpile_fy2025_potential_acquisitions = None

    # Preserve any non-numeric markers (W / E / >N) on the alias for
    # the fields we re-populated.
    sentinels: dict[str, str] = {}
    for key, row in (
        ("mined_production", prod_row),
        ("net_import_reliance", nir_row),
        ("apparent_consumption", cons_row),
    ):
        raw = _latest_raw(row)
        if raw and (raw in {"W", "E"} or raw.startswith((">", "<"))):
            sentinels[key] = raw
    rec.latest_year_sentinels = sentinels


def _fill_group_member(
    rec: ElementRecord,
    parent: ElementRecord,
    keyword: str,
    *,
    production_field: str,
    keep_world: bool,
) -> None:
    """Fill a multi-mineral group member's record from the parent, by keyword.

    For the zirconium-and-hafnium and abrasives sheets, whose Salient Statistics
    break figures out per mineral/material. Keep only the parent salient rows
    whose label contains `keyword`, and recompute the summary from that subset
    (reusing the parser's section-scoped extractors). `production_field` routes
    the production value to `mined_` (mine sheets, e.g. zircon) vs `primary_`
    (manufactured, e.g. abrasives). `keep_world` keeps the parent's
    world-production table (zirconium owns the zircon table); otherwise it's
    blanked (the PDF has no per-material world table).
    """
    kw = keyword.lower()
    rows = [r for r in parent.salient_stats if kw in r.label.lower()]
    ly = parent.latest_year

    prod_row = parser._find_row(rows, "production", "production")
    if prod_row is None:
        prod_row = next(
            (
                r for r in rows
                if (r.section or "").lower().startswith("production")
                and not r.label.lower().startswith("shipments")
            ),
            None,
        )
    imports_total, _ = parser._latest_value_by_section(rows, "imports", ly)
    exports_total, _ = parser._latest_value_by_section(rows, "exports", ly)
    cons_row = (
        parser._find_row(rows, "consumption", "apparent")
        or parser._find_row(rows, "consumption", "consumption")
    )
    nir_row = parser._find_row(rows, "net import reliance", "net import reliance")
    price_row = next(
        (
            r for r in rows
            if (r.section or "").lower().startswith("price")
            and r.values.get(ly) is not None
        ),
        None,
    )

    rec.mined_production_latest = None
    rec.primary_smelting_latest = None
    rec.secondary_smelting_latest = None
    pv = parser._latest_or_none(prod_row, ly)
    if production_field == "mined":
        rec.mined_production_latest = pv
    else:
        rec.primary_smelting_latest = pv
    rec.imports_total_latest = imports_total
    rec.exports_total_latest = exports_total
    rec.apparent_consumption_latest = parser._latest_or_none(cons_row, ly)
    rec.price_usd_per_pound_latest = parser._latest_or_none(price_row, ly)
    if price_row:
        sec = price_row.section or ""
        rec.price_unit_note = sec if "dollar" in sec.lower() else price_row.label
    else:
        rec.price_unit_note = None
    rec.net_import_reliance_pct_latest = parser._latest_or_none(nir_row, ly)
    rec.stockpile_fy2025_potential_acquisitions = None
    rec.latest_year_sentinels = {}

    rec.salient_stats = list(rows)
    rec.price_quotes = [pq for pq in parent.price_quotes if kw in pq.form.lower()]
    rec.import_sources_by_category = [
        c for c in parent.import_sources_by_category
        if c.category and kw in c.category.lower()
    ]
    rec.import_sources_flat = []
    if not keep_world:
        rec.world_production = []


def _blank_aggregates(rec: ElementRecord) -> None:
    """Null out sheet-wide numeric fields on a derived record.

    Used when the parent sheet's aggregates (imports/exports/production/etc.)
    aren't applicable to the alias — e.g. a single heavy REE inheriting
    rare-earths totals that cover the entire group.
    """
    rec.mined_production_latest = None
    rec.primary_smelting_latest = None
    rec.secondary_smelting_latest = None
    rec.imports_total_latest = None
    rec.exports_total_latest = None
    rec.apparent_consumption_latest = None
    rec.net_import_reliance_pct_latest = None


def _make_alias(parent: ElementRecord, alias: config.Element) -> ElementRecord:
    """Derive an alias record from its parent.

    Branches on `alias.kind` — the source-shape taxonomy declared in
    src/config.py. Each kind corresponds to a distinct USGS PDF structure /
    inheritance pattern:

    * `rare_earth` — alias against the rare-earths grouped sheet. When
      `parent_filter` matches a per-element price quote (e.g. "Europium oxide"),
      we pull that price; otherwise we blank prices (so we don't misattribute
      lanthanum's price to dysprosium). Sheet-wide aggregates are always
      blanked because they cover the entire REE group, not this one element.

    * `grouped` — alias against a grouped multi-commodity sheet (PGMs,
      zirconium-and-hafnium). USGS reports data at the group level only, so
      members inherit the parent record verbatim. The viewer should make the
      "same data, just labeled differently" relationship visible via `kind`.

    * `sub_product` — downstream product (gallium nitride, graphite anodes,
      silicon carbide). The parent IS a single-commodity sheet whose figures
      apply to the sub-product, so inherit verbatim.
    """
    rec = ElementRecord(**parent.model_dump())
    rec.slug = alias.slug
    rec.name = alias.name
    rec.symbol = alias.symbol
    rec.kind = alias.kind
    rec.parent_slug = alias.parent_slug

    if alias.kind == "rare_earth":
        _blank_aggregates(rec)
        # USGS reports rare-earth mine production / reserves, import sources, and
        # the Government Stockpile only at the GROUP level (REO content / the
        # group's lanthanum stockpile). Per-element figures aren't published, so
        # don't let an individual REE inherit them — that would attribute the
        # whole group's 270,000 t China mine / 44,000,000 t reserves / 1,100 t
        # stockpile to one element.
        rec.world_production = []
        rec.import_sources_flat = []
        rec.import_sources_by_category = []
        rec.stockpile_fy2025_potential_acquisitions = None
        rec.latest_year_sentinels = {}

        if alias.parent_filter:
            pat = re.compile(alias.parent_filter, re.IGNORECASE)
            matching_quote: PriceQuote | None = None
            for pq in parent.price_quotes:
                if pat.search(pq.form):
                    matching_quote = pq
                    break

            if matching_quote:
                rec.price_usd_per_pound_latest = matching_quote.values.get(parent.latest_year)
                # Keep both the commodity form AND the parent's per-unit basis
                # (e.g. "$/kg"), otherwise the viewer loses the unit when it
                # shows the price-basis line on a per-element page.
                unit = matching_quote.unit_note or parent.price_unit_note
                rec.price_unit_note = (
                    f"{matching_quote.form} ({unit})" if unit else matching_quote.form
                )
                row = YearSeries(
                    label=matching_quote.form,
                    section="Price",
                    values=matching_quote.values,
                    raw_values=matching_quote.raw_values,
                )
                rec.salient_stats = [row]
                rec.price_quotes = [matching_quote]
            else:
                rec.price_usd_per_pound_latest = None
                rec.price_unit_note = None
                rec.price_quotes = []
                rec.salient_stats = []
        else:
            # Heavy REE without an individual price quote — null out price
            # fields so we don't falsely attribute another REE's value.
            rec.price_usd_per_pound_latest = None
            rec.price_unit_note = None
            rec.price_quotes = []
            rec.salient_stats = []

    elif alias.kind == "grouped" and alias.parent_slug == "platinum-group-metals":
        # PGM alias. The parent's salient_stats has per-metal rows under
        # each section (Production: Palladium / Platinum; Imports for
        # consumption: Palladium / Platinum / PGM waste / Iridium / Osmium
        # / Rhodium / Ruthenium; Exports: …; etc.). Pull this metal's row
        # into the alias's summary fields so per-metal CSV rows carry
        # per-metal values instead of the parent's group totals.
        #
        # `alias.name` is the metal display name (e.g. "Palladium",
        # "Iridium") — we match against the salient row label, restricted
        # by section keyword. Missing rows leave the field at the value
        # inherited from the parent (mostly the group total, which we
        # then explicitly null).
        metal_name = alias.name        # "Palladium" / "Iridium" / etc.
        _pgm_fill_per_metal_summary(rec, parent, metal_name)

        # World production + import sources: same per-metal filtering as
        # before. Pd / Pt have sub-column data; the others get blank rows.
        if alias.parent_filter:
            metal = alias.parent_filter
            new_rows: list[WorldProductionRow] = []
            for wp in parent.world_production:
                v = wp.sub_metal_production_latest.get(metal)
                new_rows.append(WorldProductionRow(
                    country=wp.country,
                    production_prev_year=None,
                    production_latest_year=v,
                    capacity=None,
                    reserves=None,            # PGM reserves stay on the parent
                    production_prev_raw=None,
                    production_latest_raw=None,
                    reserves_raw=None,
                    note=wp.note,
                    sub_metal_production_latest={},
                ))
            rec.world_production = new_rows
            rec.import_sources_by_category = [
                c for c in parent.import_sources_by_category
                if c.category and c.category.strip().lower() == metal.lower()
            ]
            rec.import_sources_flat = []
        else:
            rec.world_production = []
            rec.import_sources_by_category = []
            rec.import_sources_flat = []

    elif alias.kind == "sub_product" and alias.parent_slug == "titanium":
        # Titanium sub-products (sponge metal / TiO2 pigment). The parent's
        # salient_stats is two stacked sub-tables; split it and recompute this
        # commodity's full summary from its half only (NOT the blended parent).
        # Unlike iron-and-steel, each titanium sub-table is complete, so the
        # sub-rows carry imports/exports/consumption/price/NIR — not just
        # production. Titanium has no per-country world table, so all country
        # production/reserves blocks stay empty.
        want_sponge = (alias.parent_filter or "").lower() == "sponge"
        sponge_rows, dioxide_rows = _titanium_salient_groups(parent.salient_stats)
        group = sponge_rows if want_sponge else dioxide_rows
        _fill_titanium_group_summary(rec, group, parent.latest_year)

        # Keep only this commodity's salient rows + price quotes for the
        # detail panel.
        rec.salient_stats = list(group)
        group_price_forms = {
            r.label for r in group if r.label.lower().startswith("price")
        }
        rec.price_quotes = [
            pq for pq in parent.price_quotes if pq.form in group_price_forms
        ]

        # Import sources: keep only this commodity's category ("Sponge metal"
        # for sponge; "TiO pigment" for dioxide).
        want_keyword = "sponge" if want_sponge else "pigment"
        rec.import_sources_by_category = [
            c for c in parent.import_sources_by_category
            if c.category and want_keyword in c.category.lower()
        ]
        rec.import_sources_flat = []
        rec.world_production = []

    elif alias.parent_slug in ("zirconium-and-hafnium", "abrasives") and alias.parent_filter:
        # Multi-mineral group member (zirconium / hafnium; fused-aluminum-oxide
        # / silicon-carbide / metallic-abrasives). The sheet breaks Salient
        # Statistics out per mineral, so keep only this mineral's rows + import
        # categories and recompute the summary from them. zirconium owns the
        # zircon World Mine Production and Reserves table; the rest get world
        # N/A. The parent collapses to a bare sum row (see csv_export).
        production_field = "mined" if alias.parent_slug == "zirconium-and-hafnium" else "primary"
        _fill_group_member(
            rec, parent, alias.parent_filter,
            production_field=production_field,
            keep_world=alias.inherits_world_table,
        )

    elif alias.kind == "sub_product" and alias.parent_filter:
        # Iron-and-steel sub-products (Pig iron / Raw steel). Per user spec
        # (2026-05-19), these rows carry ONLY the production total for the
        # latest year + per-country production (refinery block). All other
        # summary + per-country fields blank out.
        #
        # The US production total comes from the parent's salient row
        # ("Pig iron production" = 21 / "Raw steel production" = 82). The
        # per-country breakdown comes from the parent's World Production
        # table, which splits into "Pig iron" / "Raw steel" sub-columns
        # (captured as WorldProductionRow.sub_metal_production_latest) —
        # so Pig iron and Raw steel rows show DIFFERENT per-country figures
        # (e.g. China pig iron 830 vs raw steel 980).
        pat = re.compile(alias.parent_filter, re.IGNORECASE)
        v: Optional[float] = None
        for row in parent.salient_stats:
            if pat.search(row.label):
                v = row.values.get(parent.latest_year)
                break

        # Reset every summary field except primary_smelting.
        rec.mined_production_latest = None
        rec.primary_smelting_latest = v
        rec.secondary_smelting_latest = None
        rec.imports_total_latest = None
        rec.exports_total_latest = None
        rec.apparent_consumption_latest = None
        rec.price_usd_per_pound_latest = None
        rec.price_unit_note = None
        rec.net_import_reliance_pct_latest = None
        rec.stockpile_fy2025_potential_acquisitions = None
        rec.latest_year_sentinels = {}
        rec.import_sources_flat = []
        rec.import_sources_by_category = []

        # Rewrite world_production so the refinery block shows THIS
        # sub-commodity's per-country values (not the parent's combined /
        # first-column figure). Match the sub-metal key case-insensitively
        # against the alias's parent_filter.
        metal_key = alias.parent_filter.lower()
        new_rows: list[WorldProductionRow] = []
        for wp in parent.world_production:
            cv: Optional[float] = None
            for k, val in wp.sub_metal_production_latest.items():
                if k.lower() == metal_key:
                    cv = val
                    break
            new_rows.append(WorldProductionRow(
                country=wp.country,
                production_prev_year=None,
                production_latest_year=cv,
                capacity=None,
                reserves=None,
                production_prev_raw=None,
                production_latest_raw=None,
                reserves_raw=None,
                note=wp.note,
                sub_metal_production_latest={},
            ))
        rec.world_production = new_rows

    else:
        # No per-mineral / per-product data in the PDF: superhard-materials
        # (abrasives proxy) and the single-mineral downstream products
        # (diamond-powders / gallium-nitride / graphite-anodes /
        # lithium-batteries). Inherit prose + identity only; blank every numeric
        # field + world table + import sources so the row never presents the
        # parent's figures as if they were its own.
        _blank_aggregates(rec)
        rec.price_usd_per_pound_latest = None
        rec.price_unit_note = None
        rec.price_quotes = []
        rec.salient_stats = []
        rec.world_production = []
        rec.import_sources_flat = []
        rec.import_sources_by_category = []
        rec.stockpile_fy2025_potential_acquisitions = None
        rec.latest_year_sentinels = {}

    return rec


def _write_bundle(records: list[ElementRecord]) -> tuple[Path, Path]:
    config.ensure_dirs()
    bundle = ElementBundle(
        edition=config.MCS_EDITION,
        generated_at=_dt.datetime.now().isoformat(timespec="seconds"),
        elements=records,
    )
    out_json = config.PROCESSED_DIR / "elements.json"
    out_json.write_text(
        json.dumps(bundle.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    out_csv = config.PROCESSED_DIR / "elements.csv"
    csv_export.write_csv(records, out_csv)

    # Mirror into the viewer for static loading
    viewer_data = config.VIEWER_DIR / "data.json"
    config.VIEWER_DIR.mkdir(parents=True, exist_ok=True)
    viewer_data.write_text(out_json.read_text(encoding="utf-8"), encoding="utf-8")
    viewer_csv = config.VIEWER_DIR / "data.csv"
    viewer_csv.write_text(out_csv.read_text(encoding="utf-8"), encoding="utf-8")

    log.info("wrote %s, %s, and %s", out_json, out_csv, viewer_data)
    return out_json, out_csv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Parse USGS MCS PDFs into structured data.")
    ap.add_argument("elements", nargs="*", help="Element slugs to parse. Default: all registered.")
    ap.add_argument("--refresh", action="store_true", help="Ignore cached PDF.")
    ap.add_argument("--audit", action="store_true", help="Render page screenshots and audit.md.")
    ap.add_argument("--no-bundle", action="store_true", help="Skip writing the combined elements.json.")
    ap.add_argument("--no-aliases", action="store_true", help="Skip the alias / sub-product records.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    configure_logging(args.verbose)
    config.ensure_dirs()

    all_known = config.all_known()
    if args.elements:
        unknown = [s for s in args.elements if s not in all_known]
        if unknown:
            ap.error(f"unknown slugs: {unknown}; known={sorted(all_known)}")
        requested = list(args.elements)
    else:
        # Default: every primary element, then every alias.
        requested = list(config.ELEMENTS.keys())
        if not args.no_aliases:
            requested += list(config.ALIASES.keys())

    primary_records: dict[str, ElementRecord] = {}
    failures: list[tuple[str, str]] = []

    # First pass: parse every primary that is needed.
    needed_primaries: list[str] = []
    for slug in requested:
        el = all_known[slug]
        if el.parent_slug is None:
            if slug not in needed_primaries:
                needed_primaries.append(slug)
        else:
            if el.parent_slug not in needed_primaries:
                needed_primaries.append(el.parent_slug)
            if not args.no_aliases:
                pass  # alias will be made in the second pass

    for slug in needed_primaries:
        try:
            primary_records[slug] = _process_primary(slug, refresh=args.refresh, do_audit=args.audit)
        except Exception as exc:
            log.exception("FAILED on %s", slug)
            failures.append((slug, str(exc)))

    # Second pass: emit aliases (and direct primaries) in the user's order.
    out_records: list[ElementRecord] = []
    for slug in requested:
        el = all_known[slug]
        if el.parent_slug is None:
            rec = primary_records.get(slug)
            if rec is not None:
                out_records.append(rec)
        else:
            parent = primary_records.get(el.parent_slug)
            if parent is None:
                log.warning("alias %s: parent %s missing — skipping", slug, el.parent_slug)
                continue
            out_records.append(_make_alias(parent, el))

    if out_records and not args.no_bundle:
        _write_bundle(out_records)

    if failures:
        log.error("completed with %d failures: %s", len(failures), [s for s, _ in failures])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
