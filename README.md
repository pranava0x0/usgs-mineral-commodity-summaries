# USGS Mineral Commodity Summaries — easier viewing tool

> **Source data is public domain, published by the U.S. Geological Survey.**
> This repository is a *viewing tool* — it downloads the official MCS PDFs,
> extracts the salient statistics tables, and presents them in a sortable
> table with source-page screenshots inline. No data is invented here; every
> value links back to the page of the PDF it came from.
>
> Live viewer: <https://pranava0x0.github.io/usgs-mineral-commodity-summaries/>
> (deployed by [.github/workflows/deploy-pages.yml](.github/workflows/deploy-pages.yml))

Currently covered (MCS 2026 edition):

- **Primary sheets (`kind="primary"`)** — own MCS PDF: Abrasives (manufactured),
  Aluminum, Antimony, Bismuth, Chromium, Cobalt, Copper, Diamond (industrial),
  Gallium, Germanium, Graphite (natural), Indium, Lithium, Magnesium, Manganese,
  Molybdenum, Nickel, Niobium, Platinum-group metals (grouped), Rare Earths
  (grouped), Rhenium, Scandium, Silicon, Silver, Tantalum, Tellurium, Tin,
  Titanium, Tungsten, Vanadium, Zinc, Zirconium-and-hafnium (grouped).
- **Rare-earth aliases (`kind="rare_earth"`)** — derived from the rare-earths
  grouped sheet: Cerium, Lanthanum, Neodymium, Praseodymium, Samarium,
  Europium, Gadolinium (each matched to its oxide price quote). Heavy REEs
  Dysprosium, Erbium, Holmium, Lutetium, Terbium, Thulium, Ytterbium, Yttrium
  carry parent provenance with "Not available" where MCS 2026 doesn't
  separately price them.
- **Grouped-sheet aliases (`kind="grouped"`)** — members of a grouped parent
  sheet: Iridium, Palladium, Platinum, … (← platinum-group-metals); Hafnium,
  Zirconium (← zirconium-and-hafnium). Each carries only its own mineral's
  figures where USGS breaks them out (e.g. zirconium owns the zircon world
  table; hafnium imports 84 vs the combined 18,294); the parent holds the sum.
- **Sub-product aliases (`kind="sub_product"`)** — downstream products or
  per-material splits derived from a parent sheet: Diamond powders, Gallium
  nitride, Graphite anodes, Lithium batteries (single-mineral downstream
  products — numeric fields N/A); Fused aluminum oxide, Silicon carbide,
  Metallic abrasives, Superhard materials (← abrasives); Iron and Steel (Pig
  iron / Raw steel); Titanium (sponge/metal) and Titanium (dioxide). Group
  parents collapse to a bare sum row and each member carries its own figures.

Each record's `kind` field surfaces this taxonomy so the viewer / CSV can
filter by category (e.g. "REE only", "PGM only"). See
[src/config.py](src/config.py) `ElementKind` for the full definition.

Next up: see [BACKLOG.md](BACKLOG.md).

## What you get

For each element:

- US salient statistics across 2021 – 2025 (Refinery, Secondary, Imports, Exports,
  Apparent consumption, Reported consumption, Price `$/lb`, Stocks, Net import
  reliance %), with footnote markers preserved.
- Import sources by country (with the date range USGS aggregated over).
- World refinery / mine production and reserves table.
- Verbatim prose blocks: Domestic Production & Use, Events Trends & Issues,
  World Resources, Substitutes, Recycling.
