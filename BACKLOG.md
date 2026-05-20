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

## Multi-category element audit — 2026-05-19

Walked through every sheet that emits more than one CSV row (one row
per import-source category). Most are clean; the issues below recur
across multiple commodities and are the same *class* as rare-earths
#R8 (semantic mismatch in the "Mined production" summary column).

### Latest-year summary is N/A but the PDF reports production

The summary's `mined_production_latest` / `primary_smelting_latest` /
`secondary_smelting_latest` triplet only matches rows whose label or
section keyword is `mine` / `primary` / `secondary` / `refinery`. Many
sheets use different label conventions. Affected elements (latest-year
values from the PDF in parens; current summary in column 2):

| Element                 | Summary shows        | PDF reports                                 |
| ----------------------- | -------------------- | ------------------------------------------- |
| Abrasives (manufactured)| mine/primary/sec N/A | 4 production rows (fused Al₂O₃, SiC, metallic, shipments — no single total) |
| Silicon                 | all N/A              | 1 row "Production, ferrosilicon and silicon metal" = `W` (withheld) |
| Titanium                | all N/A              | 1 bare "Production" row = `—` (zero)        |
| Rhenium                 | all N/A              | 1 bare "Production" row = `9,800`           |
| Zirconium-and-hafnium   | all N/A              | 1 row "Production, zirconium ores and concentrates" = `<100,000` |
| Iron-and-steel          | all N/A              | 4 rows (pig iron 21, raw steel 82, continuously-cast %, shipments 82) — already filed as issues.md #14 |

Suggested fix: extend `_find_row` to (a) match a bare `Production`
section as the `mine` fallback when no labelled mine row exists, and
(b) match `production, <anything>` as the `mine` fallback when the
section is anchored at "Production". For genuinely multi-product
sheets (abrasives, silicon), pick the first production row OR leave
N/A — same trade-off as rare-earths' multi-price summary.

### Confirmed parser label-merging bugs

These show up in audit reports and the CSV as nonsensical row labels:

- [ ] **Tantalum** — under section "Shipments from Government stockpile",
      the row label is `"NA Consumption, apparent"` with value `890`.
      The stockpile cell value `NA` got concatenated onto the next
      row's label. The real shape: stockpile row → NA; apparent
      consumption row → 890. Likely in the label-continuation merge
      in `_parse_salient_stats` (a leading short token like "NA" is
      ambiguous with a label fragment).
- [ ] **Rhenium** — under section "Employment, number", the row label
      is `"Small Net import reliance as a percentage of apparent c…"`.
      The Employment-number value (probably "Small") got prefixed to
      the NIR row's wrapped label. Same root cause as the tantalum
      one: tiny right-edge tokens are mis-classified as label
      fragments.

### Chromium "Stainless steel" import-sources truncated

- [ ] **Chromium** — the `Stainless steel` import-source category
      currently lists only `Taiwan, 16%; others, 55%`. The PDF lists
      more countries (Finland, India, China). Surfaced by the country-
      share parser bug already filed as issues.md #12 ("merges
      multiple countries when separator is 'and'"). When that fix
      lands, chromium's stainless-steel row should round-trip to 5+
      countries.

### Things that look correct

Confirmed-good across the multi-category set: copper, manganese,
niobium, nickel, molybdenum, tin, vanadium, zinc, diamond, germanium,
magnesium. The Antimony / Rare-Earths audits earlier this session
cover those.

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

## CSV restructure — public-column spec (shipped 2026-05-19)

Per user-provided `public column information.xlsx`, restructured
`elements.csv` to a fixed shape derived from a 203-country canonical
list (Canada, China, Mexico, EU, then alphabetical world, ending at
Vatican City). Final shape: **139 rows × 1,032 cols** (was 135 × 2,305).

User-confirmed answers (2026-05-19):
- A. PGM multi-column parser bundled in.
- B. Iron and Steel Pig iron + Raw steel → Refinery Production block.
- C. Bismuth → Capacity (all NA in source).
- D. Indium / Tellurium / Germanium / Gallium → Refinery Production.
- E. USGS country names mapped to spec list; EU members roll up into
     `European Union`; non-country labels (`other`, `World total`,
     parser bug labels) dropped.

### Final shape

- **8 identity columns** (A–H, unchanged): `name, kind, source_url,
  units_note, price_unit_note, import_sources_range,
  world_production_label, import_category`
- **9 summary columns** (I–Q):
  1. USGS 2025 total mined production
  2. USGS 2025 total primary smelting
  3. USGS 2025 total secondary smelting
  4. Imports for consumption (total)
  5. Exports (total)
  6. Consumption, apparent (primary + secondary + imports − exports)
  7. Price, metal, average, dollars per pound
  8. Net import reliance as a percentage of apparent consumption
  9. **Government Stockpile (FY2025 Potential Acquisitions)** ← new field
