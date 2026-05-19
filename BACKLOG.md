# BACKLOG.md

Per CLAUDE.md §Backlog — ideas, follow-ups, and queued elements. Each item has a priority.

## Elements

### Done — primary MCS sheets

- [x] **Antimony** — multi-form imports/exports, world Mine Production + Reserves
- [x] **Bismuth** — single-form, world Refinery Production (byproduct of lead/zinc/tungsten)
- [x] **Diamond (industrial)** — covers natural + synthetic; powder grades not separately tabulated
- [x] **Gallium** — Low-Purity Production and Capacity
- [x] **Germanium** — Refinery Production (no per-country reserves in MCS 2026)
- [x] **Graphite (natural)** — three priced forms (flake / lump / amorphous)
- [x] **Indium** — Refinery Production and Capacity
- [x] **Lithium** — US production W (withheld); world Mine Production and Reserves
- [x] **Molybdenum** — Mine Production and Reserves
- [x] **Rare Earths (grouped)** — 9 per-oxide price quotes; multi-row NIR (compounds vs concentrates)
- [x] **Scandium** — short sheet, no production table; 3 priced grades; NIR=100%
- [x] **Tellurium** — Refinery Production and Capacity
- [x] **Tungsten** — multi-form, multiple W cells, NIR ">50"
- [x] **Abrasives (manufactured)** — closest analog for "superhard materials"

### Done — alias / sub-product views

These records reference a primary's PDF (`parent_slug`) and either filter to a
specific price quote (`parent_filter`) or inherit the parent's aggregates:

- [x] **Diamond powders** ← diamond
- [x] **Gallium nitride** ← gallium
- [x] **Graphite anodes** ← graphite
- [x] **Lithium batteries** ← lithium
- [x] **Superhard materials** ← abrasives
- [x] **Europium / Gadolinium / Samarium** ← rare-earths (matched to their oxide price quote)
- [x] **Dysprosium / Erbium / Holmium / Lutetium / Terbium / Thulium / Ytterbium / Yttrium** ← rare-earths
      (no individual price in MCS 2026 — numeric fields are "Not available", parent's narrative + world rows still surface)

### Queued — additional commodities (USGS 2022 critical minerals list)

Standard MCS sheets exist for the rest of the list; adding any of these is a
one-line entry to `ELEMENTS` in [src/config.py](src/config.py):

- [ ] Aluminum, Arsenic, Barite, Beryllium, Cesium, Chromium, Cobalt,
      Fluorspar, Hafnium, Iridium, Magnesium, Manganese, Nickel, Niobium,
      Palladium, Platinum, Rhodium, Rubidium, Ruthenium, Tantalum, Titanium,
      Vanadium, Zinc, Zirconium
- [ ] Lanthanum / Cerium / Praseodymium / Neodymium / Mischmetal as REE
      aliases against rare-earths (matched on their oxide price quotes)
- [ ] Standalone elements that USGS does NOT cover in MCS but the user may
      want: lithium-iron-phosphate batteries, neodymium magnets, silicon
      carbide micro-grit, polycrystalline diamond compact bits.

## Parser & data-model enhancements

- [ ] **Mine production vs refinery production normalization** (medium) — current schema has both `production_prev_year` and `production_latest_year` regardless of label; viewer shows the section's label verbatim. When we add elements whose world table is "Mine Production and Reserves" (most of them), `reserves` will populate where it's null for bismuth — confirm the column-kinds inference picks "reserves" up.
- [ ] **Yearbook integration** (medium) — pull historical Minerals Yearbook chapters for longer time series than the 5-year MCS window. Source: https://www.usgs.gov/centers/national-minerals-information-center/minerals-yearbook-metals-and-minerals
- [ ] **Per-element parser overrides** (low) — keep a `src/parsers/<slug>.py` registry hook for elements where the generic state machine misreads. (Not needed for bismuth.)
- [ ] **Diff alerts** (medium) — when re-running with `--refresh`, compare new SHA-256 to the stored value and surface "USGS reissued this PDF" warnings.
- [ ] **Multi-edition history** (low) — keep `data/processed/elements_<edition>.json` so we can chart year-over-year drift in reported figures.

## Viewer enhancements

- [ ] **Sort / filter** the overview table (medium) — click a column header to sort; chip filters for "REE only", "PGM only", "Critical 2022 list".
- [ ] **Sparkline cells** (low) — add a tiny inline 5-year line for each numeric column.
- [ ] **CSV export** (medium) — "Download as CSV" for the overview table.
- [ ] **Bookmarkable detail URLs** (low) — `?element=bismuth` opens straight to that element's detail card.
- [ ] **Mobile bottom sheet for detail** (low) — per DESIGN.md §7, swap the inline detail card for a bottom sheet at <640px.

## Audit module enhancements

- [ ] **Bounding-box overlays** (medium) — for each extracted numeric value, draw a red box over its source coordinates on the page PNG. Catches "we read a footnote as a value" bugs.
- [ ] **Diff report** (medium) — when re-running, write a Markdown diff vs. the prior JSON so changes are obvious.

## Infrastructure

- [ ] **GitHub Pages deploy** (medium) — once a stable set of elements is in, publish `viewer/` + a baked `data.json` snapshot.
- [ ] **CI** (low) — run `python -m unittest tests` on push; cache the bismuth PDF as a test fixture.