- All numbered footnotes captured verbatim.
- The exact units note from the PDF subtitle ("Data in metric tons unless
  otherwise specified") — copied as a string, never normalized away.
- The source URL (the "traceback URL"), the PDF SHA-256, and the capture date
  on every record.

## Quick start

```bash
# 1. Run the extractor — downloads the PDF (cached after first run) and writes
#    data/processed/elements.json + viewer/data.json
python3 -m src.pipeline bismuth --audit

# 2. Run the regression test
python3 -m unittest tests.test_bismuth -v

# 3. Open the viewer
python3 serve.py            # static server on http://127.0.0.1:8765/
```

The viewer reads `viewer/data.json`. Page screenshots used for audit / visual
verification live under `data/audit/<slug>/page-NN.png`.

## CLI

```
python -m src.pipeline                # parse every registered element
python -m src.pipeline bismuth        # one element by slug
python -m src.pipeline --refresh      # ignore the cached PDF, re-download
python -m src.pipeline --audit        # also render page screenshots + audit.md
```

## Adding an element

Two steps:

1. Add an entry to `ELEMENTS` in [src/config.py](src/config.py) — slug, name,
   periodic-table symbol if any, and the MCS PDF URL.
2. `python -m src.pipeline <slug> --audit` and open
   `data/audit/<slug>/audit.md` to verify the extracted values against the
   page screenshots side-by-side.

The parser is generic over the standard MCS sheet shape; most elements should
work without code changes. If a sheet uses an unusual layout, log the issue in
[issues.md](issues.md) and add a per-element override.

## Deploy & data refresh

Two workflows under `.github/workflows/`:

| Workflow            | Trigger                  | What it does                                                                   |
| ------------------- | ------------------------ | ------------------------------------------------------------------------------ |
| `deploy-pages.yml`  | every push to `main`     | Tests + sanity-check + bundle the **committed** `viewer/` and `data/`. No network. |
| `refresh-data.yml`  | manual dispatch only     | Re-runs the extraction pipeline against USGS and commits any data deltas back. |

This split keeps deploys fast (~10s build + ~8s deploy) and removes the failure
mode where a USGS URL change took down the live site. To refresh from upstream:
Actions tab → **Refresh data from USGS** → *Run workflow*. Inputs let you scope
to a single slug, skip the audit screenshots, or force a re-download.

**Author flow when editing the parser:**
1. Edit `src/`.
2. `python -m src.pipeline --audit` (regenerates `data/processed/`, `viewer/data.*`, `data/audit/`).
3. Commit code AND the regenerated data together. The deploy ships exactly what's committed.

## Repo layout

```
src/
  config.py     # element registry, paths, edition pin
  models.py     # Pydantic models — ElementRecord is the canonical shape
  fetcher.py    # cached, rate-limited PDF download
  extractor.py  # PyMuPDF text + superscript-aware footnote extraction
  parser.py     # state-machine parser; bbox-based world-table parsing
  audit.py      # PNG page renders + audit.md report
  pipeline.py   # CLI entry
tests/
  test_bismuth.py
viewer/
  index.html style.css viewer.js data.json
data/
  raw/         # downloaded PDFs (idempotent cache)
  processed/   # elements.json (canonical output)
  audit/       # per-element screenshots + audit.md + data.json mirror
```

## Notes on the data

- **Units are not normalized.** Whatever the MCS sheet says ("metric tons",
  "kilograms", "thousand carats", ...) is carried verbatim in `units_note`.
  Numeric fields are in those units. Prices are typically `$/lb` for metals,
  `$/kg` or `$/metric ton` for others — `price_unit_note` carries the exact label.
- **`—` is zero.** USGS uses an em-dash for zero / not produced; the parser
  emits `0.0`.
- **`NA` is `null`.** Distinguishes "USGS didn't report this" from "USGS
  reported a zero." The viewer renders nulls as *Not available* per
  [DESIGN.md §11](DESIGN.md).
- **`e` is the USGS estimated marker.** It applies to row labels and column
  headers; we don't treat it as a numbered footnote but `record.footnotes['e']`
  contains the definition the sheet provided.

## Source

> U.S. Geological Survey, *Mineral Commodity Summaries* (MCS) 2026, February 2026.
> National Minerals Information Center.

Bismuth sheet: <https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-bismuth.pdf>