- **5 country blocks × 203 countries = 1,015 country columns**:
  1. Import Sources (2021–2024)
  2. Mine Production
  3. Refinery Production
  4. Capacity (refinery or production)
  5. Reserves

Total: ~1,032 cols × ~140 rows (was 2,305 cols × 135 rows).

### Per-element block placement (which block USGS data populates)

| Element                                                                          | Mine | Refinery | Capacity | Reserves |
| -------------------------------------------------------------------------------- | :--: | :------: | :------: | :------: |
| Antimony, Aluminum, Chromium, Cobalt, Copper, Diamond, Graphite, Lithium, Magnesium, Manganese, Molybdenum, Nickel, Niobium, Rare Earths, Silver, Tantalum, Tin, Tungsten, Vanadium, Zinc, Zirconium-and-hafnium | ✅ | — | — | ✅ |
| **Bismuth**                                                                      | —    | ✅       | ✅ (all NA) | — |
| **Indium**                                                                       | —    | ✅       | ✅        | — |
| **Tellurium**                                                                    | —    | ✅       | ✅        | — |
| **Germanium**                                                                    | —    | (prose only) | — | — |
| **Gallium**                                                                      | —    | ✅ (USGS calls it "Primary Low-Purity Production") | ✅ | — |
| **Iron and Steel (Pig iron)** ← new row                                          | ✅¹  | — | — | — |
| **Iron and Steel (Raw steel)** ← new row                                         | ✅¹  | — | — | — |
| **PGM: Palladium** ← new alias                                                   | ✅ (palladium sub-column) | — | — | — |
| **PGM: Platinum** (existing alias, reshape)                                      | ✅ (platinum sub-column) | — | — | — |
| **PGM: Iridium / Osmium / Rhodium / Ruthenium** (Pd/Rh/Ru/Os are new aliases)    | —    | — | — | — |
| **PGM (grouped parent)**                                                         | —    | — | — | ✅ (PGM-aggregate) |
| **Titanium** (skipped per user)                                                  | —    | — | — | — |
| Abrasives, Scandium (no world table)                                             | —    | — | — | — |

¹ Iron and Steel placement: open question. PDF table is just "World
   Production" (neither mine nor refinery). My pick: Mine Production
   for human readability; alternative is Refinery Production for
   technical accuracy.

### Row-count changes from current

- Iron and Steel: 1 → **2** rows (Pig iron, Raw steel)
- Platinum-group metals: 2 → **7** rows (Ir, Os, Rh, Ru, Pd, Pt, group)
- All other elements: unchanged
- Net: 135 → ~140 rows

### Country-name reconciliation

- USGS variants get mapped to the spec list (e.g.
  `Korea, Republic of` → `Korea, South`)
- USGS-side row labels that aren't real countries — `other`, `others`,
  `World total (rounded)`, and the scandium prose-as-country parser
  bug — are **dropped** from CSV. They remain in `elements.json` for
  anyone who needs them. Row sums won't always equal 100% / world total
  as a result (the residual is invisible). Acceptable per spec.

### Code work required (~5 hours)

| Change | Effort |
| --- | --- |
| Parse Government Stockpile section → new `stockpile_fy2025_potential_acquisitions: Optional[float]` field on ElementRecord (resolves BACKLOG R4) | ~30 min |
| Parse PGM multi-column world production (capture both Pd + Pt sub-columns) | ~60 min |
| Add `palladium`, `rhodium`, `ruthenium`, `osmium` aliases in config | 5 min |
| Add `iron-and-steel-pig-iron` and `iron-and-steel-raw-steel` sub-aliases (or generalise the row-fanout logic) | 10 min |
| Rewrite `_make_alias` to filter PGM data per-metal | 30 min |
| Rewrite `csv_export.py` with the 5-block, 203-country layout + country-name mapping | ~2 hours |
| Update `tests/test_csv_export.py` for new columns + new row counts | 30 min |
| Regenerate `elements.{csv,json}` + verify | 15 min |

### Open questions (resolved 2026-05-19)

- [x] **Q1. Iron and Steel block placement** — Refinery Production (user override; pig iron + raw steel both post-mine smelting).
- [x] **Q2. Gallium placement** — Refinery Production (Low-Purity Production is a smelter-stage byproduct).
- [x] **Q3. Parser bundling** — bundled: Government Stockpile parser + PGM multi-column parser both shipped with the restructure.

### Follow-up items (deferred)

- [ ] **Rare-earths Government Stockpile is under-counted** — parser captures
      the 1,100 t Lanthanum table row but misses the prose mention of
      300 t NdPr oxide + 450 t NdFeB block + 60 t SmCo alloy. Would need
      Stockpile-section prose parsing (estimated +30 min).
