# Parsing special cases & data-refresh checklist

> **Read this before re-running the pipeline against a new MCS edition.**
> The generic state-machine parser ([src/parser.py](../src/parser.py)) handles
> most USGS Mineral Commodity Summaries sheets, but a handful of commodities
> have layouts that need bespoke handling. Each case below is a place where the
> source PDF deviates from the common shape — if USGS changes a layout in a new
> edition, these are the first things to re-verify. Every case lists **what**,
> **why**, **where in code**, and **how to verify**.

This file is organizational scar tissue (per [CLAUDE.md](../CLAUDE.md)
§"Keep this file current"). When you discover a new layout quirk, add it here.

---

## Refresh checklist (run top-to-bottom on a new MCS edition)

1. **Bump the edition constants.** [src/config.py](../src/config.py):
   `MCS_EDITION`, `MCS_DATE`, `BASE_MCS`. Confirm USGS hasn't renamed any
   slugs (they renamed `platinum-group-metals` → `platinum-group`,
   `zirconium-and-hafnium` → `zirconium-hafnium`, `iron-and-steel` →
   `iron-steel`, `magnesium` → `magnesium-metal`, `titanium` already in 2026).
2. **Bump `YEAR_COLUMNS`.** [src/models.py](../src/models.py) — for MCS 2026
   it's `("2021", "2022", "2023", "2024", "2025e")`. For MCS 2027 the latest
   estimated year becomes `2026e` and the window slides. The viewer
   ([viewer/viewer.js](../viewer/viewer.js) `YEARS` / `YEAR_LABELS`) and audit
   header ([src/audit.py](../src/audit.py)) hardcode the same tuple — update
   all three. See **"The `2025e` estimated marker"** below.
3. **Run** `python -m src.pipeline --refresh` then `python -m unittest discover tests`.
4. **Re-verify every special case below** — diff the new `elements.json`
   against the prior edition for the special-case slugs.
5. **Re-run the country-mapping audit** (see "Country name mapping").
6. **Regenerate audits** with `--audit` and eyeball the special-case sheets.

---

## The `2025e` estimated marker

**What:** USGS prints the latest MCS year with a superscript `e` (e.g.
`2025ᵉ`) because those figures are **preliminary estimates**, not finalized
reported data. The prior four years (2021–2024 in MCS 2026) are reported
actuals. We carry the marker into the data key: the last entry of
`YEAR_COLUMNS` is the string `"2025e"`, and `ElementRecord.latest_year ==
"2025e"`.

**Why it looks cryptic:** `2025e` is a *data key*, not a label. It appears in:
- `elements.json` — every `values` / `raw_values` / `price_quotes` dict keys
  on `"2025e"` (machine-readable, kept as-is).
- The viewer salient table — now rendered as `2025ᵉ` with a hover tooltip plus
  a legend line ("e = USGS estimate"). See `YEAR_LABELS` in viewer.js.
- `audit.md` — a one-line legend was added under the Salient Statistics header.
- The CSV does **not** use `2025e`. The summary columns are named
  `usgs_2025_total_*` (no `e`) per the public-column spec; the values in those
  columns are nonetheless the 2025-estimated figures.

**Refresh action:** when the window slides (MCS 2027 → `2026e`), update
`YEAR_COLUMNS`, viewer `YEARS`/`YEAR_LABELS`, and the audit header tuple. Grep
for the literal `2025e` across `src/`, `viewer/`, `tests/` to catch them all.

---

## Multi-column world-production tables (sub-commodity splits)

Two sheets split their World Production table into **sub-columns** — one
(prev, latest) pair per sub-commodity — instead of a single production column.
The parser captures these into `WorldProductionRow.sub_metal_production_latest`
(a `{sub_name: latest_value}` dict).

### Platinum-group metals — Palladium / Platinum sub-columns

**What:** The PGM "World Mine Production and Reserves" table is:

```
                Mine production              PGM reserves
                Palladium      Platinum
                2024   2025e   2024   2025e
United States   10,200 6,200   3,010  1,800   590,000
...
```

