# issues.md

Bug log per CLAUDE.md §Issue tracking. One entry per defect; record root cause and fix commit.

## 2026-05-18 — initial bismuth pipeline

### #1 — Footnote-body text misclassified as superscript
- **Module**: `src/extractor.py`
- **Symptom**: Every entry under "Footnotes" in the JSON came out empty; "Fastmarkets." and an HTS-code line were misidentified as leading footnote markers.
- **Root cause**: Code bug — `SUPERSCRIPT_SIZE_MAX_PT` was set to 8.0pt, but the MCS 2026 PDF renders footnote body at 7.98pt (just below the threshold) while inline superscripts are 6.5pt and footnote-section markers are 4.98pt. The 8.0pt threshold caught footnote body text in the superscript bucket.
- **Fix**: Lowered the threshold to 7.0pt so footnote body (7.98pt) is treated as normal text and only the genuine markers (≤7pt) are flagged.
- **Status**: Fixed in initial scaffold (this session). Regression test: `tests/test_bismuth.py::test_footnotes` asserts non-empty footnote bodies.

### #2 — World-production header prose pulled in as data rows
- **Module**: `src/parser.py`
- **Symptom**: "Laos based on company and Government reports." appeared as a country row in the world-production table.
- **Root cause**: Code bug — the original token-stream parser had no way to distinguish the section's prose continuation from the table body, so it walked into both.
- **Fix**: Rewrote `_parse_world_production` to group lines by y-coordinate (bbox-based), so prose continuation (a single-cell band) is filtered out and country rows are the only multi-cell bands.
- **Status**: Fixed in initial scaffold. Regression test: `tests/test_bismuth.py::test_world_production`.

### #3 — "Secondary (scrap)e" footnote field was 'e'
- **Module**: `src/parser.py`
- **Symptom**: The YearSeries for "Secondary (scrap)" carried `footnote='e'`, which the user reads as "estimated" not "footnote e".
- **Root cause**: Code bug — `e` is a USGS estimation marker, not a referenced footnote. Mixing them confuses readers and the viewer.
- **Fix**: In `_parse_salient_stats`, only treat numeric trailing footnotes as `YearSeries.footnote`; the `e` marker is implicit in the row label.
- **Status**: Fixed. The estimated convention is described in footnote `e` in `record.footnotes`.

## 2026-05-18 — multi-element expansion (14 primary elements + 16 aliases)

### #4 — Antimony's Vietnam world-prod cells were merged into "220 220"
- **Module**: `src/extractor.py`, `src/parser.py`
- **Symptom**: `WARNING could not coerce token to float: '220 220'`; Vietnam's prev-year value came out as `None` instead of 220.
- **Root cause**: Code bug — PyMuPDF's line-level extraction (`get_text("dict")`) packs adjacent value cells separated only by small whitespace into a single span. The line-based parser saw one big "220 220" token instead of two.
- **Fix**: Added word-level extractor (`iter_words`) that uses `rawdict` so each whitespace-delimited token has its own bbox AND its leading superscript characters are dropped. The world-production parser now consumes words inside the section's y-range and clusters them into cells by proximity.
- **Status**: Fixed. `tests.test_antimony.AntimonyRecordTests.test_world_production_reserves` asserts Vietnam=220/220/54,000.

### #5 — Scandium's NIR row was misread as "consumption"
- **Module**: `src/parser.py`
- **Symptom**: Scandium's salient stats contained a label "consumption" with values [100,100,100,100,100] instead of "Net import reliance as a percentage of apparent consumption".
- **Root cause**: Code bug — the NIR label wraps across two PDF lines ("Net import reliance as a percentage of apparent" / "consumption"). The parser took only the last line as the label.
- **Fix**: Multi-line label merging in `_parse_salient_stats`: when the current label has no values immediately after it, try appending the next line. Use the *original* trailing-colon as the discriminator between true section headers (rare-earths' "Net import reliance ... :") and wrapped labels (scandium's continuation).
- **Status**: Fixed. `tests.test_antimony.ScandiumRecordTests.test_wrapped_nir_label_and_value` asserts NIR=100.