- [ ] **PGM grouped parent's mined / primary / secondary summary cells are N/A**
      — generic `_find_row(salient, "Production", "mine")` doesn't match
      PGM's per-metal "Palladium" / "Platinum" salient rows. After the
      May-2026 PGM-alias refactor, individual aliases (palladium,
      platinum, iridium, …) now carry correct per-metal summary values
      via `_make_alias`, but the *grouped parent row* still has N/A in
      mined / primary / secondary. Fix: a PGM-specific
      `_postprocess_record` branch that sums Pd + Pt into
      `mined_production_latest` for the parent. ~10 min.
- [x] **Iron-and-Steel parent has all-N/A summary cells** — fixed in PR
      that landed alongside the country-list revision. `_postprocess_record`
      sums Pig iron + Raw steel into `primary_smelting_latest`; mined stays
      N/A (per user — both rows are post-mine smelting). Sub-product rows
      (Pig iron / Raw steel) now strip to only primary_smelting +
      refinery_production country block; all other fields N/A.
- [x] **Iron and Steel sub-products inherit parent's combined per-country
      refinery numbers** — RESOLVED. The earlier assumption (single
      combined World Production column) was wrong: the USGS table DOES
      split into "Pig iron" / "Raw steel" sub-columns, exactly like PGM's
      Pd / Pt. The parser missed it because there's no explicit "X
      production" column-title row (the sub-headers sit directly under
      "World Production:") AND the header line's tall bbox overlapped the
      sub-header row, excluding it from the y-range. Fixed by (a) using the
      header's vertical center as `y_min`, and (b) allowing sub-metal
      detection when the section header itself is a production table. Now
      China shows pig iron 830 vs raw steel 980; the parent shows the sum
      (1810) consistent with its summary primary_smelting (103).
- [ ] **Canonical country list audit (post-revision)** — the user revised
      the canonical list to 94 entries on 2026-05-19. The shorter list
      means more USGS countries fall to `map_country() → None` than
      before (Algeria, Albania, EU non-member microstates, most small
      islands, etc.). We should systematically walk every USGS country
      name we drop and surface any with material world-production or
      reserves data so the user can decide whether to add them back
      Kyrgyzstan-style. Low priority — most dropped entries are small
      islands with no USGS mineral data.
- [x] **Kyrgyzstan missing from spec** — fixed by extending the canonical
      list to 204 entries (Kyrgyzstan inserted alphabetically between
      Kosovo and Liechtenstein in the Europe block). Captures 700 t
      antimony mine production + 260,000 t reserves that were previously
      dropped. CSV column count grew 1,032 → 1,037.

## Cell-validation pass — 2026-05-19 (against MCS 2026 PDFs)

Walked every primary element's summary columns + world-production /
reserves cells against the source PDFs. World production, reserves,
sentinel preservation (W / E / >N / —), and country-name mapping
(Congo (Kinshasa) / DRC, Burma (Myanmar), Korea N/S, Côte d'Ivoire,
Kyrgyzstan) all round-trip correctly. Findings:

- [x] **Scandium apparent_consumption was the NIR % (100), not consumption**
      — FIXED. Scandium has no consumption row, but its NIR label ("Net
      import reliance as a percentage of apparent consumption") contains
      "apparent", so `_find_row(None, "apparent")` grabbed it. Now scoped to
      the Consumption section with a non-NIR fallback; scandium correctly
      reports apparent_consumption = None. Regression test in
      `tests/test_antimony.py::ScandiumRecordTests`.
- [ ] **Titanium summary blends two commodities** — the sheet is "TITANIUM
      AND TITANIUM DIOXIDE" with two stacked salient sub-tables (Ti metal:
      imports 44,000 / exports 63 / cons 44,000 / $12 per kg; TiO₂: prod
      1,000,000 / imports 230,000 / exports 330,000 / cons 900,000 / $3,200
      per t). `_latest_value_by_section` SUMS across both, so the row shows
      imports 274,000 + exports 330,063 — a blend of titanium sponge and
      TiO₂ pigment, while consumption/price/NIR pick only the first
      sub-table. Same class as abrasives. Fix would split titanium into two
      rows (like iron-and-steel pig iron / raw steel) — needs a design call
      on naming. Medium priority; flagged for user.
- [ ] **Vanadium production summary undercounts byproduct recovery** —
      `primary_smelting` = 0 (from "Production from primary ore and
      concentrates" = 0); the real 7,500 t from "Production from ash,
      residues, and spent catalysts" lands in no summary field. Vanadium is
      mostly a byproduct, so the headline production reads as zero. Low
      priority — full data is in salient_stats; only the summary triplet is
      incomplete.
