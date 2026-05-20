"""Audit module: PNG screenshots of every PDF page + a written audit report.

The goal is to let a human verify the extracted JSON against the original.
We render at 2x DPI so footnotes and small numerals are legible. The audit
report lists every value the user asked about and (for the salient stats)
prints them next to a literal snippet of the PDF text so divergences are
obvious at a glance.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

import fitz

from . import config
from .models import ElementRecord

log = logging.getLogger(__name__)

RENDER_ZOOM = 2.0  # 2x => ~144 dpi at default; readable but small file size


def render_pages(pdf_path: Path, out_dir: Path) -> list[Path]:
    """Render every page of `pdf_path` as a PNG into `out_dir`.

    Returns the list of generated PNG paths (in page order).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix = fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM)
    paths: list[Path] = []
    doc = fitz.open(pdf_path)
    try:
        for page_idx, page in enumerate(doc):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            out = out_dir / f"page-{page_idx + 1:02d}.png"
            pix.save(out)
            paths.append(out)
            log.info("rendered %s", out.name)
    finally:
        doc.close()
    return paths


def write_audit_report(record: ElementRecord, out_path: Path) -> None:
    """Write a human-readable Markdown audit report for one element."""
    lines: list[str] = []
    lines.append(f"# Audit — {record.name} ({record.slug})")
    lines.append("")
    lines.append(f"- **Source**: <{record.source_url}>")
    lines.append(f"- **Edition**: {record.edition} ({record.edition_date})")
    lines.append(f"- **Captured**: {record.captured_at}")
    lines.append(f"- **PDF SHA-256**: `{record.pdf_sha256[:16]}…`")
    lines.append(f"- **Pages**: {record.pdf_page_count}")
    lines.append(f"- **Units note (verbatim)**: {record.units_note}")
    lines.append("")

    lines.append("## Latest-year US summary")
    lines.append("")
    lines.append("| field | value |")
    lines.append("| --- | --- |")
    rows = [
        ("Mined production (US)", record.mined_production_latest),
        ("Primary smelting / refinery (US)", record.primary_smelting_latest),
        ("Secondary smelting / scrap (US)", record.secondary_smelting_latest),
        ("Imports for consumption (total)", record.imports_total_latest),
        ("Exports (total)", record.exports_total_latest),
        ("Apparent consumption", record.apparent_consumption_latest),
        ("Price, $ per pound", record.price_usd_per_pound_latest),
        ("Net import reliance (% of apparent consumption)", record.net_import_reliance_pct_latest),
    ]
    for label, value in rows:
        lines.append(f"| {label} | {_fmt(value)} |")
    lines.append("")

    lines.append("## Salient Statistics (US) — full table")
    lines.append("")
    lines.append("_`2025e` = 2025 USGS estimate (preliminary); 2021–2024 are reported actuals._")
    lines.append("")
    header = "| Row | Footnote | 2021 | 2022 | 2023 | 2024 | 2025e |"
    sep = "| --- | --- | ---: | ---: | ---: | ---: | ---: |"
    lines.append(header)
    lines.append(sep)
    for row in record.salient_stats:
        cells = [_fmt_cell(row.values.get(y), (row.raw_values or {}).get(y))
                 for y in ("2021", "2022", "2023", "2024", "2025e")]
        fn = row.footnote or ""
        lines.append(f"| {row.label} | {fn} | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append(f"## Import Sources ({record.import_sources_range or 'n/a'})")
    lines.append("")
    if record.import_sources_by_category:
        for cat in record.import_sources_by_category:
            heading = cat.category or "(all)"
            lines.append(f"**{heading}**")
            for cs in cat.countries:
                lines.append(f"- {cs.country}: {_fmt(cs.share_pct)}%")
            lines.append("")
    else:
        lines.append("_Not reported._")
        lines.append("")

    lines.append(f"## {record.world_production_label or 'World production'}")
    lines.append("")
    if record.world_production:
        lines.append("| country | prev-yr | latest-yr | capacity | reserves | note |")
        lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
        for r in record.world_production:
            lines.append(
                f"| {r.country} | {_fmt_cell(r.production_prev_year, r.production_prev_raw)} | "
                f"{_fmt_cell(r.production_latest_year, r.production_latest_raw)} | "
                f"{_fmt(r.capacity)} | "
                f"{_fmt_cell(r.reserves, r.reserves_raw)} | {r.note or ''} |"
            )
    else:
        lines.append("_Not reported._")
    lines.append("")

    if record.footnotes:
        lines.append("## Footnotes (verbatim)")
        lines.append("")
        for k in sorted(record.footnotes.keys(), key=lambda s: int(s) if s.isdigit() else 999):
            lines.append(f"- **{k}**: {record.footnotes[k]}")
        lines.append("")

    lines.append("## Source page screenshots")
    lines.append("")
    for page_idx in range(1, record.pdf_page_count + 1):
        rel = f"page-{page_idx:02d}.png"
        lines.append(f"### Page {page_idx}")
        lines.append("")
        lines.append(f"![{record.name} page {page_idx}]({rel})")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote audit report -> %s", out_path)


def _fmt(value) -> str:
    """Pretty-format a numeric/optional value for Markdown.

    Per user instruction: missing data renders as "N/A" — never blank, never
    a substituted/fake value.
    """
    if value is None:
        return "N/A"
    if isinstance(value, float):
        # show ints as ints; keep 2 dp for fractional
        if value.is_integer():
            return f"{int(value):,}"
        return f"{value:,.2f}"
    return str(value)


def _fmt_cell(value, raw) -> str:
    """Format a cell, preferring the verbatim raw token when it carries a sentinel.

    USGS sheets use a few sentinels — `W` (withheld), `E` (net exporter), `>N`
    / `<N` (approximate bounds) — that lose meaning if we render only the
    coerced float. When `raw` carries one of these, show the raw form;
    otherwise fall back to the formatted numeric value.
    """
    if raw and (raw in {"W", "E", "NA"} or raw.startswith((">", "<"))):
        return raw
    return _fmt(value)


def audit_element(record: ElementRecord) -> Path:
    """Render screenshots and write the report. Returns the audit directory."""
    config.ensure_dirs()
    out_dir = config.AUDIT_DIR / record.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # Find the cached source PDF
    pdf_name = Path(record.source_url).name
    pdf_path = config.RAW_DIR / pdf_name
    if not pdf_path.exists():
        raise FileNotFoundError(f"expected cached PDF at {pdf_path}; run fetcher first")

    render_pages(pdf_path, out_dir)
    report_path = out_dir / "audit.md"
    write_audit_report(record, report_path)

    # Also drop the JSON next to the audit for convenience
    (out_dir / "data.json").write_text(
        json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_dir
