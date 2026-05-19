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
specific price quote (`parent_filter`) or inherit the parent's aggregates. The
`kind` field selects the derivation branch in `pipeline._make_alias`:

- [x] **Sub-products (kind="sub_product")**: Diamond powders ← diamond;
      Gallium nitride ← gallium; Graphite anodes ← graphite; Lithium batteries
      ← lithium; Silicon carbide ← abrasives; Superhard materials ← abrasives
- [x] **REE with per-oxide price (kind="rare_earth")**: Cerium, Europium,
      Gadolinium, Lanthanum, Neodymium, Praseodymium, Samarium ← rare-earths
      (matched to oxide price quote via `parent_filter`)
- [x] **REE without individual price (kind="rare_earth")**: Dysprosium, Erbium,
      Holmium, Lutetium, Terbium, Thulium, Ytterbium, Yttrium ← rare-earths
      (no individual price in MCS 2026 — numeric fields blanked; parent's
      narrative + world rows still accessible via parent record)
- [x] **Grouped-sheet members (kind="grouped")**: Iridium, Platinum ←
      platinum-group-metals; Hafnium, Zirconium ← zirconium-and-hafnium
      (verbatim inherit — USGS only reports at the group level)

### Done — primary additions (MCS 2026)

- [x] **Aluminum, Chromium, Cobalt, Copper, Magnesium, Manganese, Nickel,
      Niobium, Rhenium, Silicon, Silver, Tantalum, Tin, Titanium, Vanadium,
      Zinc** — single-element MCS sheets
- [x] **Platinum-group-metals** — grouped parent for Ir/Pt aliases
- [x] **Zirconium-and-hafnium** — grouped parent for Zr/Hf aliases

### Queued — additional commodities (USGS 2022 critical minerals list)

Standard MCS sheets exist for the rest of the list; adding any of these is a
one-line entry to `ELEMENTS` in [src/config.py](src/config.py):

- [ ] Arsenic, Barite, Beryllium, Cesium, Fluorspar, Palladium, Rhodium,
      Rubidium, Ruthenium
- [ ] Sodium — no single MCS sheet; would need salt + soda-ash + sodium-sulfate
      as separate primaries
- [ ] Mischmetal as REE alias against rare-earths (Mischmetal price quote exists)
- [ ] Standalone elements that USGS does NOT cover in MCS but the user may
      want: lithium-iron-phosphate batteries, neodymium magnets, silicon
      carbide micro-grit, polycrystalline diamond compact bits.

## Parser & data-model enhancements

- [ ] **Mine production vs refinery production normalization** (medium) — current schema has both `production_prev_year` and `production_latest_year` regardless of label; viewer shows the section's label verbatim. When we add elements whose world table is "Mine Production and Reserves" (most of them), `reserves` will populate where it's null for bismuth — confirm the column-kinds inference picks "reserves" up.
- [ ] **Yearbook integration** (medium) — pull historical Minerals Yearbook chapters for longer time series than the 5-year MCS window. Source: https://www.usgs.gov/centers/national-minerals-information-center/minerals-yearbook-metals-and-minerals
- [ ] **Per-element parser overrides** (low) — keep a `src/parsers/<slug>.py` registry hook for elements where the generic state machine misreads. (Not needed for bismuth.)
- [ ] **Diff alerts** (medium) — when re-running with `--refresh`, compare new SHA-256 to the stored value and surface "USGS reissued this PDF" warnings.
- [ ] **Multi-edition history** (low) — keep `data/processed/elements_<edition>.json` so we can chart year-over-year drift in reported figures.

## Rare-earths sheet — accuracy gaps (2026-05-19 audit)

The rare-earths sheet has a *structurally* different layout from the typical
single-commodity MCS sheet (antimony, bismuth, etc.). The generic parser
handles most of it correctly, but the differences below surface gaps where
information is silently dropped. See also AGENTS.md for the comparison
table.

