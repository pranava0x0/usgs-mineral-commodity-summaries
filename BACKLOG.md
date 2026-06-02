# BACKLOG.md

Per CLAUDE.md §Backlog — ideas, follow-ups, and queued elements. Each item has a priority.

## New ideas — 2026-06-02 online research

Sourced from a web sweep on critical-minerals policy + comparable tools. These
are *external-facing* features (the rest of this backlog is mostly internal
parser/CSV refinement). Each carries a priority + effort + the source that
motivated it.

> **Data-source rule (user, 2026-06-02): only grab documents from official U.S.
> government (`.gov`) websites** — USGS (`pubs.usgs.gov`), Census
> (`census.gov` / `usatrade.census.gov`), `trade.gov`, Federal Register
> (`federalregister.gov`), Commerce/BIS (`bis.gov`). The non-`.gov` links below
> (CSIS, Pillsbury, IEA, ScienceDirect, UN Comtrade, …) are *context /
> methodology references only* — never data sources. Any idea that needs a
> non-gov feed must be re-sourced to a `.gov` equivalent before it's built.

### 1. Align to the **2025 USGS Critical Minerals List** (HIGH)

The project is framed around the *2022* critical-minerals list (see README,
"USGS 2022 critical minerals list" in §Elements). On **2025-11-07** USGS
finalized the **2025 List** — all 50 from 2022 **plus 10 new**: boron, copper,
lead, metallurgical coal, phosphate, potash, rhenium, silicon, silver, uranium
→ **60 total**. We already cover copper, rhenium, silicon, silver. This is the
most timely gap. Two parts:

- [ ] **1a. Tag each element with the list(s) it appears on** (medium, ~2 h) —
      add a `critical_lists: list[int]` field (e.g. `[2018, 2022, 2025]`) on
      `ElementRecord` / the `ELEMENTS` config, surfaced in JSON + CSV + viewer.
      Single source of truth for "is this critical, and since when?". Directly
      powers the **already-backlogged** "chip filters for Critical 2022 list"
      (see §Viewer enhancements → Sort/filter) and lets the viewer show a
      "**New in 2025**" badge. Each element is one literal in config. STILL
      OPEN — the 2026-06-02 work added the commodities and noted list membership
      in each `Element.notes` prose, but did not add the structured field.
