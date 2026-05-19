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

from . import audit, config, csv_export, parser
from .models import ElementBundle, ElementRecord, PriceQuote, YearSeries, YEAR_COLUMNS

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
    if do_audit:
        audit.audit_element(record)
    return record


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

        if alias.parent_filter:
            pat = re.compile(alias.parent_filter, re.IGNORECASE)
            matching_quote: PriceQuote | None = None
            for pq in parent.price_quotes:
                if pat.search(pq.form):
                    matching_quote = pq
                    break

            if matching_quote:
                rec.price_usd_per_pound_latest = matching_quote.values.get(parent.latest_year)
                rec.price_unit_note = matching_quote.form
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
    # grouped + sub_product: inherit parent verbatim (no extra work).
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