### Structural differences vs. critical-mineral sheets
- **Title carries a superscript** — `RARE EARTHS¹` (footnote 1 explains
  "Data include lanthanides and yttrium but exclude most scandium"). All
  primary sheets except rare-earths use a bare title.
- **Units delimiter is `[ … ]`** — every other sheet uses `( … )`.
- **Two production rows**, not one — `Mineral concentrates²` (REO content
  of mined bastnaesite/monazite) AND `Compounds and metalsᵉ,³` (refined
  product). Antimony has `Mine` + `Smelter: Primary` + `Smelter: Secondary`.
- **Three-level salient-stats nesting** — `Imports:` → `Metals:` →
  `Ferrocerium, alloys` / `Rare-earth metals and alloys`. Most sheets
  only have two levels (section → row).
- **Multi-row Price section** — 9 different priced commodities
  (lanthanum oxide, cerium oxide, NdPr oxide, etc.), each in $/kg. Most
  sheets have a single Price row.
- **Multi-row NIR section** — `Compounds and metals` (>95/>95/>90/53/67)
  AND `Mineral concentrates` (E/E/E/E/E). Most sheets have a single
  NIR row.
- **Section-level footnotes** — `Production:ᵉ`, `Imports:ᵉ,⁴`,
  `Exports:ᵉ,⁴`, `Net import reliance⁷` carry footnote markers on the
  *section header* rather than on individual rows.
- **Multiple inline footnote markers per row** — `Compounds and metalsᵉ,³`
  has both an estimation marker (`e`) and a numeric reference (`3`). Most
  rows carry at most one numeric footnote.
- **Trailing prose after Import Sources percentages** — the sheet runs
  `"…other, 6%. Compounds and metals imported from Estonia, Japan, and
  Malaysia were derived from mineral concentrates…"`. Most sheets terminate
  the import-sources line at the last `%.`.

### Known issues — file each one separately