- [x] **1b. Add the missing 2025-list commodities** — DONE (2026-06-02). Added
      **Boron, Lead, Phosphate rock, Potash** (new on the 2025 list) plus the
      2022-list leftovers **Arsenic, Barite, Beryllium, Cesium, Fluorspar,
      Rubidium** (see §Elements "Queued" below — now resolved). All 10 had
      standard MCS 2026 sheets and parsed with the generic state machine (one
      `ELEMENTS` entry each); regression tests in
      `tests/test_new_commodities.py`. **Uranium** and **Metallurgical coal**
      confirmed absent from the MCS 2026 index (EIA-DOE domain) — left out of
      scope, not faked. Four small parser fixes shipped alongside (see
      issues.md #20–#23): `XX` sentinel recognition, bounded import shares
      (`>99%`), wrapped-unit-subheader world rows, and a comma-qualifier
      country-name fallback. Bonus: the bounded-share fix recovered
      previously-dropped import data on **copper** (Canada >99%) and
      **manganese** (other <1%). Also fixed `captured_at` churn (issues.md #24).
      Source: [USGS final 2025 list](https://www.usgs.gov/news/science-snippet/interior-department-releases-final-2025-list-critical-minerals),
      [Federal Register 2025-19813](https://www.federalregister.gov/documents/2025/11/07/2025-19813/final-2025-list-of-critical-minerals).

### 2. **Supply-concentration / HHI metric** (MEDIUM, ~3 h)

Derive a **Herfindahl-Hirschman Index** per commodity from the per-country
production shares we *already* parse (`world_production[*]`). HHI = Σ(country
share %)², range 0–10,000; it's the standard criticality / supply-risk metric
used by IEA and the academic literature. Emit two derived summary fields:
`production_hhi` and `top_producer_share_pct` (+ optionally `top3_share_pct`).
Pure computation — **no new data source, no network**. Pairs naturally with the
shipped "By country" view and the latest-year summary block. Surface as a
"supply concentration: 6,400 (highly concentrated — China 78%)" callout.
Caveat to document: HHI under-reads risk in *less* concentrated markets (per
the literature) — present it as one signal, not a verdict.
Source: [HHI criticality study (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0140988325000313),
[IEA Critical Minerals Data Explorer](https://www.iea.org/data-and-statistics/data-tools/critical-minerals-data-explorer).

### 3. **Export-control / supply-shock context layer** (MEDIUM, ~3 h)

China's controls hit *exactly* the commodities we track, with price spikes of
**200–437%**: Dec-2024 gallium/germanium/antimony/superhard + graphite review;
Apr-2025 seven heavy REEs (Tb, Dy, Sm, Gd, Lu, Sc, Y); Oct-2025 expansion;
Nov-2025 one-year suspension. We already half-acknowledge this (the dysprosium
config note cites "Apr-2025 China export controls"). Idea: a small **curated
`data/events.json`** (date, commodities[], action, price-impact, source URL),
rendered as a "supply-risk timeline / callout" on affected element pages.
Hand-maintained, append-only, source-attributed per CLAUDE.md §Data. Keeps the
tool's "as of" framing honest — USGS MCS numbers predate the shock. **Per the
data-source rule, each event must cite a `.gov` primary document** — Commerce/BIS
(`bis.gov`), the Federal Register (`federalregister.gov`), or USTR (`ustr.gov`) —
not the think-tank summaries that first surfaced them.
Source (context only, non-gov): [CSIS on China rare-earth controls](https://www.csis.org/analysis/consequences-chinas-new-rare-earths-export-restrictions),
[Pillsbury — Nov-2025 suspension](https://www.pillsburylaw.com/en/news-and-insights/china-suspends-export-controls-certain-critical-minerals-related-items.html).

### 4. **Real bilateral trade flows from the US Census trade API** (MEDIUM-HIGH, ~1–2 days)

The repo is literally named *"Critical Minerals Import Export Data"*, but we
only carry USGS **import-source shares (%)** — not actual tonnage/value flows.
The **US Census Bureau International Trade API** (`api.census.gov`, a `.gov`
source) exposes real US import/export tonnage + value time series by HS code and
partner country — the gov-native feed for this. (UN Comtrade was the original
candidate but is `un.org`, not `.gov` → excluded per the data-source rule above.)
Adding even a handful of HS-mapped series per commodity would turn the % shares
into absolute, year-over-year flows. Biggest scope here: needs an
HS-code↔commodity mapping table and a new cached+rate-limited fetcher (mirror
`fetcher.py` etiquette; Census API key is free). Highest user value, largest
effort, first external runtime dependency — scope a 2–3-commodity spike first.
Source: [US Census trade API guide](https://www.census.gov/foreign-trade/reference/guides/Guide_to_International_Trade_Datasets.pdf),
[Census International Trade API](https://www.census.gov/data/developers/data-sets/international-trade.html).

### 5. **Choropleth world-production map** (MEDIUM, ~4 h)

USGS itself ships an "Interactive Atlas of Critical Minerals." We have the
per-country mine-production / reserves data already; a world map shaded by a
selected commodity's production share would be a strong visual for the "By
country" / element-detail views. Per CLAUDE.md §Frontend (minimize page weight,
boring tech): use a **lightweight inline SVG world map** keyed by ISO code —
not a heavyweight mapping library — and reuse the existing canonical-country
mapping in `src/countries.py`. Pairs with the HHI metric (#2) as the headline
of an element page.
Source: [USGS 2025 list + Critical Minerals Atlas](https://www.usgs.gov/programs/mineral-resources-program/science/about-2025-list-critical-minerals).

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

- [x] **Arsenic, Barite, Beryllium, Cesium, Fluorspar, Rubidium** — DONE
      (2026-06-02, alongside the 2025-list additions; see §"New ideas" #1b).
      Palladium, Rhodium, Ruthenium were already covered as PGM aliases.
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
- [ ] **`ELEMENT_PRODUCTION_BLOCK` silent-drop footgun** (medium) — `csv_export.ELEMENT_PRODUCTION_BLOCK` is a hardcoded `slug → "mine"/"refinery"/None` map. A new primary added to `config.ELEMENTS` but *not* to this map gets `block=None`, so its per-country production silently vanishes from the CSV (reserves still map — they aggregate independently). Bit us on 2026-06-02 (boron/lead/potash/arsenic). Fix options: (a) derive the block from `world_production_label` (e.g. contains "Mine"→mine, "Refinery"→refinery) with the dict as an override-only table; or (b) at minimum, `log.warning` when a record has a non-empty `world_production` but no block mapping. Pairs with the existing "Mine production vs refinery production normalization" item above.
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
| Titanium                | RESOLVED (split)     | two sub-tables → sub-rows carry production in `primary_smelting` (sponge 0, TiO₂ 1,000,000); see "Titanium split" |
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

- [x] **Chromium** — FIXED (2026-05-22, issues.md #19). The `Stainless
      steel` category now round-trips to `Taiwan 16%, Finland 12%, India
      11%, China 6%, others 55%`. Root cause was comma-separated countries
      (not "and") being dropped by the country-share splitter; rewritten to
      scan all entries with `re.finditer`. Ferrochromium also recovered its
      trailing `other, 24%`.

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
- [x] **Views by country** (medium) — v1 SHIPPED (2026-05-22). A "By country"
      top-level tab in the viewer: a country picker (94-entry axis from baked
      `viewer/countries.json`) + a per-country panel with 5 blocks (import share
      w/ US net-import-reliance context, mine / refinery / capacity / reserves),
      sorted, with an empty state for prose-only countries (e.g. Bhutan) and a
      `?view=country&country=` deep link. Built client-side from the
      canonical-mapped `data.csv` (option b below was not needed). Possible
      follow-ups: filter/sort controls, a "top suppliers" landing view, baked
      `by_country.json` for static/LLM consumers. Original spec:
      a country-centric pivot of the existing
      per-element data: pick a country (from the 94-entry canonical axis) and
      see every commodity it touches — as an import source (% share + which
      form/category), and as a mine / refinery / capacity / reserves holder —
      with the US import-reliance context. Inverts today's element-first view
      ("where does the US get antimony?") into a supplier-first view ("what does
      China supply, and how dominant is it?"). The data already exists: the CSV's
      5 per-country blocks (`<country>__imports_share_pct` / `__mine_production` /
      `__refinery_production` / `__capacity` / `__reserves`) are exactly this
      table transposed, and `src/countries.py` already maps USGS spellings to the
      canonical axis. Build options: (a) a viewer tab that transposes
      `data.csv`/`data.json` client-side and renders a per-country card
      (commodity, role, value, share, US NIR); (b) a baked `by_country.json`
      pivot emitted from `csv_export` so static consumers/LLMs get it too.
      Notes/decisions:
      - Drop the residual `other`/`others` bucket and `World total` (already
        excluded from the canonical axis) so a country page sums cleanly.
      - Surface the same sentinels verbatim (W / E / >N / NA) per cell.
      - "Top suppliers" landing view (China, Canada, Australia, Mexico, Japan,
        South Korea lead by coverage — see `tests/test_countries.py`).
      - New Zealand (and other non-canonical names) have no data — render an
        explicit "not reported in MCS 2026" empty state, don't 404.
      - Pairs well with **Sort / filter** (filter the per-country list by block)
        and **Bookmarkable URLs** (`?country=china`).

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
| **Titanium** (parent + 2 sub-rows; no world table — see "Titanium split" below)  | —    | — | — | — |
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
- [x] **Titanium summary blends two commodities** — FIXED (split into two
      sub-product rows, mirroring iron-and-steel; user-confirmed naming
      2026-05-20). The "TITANIUM AND TITANIUM DIOXIDE" sheet has two stacked
      salient sub-tables (Ti metal: imports 44,000 / exports 63 / cons 44,000 /
      $12 per kg; TiO₂: prod 1,000,000 / imports 230,000 / exports 330,000 /
      cons 900,000 / $3,200 per t), which the generic summary blended (imports
      274,000 + exports 330,063; consumption/price/NIR from the first sub-table
      only). The parent `titanium` now de-blends (summary nulled in
      `_postprocess_record`) and fans out into `titanium-sponge-metal`
      ("Titanium (sponge/metal)") and `titanium-dioxide` ("Titanium (dioxide)")
      sub-products, each carrying its own full per-commodity summary +
      import-source category. Sub-table boundary detected by section-repeat in
      `pipeline._titanium_salient_groups`. Regression tests in
      `tests/test_csv_export.py::TitaniumSplitTests`; see
      `docs/parsing-special-cases.md` §"Titanium".
- [ ] **Vanadium production summary undercounts byproduct recovery** —
      `primary_smelting` = 0 (from "Production from primary ore and
      concentrates" = 0); the real 7,500 t from "Production from ash,
      residues, and spent catalysts" lands in no summary field. Vanadium is
      mostly a byproduct, so the headline production reads as zero. Low
      priority — full data is in salient_stats; only the summary triplet is
      incomplete.

## Group / multi-form repeat values (2026-05-20)

A row that belongs to a group (or a single-mineral sheet split by form) must
carry **its own** mineral/form data — never the whole-group/whole-sheet sum.
The sum belongs on the group parent / a bare total row. Reference impls: PGM,
iron-and-steel, titanium.

### Mechanism A — single-mineral sheets split by import FORM — DONE

- [x] **Per-form import/export rows + bare total row** — antimony, chromium,
      copper, germanium, magnesium, manganese, molybdenum, nickel, niobium,
      rhenium, silicon, tantalum, tin, vanadium, zinc. Each form row now shows
      its own imports/exports (or N/A if the salient doesn't break it out); the
      mineral-wide summary + world table sit on a bare parent/total row. See
      `docs/parsing-special-cases.md` §"Per-form import rows"; tests in
      `tests/test_csv_export.py::MechanismAPerFormTests`.
- [x] **Renamed summary columns** `usgs_2025_total_primary_smelting` →
      `…_primary_production`, `…_secondary_smelting` → `…_secondary_production`.

### Mechanism B — true multi-mineral GROUPS — DONE (2026-05-20)

Each member alias now grabs only its mineral's salient rows / import categories
/ world table via `parent_filter` + `pipeline._fill_group_member`; members also
reuse the Mechanism A per-form split so their import-form rows don't repeat the
member total. Group parents collapse to a bare sum row (`csv_export`). See
`docs/parsing-special-cases.md` §"Mechanism B"; tests in
`tests/test_csv_export.py::MechanismBGroupTests`.

- [x] **Hafnium / Zirconium** (← zirconium-and-hafnium) — Hf: bare 84 (unwrought
      72 / wrought 12), world N/A; Zr: bare imports 18,210 + production 100,000,
      per-form rows (ores 16,000 / compounds 1,300 / unwrought 530 / wrought
      380), keeps the zircon mine+reserves table.
- [x] **Silicon carbide / Fused aluminum oxide / Metallic abrasives**
      (← abrasives) — own production/imports/exports/consumption per material
      (SiC 30,000/95,000; fused 20,000/150,000; metallic 160,000/16,000); world
      N/A. Added `fused-aluminum-oxide` + `metallic-abrasives` aliases.
- [x] **Superhard materials** (← abrasives) — all-N/A proxy (prose kept).
- [x] **Diamond powders / Gallium nitride / Graphite anodes / Lithium
      batteries** — single-mineral downstream products; summary + world + import
      sources blanked to N/A (prose kept).
- [x] **Rare-earth aliases** — also drop the inherited group REO world table +
      import sources (kept only the per-element oxide price). Was: every REE
      showed China mine 270,000 / reserves 44,000,000.
- [x] **Abrasives / Zr-Hf parent shape** — both collapse to a bare sum row;
      abrasives fully split into fused-alumina / SiC / metallic so no import
      shares are lost.

Residual (minor, pre-existing): the Zr-Hf *parent* row's `mined_production`
summary is N/A (the bare "Production, zirconium ores…" salient row doesn't match
the parser's mine-row heuristic) even though the zirconium member shows 100,000
and the parent's per-country mine block is populated. Tracked by the existing
"bare Production → mine fallback" item.