So each country has 4 production cells (2 metals × 2 years) + 1 reserves cell.

**Why bespoke:** the generic parser expects one (prev, latest) pair. It detects
the `Palladium` / `Platinum` sub-header row sitting under the `Mine production`
column-title and multiplies the column kinds.

**Where:**
- Detection + capture: [src/parser.py](../src/parser.py) `_parse_world_production`
  (`_looks_like_submetal_row`, `_infer_column_kinds` with `sub_metals`).
- Header-token recognition: `_is_header_token` accepts `… reserves`
  (for "PGM reserves") and `… capacity`.
- Alias routing: [src/pipeline.py](../src/pipeline.py) `_make_alias`
  (`kind == "grouped"`, `parent_slug == "platinum-group-metals"`).

**How the aliases consume it:**
- `palladium` / `platinum` aliases (config `parent_filter="Palladium"/"Platinum"`)
  rewrite `world_production[*].production_latest_year` to that metal's
  sub-column value, and filter import sources to that metal's category.
- `iridium` / `osmium` / `rhodium` / `ruthenium` have **no** per-country
  mine data (USGS doesn't break them out) → world_production blanked.
- Per-metal summary values (mined / imports / exports / consumption / NIR)
  come from `_pgm_fill_per_metal_summary`, which reads the parent's salient
  rows matched by metal name. **Price is intentionally NOT set** — PGM is
  quoted in $/troy oz but the column header is $/lb (unit mismatch).
- The **grouped parent row** (`platinum-group-metals`) collapses to ONE CSV
  row (see csv_export `_category_rows_for`), blanks per-country
  mine/refinery/capacity (metal-specific), keeps per-country **reserves**
  (group-level in the source), and shows the group-sum imports/exports.

**Verify:** South Africa 2025e — Palladium mine = 70,000, Platinum mine =
120,000 (they differ!). Reserves: Russia 11,000,000, South Africa 63,000,000.

### Iron and Steel — Pig iron / Raw steel sub-columns

**What:** The "World Production" table splits into Pig iron / Raw steel
sub-columns, same shape as PGM but with **no explicit column-title row** —
the `Pig iron` / `Raw steel` sub-headers sit directly under the
`World Production:` section header.

```
                Pig iron       Raw steel
                2024   2025e   2024   2025e
China           852    830     1,010  980
```

**Two bugs this exposed (both fixed — re-verify on refresh):**
1. **No "X production" column title.** Sub-metal detection now also fires when
   the *section header itself* is a production table (`header_is_production`
   in `_parse_world_production`), and `_infer_column_kinds` emits sub-metal
   kinds even with an empty `column_titles`.
2. **Header bbox overlap.** The `World Production:` line's bbox bottom (367.7pt)
   sat ~1pt *below* the `Pig iron`/`Raw steel` sub-header top (366.3pt), so the
   old `y_min = header_line.bbox[3]` filter excluded the sub-header band
   entirely. Fixed by using the header's **vertical center** as `y_min`. This
   is the kind of thing that can silently break if USGS nudges line spacing —
   if iron-and-steel sub-columns vanish on a refresh, check this first.

**Where:** [src/parser.py](../src/parser.py) `_parse_world_production`
(`y_min` calc + sub-metal detection); [src/pipeline.py](../src/pipeline.py)
`_postprocess_record` (parent) + `_make_alias` (sub-products).

**Consumption:**
- `iron-and-steel-pig-iron` / `iron-and-steel-raw-steel` aliases (config
  `kind="sub_product"`, `parent_filter="Pig iron"/"Raw steel"`) carry ONLY the
  primary_smelting summary (from the US salient row) + the per-country
  refinery block (from their sub-column). Everything else N/A.
- The **parent** `iron-and-steel` row: `primary_smelting` summary =
  Pig iron + Raw steel US salient (21 + 82 = 103); per-country refinery =
  sum of the two sub-columns (China 830 + 980 = 1,810); mined = N/A (both
  rows are post-mine smelting per the data owner).

**Verify:** China 2025e — Pig iron 830, Raw steel 980, parent 1,810.
US — Pig iron 21, Raw steel 82, parent 103.

---

## Titanium — two stacked salient sub-tables (sponge metal / TiO₂)

**What:** The sheet titled "TITANIUM AND TITANIUM DIOXIDE" packs **two complete
salient sub-tables** into one Salient Statistics block — `Titanium sponge metal:`
then `TiO2 pigment:` — each with its own Production / Imports / Exports /
Consumption / Price / NIR rows:

```
Titanium sponge metal:
  Production                  W   W   W   W   —
  Imports for consumption     ... ...        44,000
  Exports                                        63
  Consumption, apparent                      44,000
  Price, dollars per kilogram                    12
  Net import reliance ...                       100
TiO2 pigment:
  Production                              1,000,000
  Imports for consumption                  230,000
  Exports                                  330,000
  Consumption, apparent                    900,000
  Price, dollars per metric ton              3,200
  Net import reliance ...                        E   (net exporter)
```

**Why bespoke:** the generic summary treats the whole block as one commodity,
so it **blended** the two — `_latest_value_by_section` SUMMED imports
(44,000 + 230,000 = 274,000) and exports (330,063), while consumption / price /
NIR silently took only the *first* sub-table (sponge). Neither commodity's
figure was recoverable. (The `Titanium sponge metal:` / `TiO2 pigment:` group
headers are dropped by the generic salient parser — a data-row that is itself a
section header, like "Production", resets `current_subsection`, so they don't
survive as subsections. We don't fight that here; see below.)

**Decision (user, 2026-05-20):** mirror iron-and-steel — keep a `titanium`
parent **plus** two sub-product rows (3 rows total). Unlike iron-and-steel
(whose sub-products differ only in *production*), titanium's two sub-tables are
*complete*, so the sub-rows carry the **full** per-commodity summary, not just
production.

**Where:** [src/config.py](../src/config.py) (`titanium-sponge-metal`,
`titanium-dioxide` aliases, `parent_filter="sponge"/"dioxide"`);
[src/pipeline.py](../src/pipeline.py) `_postprocess_record` (parent de-blend),
`_titanium_salient_groups` + `_fill_titanium_group_summary` (split + per-group
summary), `_make_alias` (titanium branch — placed **before** the iron-and-steel
`sub_product` branch since titanium is also `sub_product` *with* a
`parent_filter`); [src/csv_export.py](../src/csv_export.py) `_category_rows_for`
(parent collapses to one bare row, like the PGM grouped parent).

**How the split works:**
- **Boundary detection** — the two sub-tables are concatenated in source order
  and the second restarts at `Production`, so `_titanium_salient_groups` splits
  at the first row whose `section` repeats one already seen. (Robust for the
  two-table shape; if a future edition merges the tables, the second group is
  empty and the dioxide row falls to all-N/A rather than crashing.)
- **Production placement** — sponge reduction / TiO₂ pigment manufacture are
  post-mine processing, so production lands in `primary_smelting_latest` (same
  column iron-and-steel uses). Sponge = 0 (US ceased 2024), TiO₂ = 1,000,000.
- **Import sources** — the parent's two categories (`Sponge metal`,
  `TiO pigment`) move to the matching sub-row; the de-blended parent shows none.
- **Price unit** — carried per sub-row (`$/kg` for sponge, `$/metric ton` for
  TiO₂) since the two differ. The NIR `E` (net exporter) sentinel on TiO₂
  survives into `latest_year_sentinels`.

**Verify:** parent `Titanium` — all summary cells N/A. `Titanium (sponge/metal)`
— primary_smelting 0, imports 44,000, exports 63, consumption 44,000, price 12,
NIR 100, Japan import 77%. `Titanium (dioxide)` — primary_smelting 1,000,000,
imports 230,000, exports 330,000, consumption 900,000, price 3,200, NIR `E`,
Canada import 45%. No titanium row shows the old 274,000 / 330,063 blend.

---

## Block placement (mine vs refinery)

**What:** Each element's world-production rows go into either the **Mine
Production** or the **Refinery Production** country block. USGS section titles
("World Production", "World Mine Production and Reserves", "World Refinery
Production and Capacity") don't carry a clean machine signal, so placement is
**hardcoded**.

**Where:** [src/csv_export.py](../src/csv_export.py) `ELEMENT_PRODUCTION_BLOCK`.

**Decisions (per data owner, 2026-05-19):**
- **Mine + Reserves:** antimony, aluminum, chromium, cobalt, copper, diamond,
  graphite, lithium, magnesium, manganese, molybdenum, nickel, niobium,
  rare-earths, silver, tantalum, tin, tungsten, vanadium, zinc,
  zirconium-and-hafnium, PGM (+ Pd/Pt aliases).
- **Refinery + Capacity:** bismuth, indium, tellurium, germanium, gallium,
  iron-and-steel (+ pig iron / raw steel). Gallium is "Primary Low-Purity
  Production" (a smelter-stage byproduct) → Refinery. Iron-and-steel pig iron
  & raw steel are post-mine smelting → Refinery.
- **None (no world table):** rhenium, silicon, titanium, abrasives, scandium.

**Capacity nuance:** bismuth's PDF has a "Production capacity" column but every
cell is `NA`, so the capacity block renders all N/A. Indium / tellurium /
gallium have real capacity values; the header is "Refinery capacity" /
"Production capacity" — `_is_header_token` accepts the `… capacity` suffix.

**Verify:** bismuth China refinery = 14,000, capacity = N/A. Indium China
capacity = 1,100. Antimony China mine = 40,000, reserves = 830,000.

---

## Per-form import rows ("Mechanism A")

**What:** A single-mineral sheet whose imports the PDF lists by **form**
(antimony: ore / oxide / metal; germanium: metal / dioxide; tin: refined /
scrap) emits one CSV row per import-source category. Each form row carries
**only that form's imports/exports + its import-source country shares**; the
mineral-wide summary (production, consumption, price, NIR) and the
world-production / reserves table live on a **bare parent/total row**
(`import_category=""`). This is the same parent + sub-row shape used for the
true multi-mineral groups (PGM, iron-and-steel, titanium) — here applied to
single minerals so a form row never repeats the sheet-wide import total.

**Why:** previously every form row repeated the sheet total (e.g. antimony's
`Oxide` row showed imports = 44,650, the all-forms total, instead of 39,000).
That's the "group sum on a sub-item" problem. See BACKLOG "Repeat values in
group/multi-form rows".

**Scope:** primaries with >1 import category **and no alias children** —
antimony, chromium, copper, germanium, magnesium, manganese, molybdenum,
nickel, niobium, rhenium, silicon, tantalum, tin, vanadium, zinc (15 sheets).
Group sheets that *have* aliases (abrasives, rare-earths, PGM,
zirconium-and-hafnium) are handled via their aliases instead, NOT here.

**Where:** [src/csv_export.py](../src/csv_export.py) — `_is_per_form_sheet`,
`_form_summary` / `_best_form_row` (category→salient-form matcher), and the
`_emit(... is_form=...)` dispatch in `build_rows`.

**How the matcher works:** the import-source category label is matched to a
salient import/export row by token overlap, after dropping the element name
(non-distinctive) and applying a crude singular stem (`ore`~`ores`). It is
**conservative** — an ambiguous tie or no overlap yields **N/A**, never a
guess. A `Total`/`Combined` category carries the sheet total. Sheets whose
salient does NOT break imports out by form (chromium, magnesium, niobium,
tantalum) therefore show N/A on the form rows; the total survives on the
parent (and on a `Total` category row when one exists).

**The bare total row.** Sheets with no `Total`/`Combined` import category
(copper, magnesium, manganese, nickel, tin) get a synthesized bare parent row
so the sheet total isn't lost. Sheets that already have one show the total on
both the parent and that category row (the category row keeps its own country
shares) — minor, intentional redundancy.

**Verify:** antimony — parent imports 44,650; `Oxide` form 39,000; `Ore and
concentrates` 600. magnesium — bare parent imports 82; all three form rows
N/A (no per-form salient). nickel — bare parent imports 145,000; `Primary
nickel` 100,000; `…scrap` N/A.

**Column note (2026-05-20):** the two summary columns
`usgs_2025_total_primary_smelting` / `usgs_2025_total_secondary_smelting` were
renamed to `…_primary_production` / `…_secondary_production` (the values cover
mine + smelter + chemical-process output, so "production" is more accurate than
"smelting"). The `ElementRecord` field names (`primary_smelting_latest`, …) and
the `latest_year_sentinels` keys are unchanged — only the CSV headers moved.

---

## Multi-mineral group members ("Mechanism B")

**What:** a few sheets cover **several distinct minerals** in one PDF and we
split them into per-mineral alias rows. Each member must carry only its own
mineral's figures; the group **parent** collapses to a bare sum row. Covers:

- **zirconium-and-hafnium** → `zirconium`, `hafnium`
- **abrasives** → `fused-aluminum-oxide`, `silicon-carbide`, `metallic-abrasives`
  (+ `superhard-materials`, an all-N/A proxy with no source line)
- (PGM and rare-earths are also grouped but predate this — PGM via its own
  branch, rare-earths via `kind="rare_earth"`.)

**Why:** members previously inherited the parent verbatim — `hafnium` showed the
combined Zr+Hf import total (18,294) and the zircon world table; `silicon-carbide`
showed the abrasives group total (261,000) and *all* abrasive import categories
(incl. fused-alumina). See BACKLOG "Group / multi-form repeat values".

**Where:** [src/config.py](../src/config.py) (`parent_filter` keyword +
`inherits_world_table` flag on each member; new fused/metallic aliases);
[src/pipeline.py](../src/pipeline.py) `_make_alias` group-member branch +
`_fill_group_member`; [src/csv_export.py](../src/csv_export.py)
`_category_rows_for` (parent collapse) and `_is_per_form_sheet` (members reuse
the Mechanism A per-form split).

**How a member is derived:** keep only the parent salient rows whose label
contains the member's `parent_filter` keyword, recompute the summary from that
subset (reusing the parser's section extractors), filter import categories to
the keyword, and keep the parent world table only if `inherits_world_table`
(zirconium owns the zircon "World Mine Production and Reserves"; everyone else →
N/A). Members with >1 import form additionally split per form (Mechanism A), so
zirconium's `compounds` row shows 1,300, not the 18,210 member total.

**Production column:** routed to `mined_` for the mine sheet
(zirconium-and-hafnium → zircon) and `primary_` for the manufactured sheet
(abrasives), matching the per-country block.

**Blanked-to-N/A members:** `superhard-materials` (abrasives proxy) and the
single-mineral downstream products (`diamond-powders`, `gallium-nitride`,
`graphite-anodes`, `lithium-batteries`) inherit prose/identity only — every
numeric field + world table + import sources is N/A (the `else` branch of
`_make_alias`). Rare-earth aliases likewise drop the group REO world table +
import sources (keeping only the per-element oxide price).

**Verify:** Hafnium bare imports 84 (unwrought 72 / wrought 12), world N/A.
Zirconium bare imports 18,210 / production 100,000, `compounds` row 1,300, China
mine 100 on the bare row. Silicon carbide bare imports 95,000 / production
30,000. `Zirconium and hafnium (grouped)` + `Abrasives (manufactured)` each one
row (imports 18,294 / 261,000). Cerium china reserves = N/A (was 44,000,000).

---

## Government Stockpile (summary column 9)

**What:** The "Government Stockpile" section is a small table with FY 2025 /
FY 2026 × Potential acquisitions / Potential disposals columns. We capture the
**FY 2025 Potential Acquisitions** value, summed across material rows.

**Where:** [src/parser.py](../src/parser.py) `_parse_government_stockpile`.

**Gotcha (fixed — re-verify):** the section often sits at the bottom of page 1
and the generic section-extractor walks past the page break, pulling in page
2's page-header (e.g. "COBALT") and the citation line ("…February 2026"). The
"2026" token then parses as a number and pollutes the sum. Fixed by confining
the parser to the **header's page**. If stockpile totals look inflated on a
refresh, check this page-bound filter.

**Verify:** antimony 700, tungsten 2,041, cobalt 60, lithium = N/A
("Not available"). Tin / zinc = 0 (em-dash acquisitions).

**Known gap (BACKLOG):** rare-earths under-counts — captures the 1,100t
Lanthanum table row but misses the prose mention of 300t NdPr + 450t NdFeB +
60t SmCo (those are narrative, not tabular).

---

## Country name mapping

**What:** USGS country labels are mapped to a fixed 94-entry canonical list;
non-matches are dropped from the CSV (but stay in `elements.json`).

**Where:** [src/countries.py](../src/countries.py) — `CANONICAL_COUNTRIES`,
`USGS_TO_CANONICAL`, `NON_COUNTRY_LABELS`, `map_country`.

**Mappings that matter (USGS → canonical):**
- `Korea, Republic of` / `Republic of Korea` → `South Korea`
- `Korea, North` → `North Korea`
- `Burma` → `Burma (Myanmar)`
- `Congo (Kinshasa)` → `Congo (Kinshasa) / DRC`
- `Côte d'Ivoire` (USGS uses a curly apostrophe) → `Côte d'Ivoire`
- Trailing commodity qualifiers stripped as a fallback: `Sweden (concentrate)`
  → `Sweden`, `United States (copper telluride)` → `United States`.

**Dropped on purpose:** `Other`, `Other countries`, `World total (rounded)`,
the scandium prose-as-country parser bug, and any country **not** in the
94-entry list (e.g. Algeria, Albania, most small islands). EU rollup was
**removed** in the 94-entry revision — Germany / France / Belgium etc. are now
individual columns. United States **is** a country column (it was dropped under
the earlier spec because the summary block covered it).

**Refresh action:** after re-running, list every USGS name that
`map_country()` sends to `None` and confirm none has material world-production
or reserves data being silently dropped. Kyrgyzstan was such a miss in the
204-entry spec (700t antimony + 260kt reserves) — it survived the cut to 94
entries, but the same audit should run each refresh. See BACKLOG
"Canonical country list audit".

---

## Rare earths (grouped sheet)

**What:** Structurally different from single-commodity sheets — `[ … ]` units
delimiter, two production rows (Mineral concentrates + Compounds and metals),
9 per-oxide price quotes, multi-row NIR. Per-element aliases (cerium, …,
yttrium) derive via `kind="rare_earth"`.

**Where:** [src/pipeline.py](../src/pipeline.py) `_make_alias`
(`kind == "rare_earth"`) + `_postprocess_record` (rare-earths price/NIR notes).

**Decisions:**
- No single representative price → `price_usd_per_pound_latest = None` on the
  parent (the 9 oxide quotes live in the detail panel).
- Light REEs with an oxide quote (Ce, La, Pr, Nd, Sm, Eu, Gd) get that price
  via `parent_filter`; heavy REEs without a quote get blanked (no false
  attribution).

See the extensive rare-earths audit notes in [../BACKLOG.md](../BACKLOG.md).

---

## Confirmed parser label-merging bugs (open in BACKLOG)

These are known wrong-but-not-yet-fixed; don't be surprised by them on a
refresh, and don't "fix" them without checking BACKLOG first:
- **Tantalum** — `NA` from a stockpile cell concatenates onto the next row's
  label (`"NA Consumption, apparent"`).
- **Rhenium** — Employment-number value prefixes the wrapped NIR label.
- **Chromium** — stainless-steel import-source list truncated (country-share
  parser drops entries joined by "and").