### #6 — Scandium price row had 4 of 5 values merged in one cell
- **Module**: `src/parser.py`
- **Symptom**: The scandium oxide price row got dropped because its first 4 values came through as a single span `"890–1,000 820–880 700–740 660–670"`.
- **Root cause**: Same PyMuPDF span-merging issue as #4, but in the salient-stats section where the parser uses lines (not words).
- **Fix**: Added `_expand_packed_value_lines` that splits any salient-stats TextLine whose text contains multiple whitespace-separated value tokens into one virtual TextLine per token (with interpolated bboxes).
- **Status**: Fixed. `tests.test_antimony.ScandiumRecordTests.test_packed_price_cells_split` covers it.

### #7 — Multi-category Import Sources regex over-matched at semicolons
- **Module**: `src/parser.py`
- **Symptom**: Antimony's import sources came out with category names like `'Italy, 9%; and other, 5%. Oxide'`.
- **Root cause**: Code bug — the regex looked for category labels after any "." OR ";" boundary, but USGS uses "." between categories and ";" between countries within a category.
- **Fix**: Tighten `_CATEGORY_HEAD` to anchor on "." only and forbid "%" inside the category label.
- **Status**: Fixed.

### #8 — Heavy REE aliases inherited the wrong default price
- **Module**: `src/pipeline.py`
- **Symptom**: Aliases like dysprosium/erbium/holmium picked up Lanthanum-oxide's $1/kg as their price.
- **Root cause**: Design bug — when no `parent_filter` matched, the alias was still inheriting the parent's first-row price.
- **Fix**: Aliases whose `parent_slug == "rare-earths"` and have no `parent_filter` blank their per-element numeric fields. Sub-product aliases (gallium-nitride, lithium-batteries, etc.) still inherit because the parent IS the single commodity that covers them.
- **Status**: Fixed. The dysprosium / holmium / yttrium rows now show "Not available" for price and aggregates rather than misleading lanthanum data.

### #9 — Molybdenum's world-table year header parsed as a country
- **Module**: `src/parser.py` (`_parse_world_production`)
- **Symptom**: A WorldProductionRow with `country='2024'` and `prev=2025.0` is emitted from the molybdenum sheet, polluting the country axis of the wide CSV with a `world_prod__2024__*` block.
- **Root cause**: Code bug — the bbox-based world-production parser doesn't filter out the year-header band (the row that just contains "2024" and "2025e" as column labels). For most sheets the header band sits inside the prose continuation filter; molybdenum's header band is structured enough to look like a data row.
- **Status**: Open. Not blocking — affects one country slot in the CSV. To fix: add a filter that drops any row whose `country` is purely numeric / a 4-digit year, or detect the header by its position immediately under the section title.

### #10 — CSV collapsed multi-category import sources into one row per element
- **Module**: `src/csv_export.py`
- **Symptom**: 20 USGS sheets break Import Sources into multiple commodity forms (antimony has 4 forms: Ore and concentrates / Oxide / Unwrought metal and powder / Total metal and oxide; abrasives has 7; chromium has 7; etc.). The exporter packed every form's country shares into a single element row using `imports__<cat>__<country>` columns, making it awkward to slice in pandas / Sheets.
- **Root cause**: Design choice — the original exporter chose wide-on-category. User feedback: the UX page is fine as one detail panel, but the CSV should be long on category.
- **Affected elements** (one CSV row per import-source category for each):
  - 7 categories: abrasives, silicon-carbide (alias), superhard-materials (alias), chromium
  - 4 categories: antimony, copper, manganese, niobium, tantalum, zinc
  - 3 categories: germanium, magnesium, molybdenum, rhenium, silicon, vanadium
  - 2 categories: diamond, diamond-powders (alias), nickel, tin