- [ ] **#R1 Multi-superscript row labels lose all but the last footnote** (medium) —
      Salient-stats row `Compounds and metals` (Production section) shows
      `footnote=None`; the PDF marks it `Compounds and metalsᵉ,³`. The "3"
      footnote ("Production includes compounds from California and Utah.
      Data are rounded to two significant digits.") is lost. Likely fix:
      collect ALL trailing superscripts in `TextLine`, not just the last
      one; promote the numeric ones into `YearSeries.footnote` as a list.
- [ ] **#R2 Section-level footnote markers are dropped** (medium) —
      `Production:ᵉ`, `Imports:ᵉ,⁴`, `Exports:ᵉ,⁴`, `Net import reliance⁷
      as a percentage of apparent consumption:` all carry footnote markers
      that don't survive parsing. Currently the section appears under
      `YearSeries.section` as just `"Production"` / `"Imports"` etc. Likely
      fix: add `section_footnote` / `section_footnotes_list` fields on
      `YearSeries`, or store the section metadata once per record.
- [ ] **#R3 Tariff section is parsed but discarded** (medium) —
      `SECTION_STARTS` registers `TARIFF` and `_take_section` collects its
      lines, but no `ElementRecord` field stores them. The rare-earths
      sheet has 5 non-trivial HTS tariff lines (5% / 5.5% / 5.9% ad
      valorem) that may matter to downstream users. Likely fix: add
      `tariff: list[TariffItem]` to `ElementRecord` and a `_parse_tariff`
      helper that walks the section's lines.
- [ ] **#R4 Government Stockpile section is parsed but discarded** (medium) —
      Same shape as #R3. Rare earths has a 1,100-ton Lanthanum FY 2025
      potential-acquisitions row plus the prose mention of 300 t NdPr
      oxide, 450 t NdFeB block, 60 t SmCo alloy. Not exposed anywhere.
- [ ] **#R5 Title-level footnote is unreachable from the record** (low) —
      `RARE EARTHS¹` — footnote 1's body IS in `record.footnotes["1"]`,
      but nothing on the record signals that the title itself carries
      that marker. A consumer reading the units note doesn't know to
      look at footnote 1. Likely fix: add `title_footnote: Optional[str]`
      to `ElementRecord`.
- [ ] **#R6 Per-REE alias prose is unfiltered parent prose** (low) —
      Cerium's `events_trends_summary` is the verbatim rare-earths
      events block, which mentions samarium, gadolinium, terbium,
      dysprosium, lutetium, scandium, yttrium, europium, holmium, erbium,
      thulium, ytterbium — but **not cerium**. The narrative is misleading
      on the cerium detail page. Likely fix: filter the prose at alias
      time to sentences that mention the alias's name, OR add a
      per-element disclaimer "prose inherited from the rare-earths
      grouped sheet — no cerium-specific narrative is published."
- [ ] **#R7 Salient-stats row labels collide across sections** (low) —
      Rare earths has two rows labeled `Compounds and metals` (Production
      section, value 8,900) and `Compounds and metals` (NIR section, value
      67). The viewer's `salientBlock` groups by `section` so these
      render correctly, but any consumer that keys on `label` alone will
      collapse them. Similar collision: `Mineral concentrates` appears
      under Production (value 51,000) AND under NIR (value E).
- [ ] **#R8 Mined production semantic differs from antimony semantics** (low) —
      Latest-year summary column "Mined production" = 51,000 for
      rare earths (REO content of mineral concentrates) vs. "W" for
      antimony (recoverable antimony content). The two are not directly
      comparable — they measure different points in the value chain.
      Likely fix: rename the column to something more neutral
      ("Production — mine stage") OR surface the row label as a tooltip.
- [ ] **#R9 Numeric reserves fields lose `>` / `<` sentinel** (low) —
      Already partly addressed (raw form is preserved in `reserves_raw`,
      audit.md renders it), but `world_production[*].reserves` itself is
      a plain float (85,000,000) without the inequality. CSV consumers
      that only look at the numeric field can't tell `>85M` from `85M`.
      Likely fix: when a sentinel was captured, expose a `_is_lower_bound`
      / `_is_upper_bound` boolean.

### Items already addressed in this session (cross-reference)

- [x] **Import-sources regex dropped the trailing entry** when followed
      by prose — fixed in [7752b8e]; the "other, 6%" now appears.
- [x] **Primary-smelting summary value was null** for rare earths —
      fixed by extending `_find_row` to match `compounds and metals`.
- [x] **Price summary value picked an arbitrary commodity** — fixed in
      `pipeline._postprocess_record` for the rare-earths slug.
- [x] **Per-rare-earth alias lost the $/kg unit** — fixed by composing
      `<form> (<unit>)` in the alias's `price_unit_note`.

## CSV pruning — 2026-05-19 inventory

`elements.csv` currently sits at **135 rows × 2,305 cols**. Most of the
width comes from per-year × per-form salient stats and per-country
production tables. The decision matrix below is what we'd cut next when
column count becomes the bottleneck (Excel choking, Sheets refusing to
open it, slow `pd.read_csv`).

### Family inventory (current, MCS 2026 bundle)

| # | Family                             | Cols  | Schema                                              |
| - | ---------------------------------- | ----: | --------------------------------------------------- |
| 1 | IDENTITY                           |     8 | `name, kind, source_url, units_note, price_unit_note, import_sources_range, world_production_label, import_category` |
| 2 | LATEST-YEAR SUMMARY                |     8 | `mined_production_latest`, `primary_smelting_latest`, … `net_import_reliance_pct_latest` |
| 3 | SALIENT STATS per year             |   800 | `<section>__<label>__<year>` (5 yrs × ~160 forms) |
| 4 | PRICE QUOTES per year              |   340 | `price__<form>__<year>` (5 yrs × ~68 priced forms) |
| 5 | PER-COUNTRY imports share %        |    50 | `<country>_imports_share_pct` |
| 6 | PER-COUNTRY production (year-tag)  |   162 | `<country>_production_<year>` (81 countries × 2 yrs) |
| 7 | PER-COUNTRY capacity               |    81 | `<country>_capacity` (mostly N/A — USGS rarely reports capacity) |
| 8 | PER-COUNTRY reserves               |    66 | `<country>_reserves` |
| 9 | OTHER (long-slug variants of #3/4) |   790 | same shape as #3/#4 but with verbose USGS section labels (e.g. `price_average_unit_value_of_imports_dollars_per_metric_ton__…__2025e`) |

### Cut options ranked by reward / regret

- [ ] **Drop #7 capacity** (low effort, low regret) — 2305 → 2224.
      Almost every cell is `N/A` because USGS only reports capacity on a
      handful of sheets (indium, germanium, niobium, …). Five mins of work.
- [ ] **Drop #9 "OTHER" long-slug family** — 2305 → 1515. Same data
      content as #3/#4 but at column names so long they hurt to read.
      Better fix would be to *shorten* the section slug in `_slugify`
      (clip to N chars + hash) rather than drop.
- [ ] **Drop pre-2024 history in #3 / #4** — 2305 → ~1380. Keep only
      `_2024` and `_2025e` columns; the 2021–2023 history lives in
      `elements.json` for the rare consumer who needs five-year series.
      Big win, but irreversible without re-running the pipeline.
- [ ] **Drop #4 price quotes per year entirely** — 2305 → 1965. Detail
      panel already shows the full price table; CSV consumers usually
      only need one price (already in #2 latest-year summary).
- [ ] **Minimum-viable "country dependency table" CSV** (most
      aggressive) — keep only #1 + #2 + #5 + #6 → ~286 cols. Loses
      everything per-year except the latest-year summary. Best for the
      "open-in-Sheets-and-skim" use case.
- [ ] **Long-slug-shortening pass** (~30 min) — rewrite `_slugify` to
      clip section slugs over ~32 chars and append a short hash. Doesn't
      lose columns, just makes them readable: e.g.
      `price_average_unit_value_of_imports_dollars_per_metric_ton__fused_aluminum_oxide_crude__2025e`
      → `price_aviu_dpmt__fused_aluminum_oxide_crude__2025e`. Acts as a
      cheaper substitute for "drop #9".

### Notes
- `elements.json` schema is unchanged by every option above — these
  cuts only affect the rectangular CSV view. JSON consumers (the viewer,
  audit reports) keep full fidelity regardless.
- Pairs well with **CSV-shape filters** in the viewer: a "download CSV"
  button per *use-case* (full / country-dependency-only / latest-year-only)
  would let consumers choose without committing to a single global
  pruning decision.

## Viewer enhancements

- [ ] **Sort / filter** the overview table (medium) — click a column header to sort; chip filters for "REE only", "PGM only", "Critical 2022 list".
- [ ] **Sparkline cells** (low) — add a tiny inline 5-year line for each numeric column.
- [ ] **Bookmarkable detail URLs** (low) — `?element=bismuth` opens straight to that element's detail card.
- [ ] **Mobile bottom sheet for detail** (low) — per DESIGN.md §7, swap the inline detail card for a bottom sheet at <640px.

## Audit module enhancements

- [ ] **Bounding-box overlays** (medium) — for each extracted numeric value, draw a red box over its source coordinates on the page PNG. Catches "we read a footnote as a value" bugs.
- [ ] **Diff report** (medium) — when re-running, write a Markdown diff vs. the prior JSON so changes are obvious.

## Infrastructure

- [ ] **GitHub Pages deploy** (medium) — once a stable set of elements is in, publish `viewer/` + a baked `data.json` snapshot.
- [ ] **CI** (low) — run `python -m unittest tests` on push; cache the bismuth PDF as a test fixture.
