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