- **Audited surfaces (no fix needed elsewhere)**: `src/audit.py` (`write_audit_report` already loops `import_sources_by_category` into separate Markdown sub-blocks); `viewer/viewer.js` (`importSourcesBlock` already renders one mini-table per category); `data/processed/elements.json` already stores categories as a nested list with their own `countries`. CSV was the only flattened surface.
- **Fix**: Exporter now emits one row per `(element, import-source category)`. Country axis is flat (`imports__<country>`); new `import_category` identity column distinguishes the rows; world-production / reserves data is duplicated across an element's rows because USGS doesn't categorize it. Single-flat-list sheets (bismuth, graphite, indium, lithium, scandium, tellurium) still emit one row with `import_category=""`. Aliases inherit their parent's category set.
- **Status**: Fixed in this session. Regression coverage: `tests/test_csv_export.py` (5 tests using small fixtures, no PDF I/O).

### #11 — Stale elements.json was missing `kind` and `parent_slug` fields
- **Module**: `data/processed/elements.json` (artifact, not code)
- **Symptom**: The committed JSON had only 30 records and lacked `kind` / `parent_slug` for every element. Reading it back through pydantic silently filled defaults (`kind="primary"`, `parent_slug=None`), so a CSV regenerated from the stale JSON had `kind="primary"` for every alias (gallium-nitride, dysprosium, etc.).
- **Root cause**: The JSON was committed before the model added `kind`/`parent_slug`. Pydantic accepts the older shape because the fields have defaults, so the discrepancy is invisible at load time.
- **Fix**: Re-ran `python3 -m src.pipeline` against cached PDFs to regenerate `elements.json` (50 records: 29 primary, 6 sub_product, 15 rare_earth) and `elements.csv` (108 rows × 3706 cols). Aliases now carry correct kind/parent_slug.
- **Status**: Fixed in this session (data refresh). No code change required; the parser was already producing the field — only the on-disk artifact was stale.

### #12 — Country-share parser merges multiple countries when separator is "and"
- **Module**: `src/parser.py` (import-sources splitter)
- **Symptom**: Chromium's Ferrochromium row carries `"country": "Finland, 5%, and other"` instead of two entries (`Finland: 5%` + `other: 24%`); the Stainless steel row carries `"country": "Taiwan, 16%, Finland, 12%, India, 11%, China"` as one giant name. Similar smashing likely affects any USGS line that uses "and" as a separator between country shares.
- **Root cause**: Code bug — the country splitter only breaks on `,` / `;`, but USGS sometimes writes `..., 5%, and other, ...` or runs multiple countries with intervening percentages.
- **Status**: Open. Pre-existing (independent of #10). Surfaced while auditing #10 because the new long-format CSV makes per-category bad cells more visible. To fix: tokenise the line as `<country> <share>% (separator) ...` and split on the `<share>%` boundary rather than punctuation alone.

### #13 — Three primary sheets fail to fetch (404)
- **Module**: `src/config.py` (registry) / fetch URLs
- **Symptom**: Running `python3 -m src.pipeline` against the full registry fails for `platinum-group-metals`, `titanium`, and `zirconium-and-hafnium` with HTTP 404, and their aliases (iridium, platinum, hafnium, zirconium) are skipped as a consequence.
- **Root cause**: The MCS 2026 PDFs for those commodities are at different URLs than the registry's pattern assumes, or the slug doesn't match the USGS filename. (Spotted while regenerating data for #11.)
- **Status**: Open. Pre-existing — not introduced here. The other 11 primaries fetch fine.

### #11 — Scandium prose fragment parsed as a country name
- **Module**: `src/parser.py` (import-sources parser)
- **Symptom**: A new column `imports__although_there_are_no_domestic_trade_codes_for_scandium_materials_exclusively_shipping_records_indicated_scandium_oxide_was_imported_from_japan` appears in the wide CSV; the JSON also has this as a `country` value in `import_sources_*`. The text is the verbatim USGS prose explaining that scandium has no HTS code.
- **Root cause**: Code bug — the parser greedily reads the line after "Import Sources" as country/share data, but on scandium that line is a prose explanation, not a country list.
- **Status**: Open. Pre-existing (independent of #10). Was previously hidden behind the per-category column prefix. To fix: detect-and-skip lines that don't match the `<country>, <pct>%` shape before assigning them to `CountryShare`.
