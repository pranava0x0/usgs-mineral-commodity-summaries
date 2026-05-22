"""Regression test for the CSV exporter's public-spec shape (May 2026).

Layout: 8 identity + 9 summary + 5 × 203 country = 1,032 cols. One row per
(element, import-source category). Country axis is the fixed 203-entry
canonical list with EU rollup; non-country labels are dropped.
"""

from __future__ import annotations

import csv
import io
import unittest

from src import csv_export
from src.countries import canonical_slugs
from src.models import (
    CountryShare,
    ElementRecord,
    ImportSourceCategory,
    WorldProductionRow,
    YearSeries,
)


def _antimony_fixture() -> ElementRecord:
    """A tiny ElementRecord that mirrors antimony's import-source shape."""
    return ElementRecord(
        slug="antimony",
        name="Antimony",
        symbol="Sb",
        kind="primary",
        source_url="https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-antimony.pdf",
        edition="MCS 2026",
        edition_date="2026-02",
        captured_at="2026-05-18",
        pdf_sha256="deadbeef",
        pdf_page_count=2,
        units_note="(Data in metric tons, antimony content, unless otherwise specified)",
        primary_smelting_latest=700.0,
        import_sources_by_category=[
            ImportSourceCategory(
                category="Ore and concentrates",
                countries=[
                    CountryShare(country="Mexico", share_pct=86.0),
                    CountryShare(country="Italy", share_pct=9.0),         # EU → rolls up
                    CountryShare(country="other", share_pct=5.0),         # dropped
                ],
            ),
            ImportSourceCategory(
                category="Oxide",
                countries=[
                    CountryShare(country="China", share_pct=66.0),
                    CountryShare(country="Belgium", share_pct=16.0),      # EU → rolls up
                ],
            ),
            ImportSourceCategory(
                category="Unwrought metal and powder",
                countries=[
                    CountryShare(country="China", share_pct=22.0),
                    CountryShare(country="India", share_pct=22.0),
                ],
            ),
            ImportSourceCategory(
                category="Total metal and oxide",
                countries=[
                    CountryShare(country="China", share_pct=55.0),
                    CountryShare(country="Belgium", share_pct=12.0),
                ],
            ),
        ],
        world_production_year_prev="2024",
        world_production_year_latest="2025e",
        world_production=[
            WorldProductionRow(
                country="China",
                production_prev_year=40000.0,
                production_latest_year=40000.0,
                reserves=830000.0,
            ),
        ],
        stockpile_fy2025_potential_acquisitions=700.0,
    )


def _bismuth_fixture() -> ElementRecord:
    """Single-flat-list element: one CSV row, import_category=''."""
    return ElementRecord(
        slug="bismuth",
        name="Bismuth",
        symbol="Bi",
        kind="primary",
        source_url="https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-bismuth.pdf",
        edition="MCS 2026",
        edition_date="2026-02",
        captured_at="2026-05-18",
        pdf_sha256="cafef00d",
        pdf_page_count=2,
        units_note="(Data in metric tons unless otherwise specified)",
        import_sources_by_category=[
            ImportSourceCategory(
                category=None,
                countries=[
                    CountryShare(country="China", share_pct=56.0),
                    CountryShare(country="Germany", share_pct=13.0),       # EU → rolls up
                ],
            ),
        ],
        world_production=[
            WorldProductionRow(
                country="China",
                production_prev_year=14000.0,
                production_latest_year=14000.0,
            ),
        ],
    )


def _read(columns: list[str], rows: list[dict[str, str]]) -> list[dict[str, str]]:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "") for c in columns})
    buf.seek(0)
    return list(csv.DictReader(buf))


class CsvLongFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [_antimony_fixture(), _bismuth_fixture()]
        cols, rows = csv_export.build_rows(self.records)
        self.cols = cols
        self.rows = _read(cols, rows)

    def test_total_column_count(self) -> None:
        """8 identity + 9 summary + 5 × 94 country = 487 columns.

        (User-revised spec 2026-05-19: replaces earlier 204-entry list with
        a focused 94-country alphabetical list — EU members listed
        individually, US is a regular country column, smaller territories
        dropped.)
        """
        self.assertEqual(len(self.cols), 487)

    def test_first_columns_are_identity_then_summary(self) -> None:
        # Identity (8)
        self.assertEqual(self.cols[:8], list(csv_export.IDENTITY_COLUMNS))
        # Summary (9)
        self.assertEqual(self.cols[8:17], list(csv_export.SUMMARY_COLUMNS))

    def test_country_blocks_appear_in_expected_order(self) -> None:
        slugs = canonical_slugs()
        n = len(slugs)                # 204 after Kyrgyzstan add-back
        # Block 1 — Import Sources
        self.assertEqual(self.cols[17], f"{slugs[0]}__imports_share_pct")
        self.assertEqual(self.cols[17 + n - 1], f"{slugs[-1]}__imports_share_pct")
        # Block 2 — Mine Production
        self.assertEqual(self.cols[17 + n], f"{slugs[0]}__mine_production")
        # Block 5 — Reserves (last)
        self.assertEqual(self.cols[-1], f"{slugs[-1]}__reserves")

    def test_antimony_has_parent_plus_form_rows(self) -> None:
        """Per-form layout: a bare parent/total row (import_category="") plus
        one form row per import category (Mechanism A)."""
        antimony = [r for r in self.rows if r["name"].startswith("Antimony")]
        self.assertEqual(len(antimony), 5)  # 1 parent + 4 form rows
        cats = [r["import_category"] for r in antimony]
        self.assertEqual(
            cats,
            ["", "Ore and concentrates", "Oxide", "Unwrought metal and powder", "Total metal and oxide"],
        )

    def test_multi_row_name_annotated_with_category(self) -> None:
        antimony_names = [r["name"] for r in self.rows if r["name"].startswith("Antimony")]
        self.assertEqual(
            antimony_names,
            [
                "Antimony",  # bare parent/total row
                "Antimony (Ore and concentrates)",
                "Antimony (Oxide)",
                "Antimony (Unwrought metal and powder)",
                "Antimony (Total metal and oxide)",
            ],
        )
        bismuth_names = [r["name"] for r in self.rows if r["name"] == "Bismuth"]
        self.assertEqual(bismuth_names, ["Bismuth"])

    def test_country_share_isolated_per_category(self) -> None:
        antimony = {r["import_category"]: r for r in self.rows if r["name"].startswith("Antimony")}
        # Mexico is in Ore-and-concentrates only
        self.assertEqual(antimony["Ore and concentrates"]["mexico__imports_share_pct"], "86")
        self.assertEqual(antimony["Oxide"]["mexico__imports_share_pct"], "N/A")
        # China is in Oxide / Unwrought / Total
        self.assertEqual(antimony["Oxide"]["china__imports_share_pct"], "66")
        self.assertEqual(antimony["Ore and concentrates"]["china__imports_share_pct"], "N/A")

    def test_eu_members_are_individual_columns(self) -> None:
        """User-revised spec (2026-05-19) drops the European-Union rollup —
        Belgium, Germany, Italy etc. each get their own column."""
        antimony = {r["import_category"]: r for r in self.rows if r["name"].startswith("Antimony")}
        # Italy 9% lands in italy__imports_share_pct, not a rollup
        self.assertEqual(antimony["Ore and concentrates"]["italy__imports_share_pct"], "9")
        # Belgium 16% similarly individual
        self.assertEqual(antimony["Oxide"]["belgium__imports_share_pct"], "16")
        # Bismuth's Germany 13% lands in germany column
        bism = next(r for r in self.rows if r["name"] == "Bismuth")
        self.assertEqual(bism["germany__imports_share_pct"], "13")
        # And there's no european_union column anywhere
        self.assertFalse(any(c.startswith("european_union") for c in self.cols))

    def test_united_states_is_an_individual_country_column(self) -> None:
        """User-revised spec promotes United States from "drop, summary-only"
        to a regular country column. The slug `united_states__*` must exist
        in every block."""
        for suffix in ("imports_share_pct", "mine_production",
                       "refinery_production", "capacity", "reserves"):
            self.assertIn(f"united_states__{suffix}", self.cols)

    def test_kyrgyzstan_present(self) -> None:
        """Kyrgyzstan was absent from the user-provided spec xlsx but USGS
        reports it as a material antimony producer (700 t mine + 260,000 t
        reserves). We added it back after-the-fact; the columns must exist."""
        self.assertIn("kyrgyzstan__mine_production", self.cols)
        self.assertIn("kyrgyzstan__reserves", self.cols)
        self.assertIn("kyrgyzstan__imports_share_pct", self.cols)

    def test_non_country_labels_dropped(self) -> None:
        """`other`/`Other countries`/`World total (rounded)` USGS rows are
        not represented anywhere in the country axis."""
        antimony = next(r for r in self.rows if r["name"].startswith("Antimony"))
        # No "other" column anywhere
        self.assertFalse(any("other_imports" in c for c in self.cols))
        self.assertFalse(any(c.startswith("world_total") for c in self.cols))

    def test_summary_column_population(self) -> None:
        antimony = next(r for r in self.rows if r["name"].startswith("Antimony"))
        self.assertEqual(antimony["usgs_2025_total_primary_production"], "700")
        # Government stockpile populates
        self.assertEqual(antimony["government_stockpile_fy2025_potential_acquisitions"], "700")
        # Unset summary fields become N/A
        self.assertEqual(antimony["usgs_2025_total_mined_production"], "N/A")

    def test_per_form_summary_and_world_on_parent_only(self) -> None:
        """Per-form layout: the mineral-wide summary + world-production table
        live on the bare parent row; form rows carry only their own
        imports/exports + import shares, everything else N/A."""
        antimony = {r["import_category"]: r for r in self.rows if r["name"].startswith("Antimony")}
        parent = antimony[""]
        # Parent carries summary + world production + reserves.
        self.assertEqual(parent["usgs_2025_total_primary_production"], "700")
        self.assertEqual(parent["china__mine_production"], "40000")
        self.assertEqual(parent["china__reserves"], "830000")
        # Form rows have those blanked (world tables are mineral-wide, not per-form).
        for cat in ("Ore and concentrates", "Oxide"):
            self.assertEqual(antimony[cat]["usgs_2025_total_primary_production"], "N/A")
            self.assertEqual(antimony[cat]["china__mine_production"], "N/A")
            self.assertEqual(antimony[cat]["china__reserves"], "N/A")
        # Identity columns stay identical across every row.
        units = {r["units_note"] for r in antimony.values()}
        self.assertEqual(len(units), 1)

    def test_sentinel_merged_into_value_column(self) -> None:
        rec = _antimony_fixture()
        rec.mined_production_latest = None
        rec.latest_year_sentinels = {"mined_production": "W"}
        rec.net_import_reliance_pct_latest = 50.0
        rec.latest_year_sentinels["net_import_reliance"] = ">50"
        cols, rows = csv_export.build_rows([rec])
        rows = _read(cols, rows)
        antimony = next(r for r in rows if r["name"].startswith("Antimony"))
        self.assertEqual(antimony["usgs_2025_total_mined_production"], "W")
        self.assertEqual(antimony["net_import_reliance_pct"], ">50")
        # No companion *_sentinel / *_raw columns
        leaked = [c for c in cols if c.endswith(("_sentinel", "_raw"))]
        self.assertEqual(leaked, [])

    def test_bismuth_single_row_with_blank_category(self) -> None:
        bism = [r for r in self.rows if r["name"] == "Bismuth"]
        self.assertEqual(len(bism), 1)
        self.assertEqual(bism[0]["import_category"], "")
        self.assertEqual(bism[0]["china__imports_share_pct"], "56")
        # bismuth slug → "refinery" block, so world_production lands there
        self.assertEqual(bism[0]["china__refinery_production"], "14000")
        # Mine block is N/A for bismuth (refinery-classified)
        self.assertEqual(bism[0]["china__mine_production"], "N/A")

    def test_missing_values_render_as_na(self) -> None:
        antimony = next(r for r in self.rows if r["name"].startswith("Antimony"))
        # Numeric fields the fixture didn't set
        self.assertEqual(antimony["usgs_2025_total_mined_production"], "N/A")
        self.assertEqual(antimony["consumption_apparent"], "N/A")
        self.assertEqual(antimony["net_import_reliance_pct"], "N/A")
        # Text identity fields the fixture didn't set
        self.assertEqual(antimony["price_unit_note"], "N/A")
        # No blank cells in country slots
        import re as _re
        country_col = _re.compile(
            r"__(imports_share_pct|mine_production|refinery_production|capacity|reserves)$"
        )
        suspect_cols = [c for c in self.cols if country_col.search(c)]
        for c in suspect_cols:
            self.assertNotEqual(antimony[c], "",
                                f"{c!r} is blank for antimony — should be a value or 'N/A'")


def _per_form_fixture() -> ElementRecord:
    """Antimony-like single-mineral sheet WITH per-form salient rows, so the
    Mechanism A category->form value extraction can be exercised."""
    return ElementRecord(
        slug="antimony", name="Antimony", symbol="Sb", kind="primary",
        source_url="https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-antimony.pdf",
        edition="MCS 2026", edition_date="2026-02", captured_at="2026-05-20",
        pdf_sha256="x", pdf_page_count=2,
        units_note="(Data in metric tons unless otherwise specified)",
        latest_year="2025e",
        imports_total_latest=44650.0, exports_total_latest=3281.0,
        mined_production_latest=None, primary_smelting_latest=700.0,
        net_import_reliance_pct_latest=91.0,
        salient_stats=[
            YearSeries(label="Ore and concentrates", section="Imports for consumption",
                       values={"2025e": 600.0}, raw_values={"2025e": "600"}),
            YearSeries(label="Oxide", section="Imports for consumption",
                       values={"2025e": 39000.0}, raw_values={"2025e": "39000"}),
            YearSeries(label="Unwrought, powder", section="Imports for consumption",
                       values={"2025e": 4500.0}, raw_values={"2025e": "4500"}),
            YearSeries(label="Oxide", section="Exports",
                       values={"2025e": 2900.0}, raw_values={"2025e": "2900"}),
        ],
        import_sources_by_category=[
            ImportSourceCategory(category="Ore and concentrates",
                                 countries=[CountryShare(country="Mexico", share_pct=86.0)]),
            ImportSourceCategory(category="Oxide",
                                 countries=[CountryShare(country="China", share_pct=66.0)]),
            ImportSourceCategory(category="Unwrought metal and powder",
                                 countries=[CountryShare(country="China", share_pct=22.0)]),
            ImportSourceCategory(category="Total metal and oxide",
                                 countries=[CountryShare(country="China", share_pct=55.0)]),
        ],
        world_production=[WorldProductionRow(country="China",
                                             production_latest_year=40000.0, reserves=830000.0)],
    )


def _no_total_category_fixture() -> ElementRecord:
    """Nickel-like sheet: import categories but NO 'Total' category, and only
    one form broken out in the salient. The sheet total must survive on a bare
    parent row, and the unmatched form must be N/A (not the sheet total)."""
    return ElementRecord(
        slug="nickel", name="Nickel", symbol="Ni", kind="primary",
        source_url="https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-nickel.pdf",
        edition="MCS 2026", edition_date="2026-02", captured_at="2026-05-20",
        pdf_sha256="x", pdf_page_count=2,
        units_note="(Data in metric tons unless otherwise specified)",
        latest_year="2025e",
        imports_total_latest=145000.0, exports_total_latest=56000.0,
        mined_production_latest=10000.0,
        salient_stats=[
            YearSeries(label="Primary", section="Imports for consumption",
                       values={"2025e": 100000.0}, raw_values={"2025e": "100000"}),
        ],
        import_sources_by_category=[
            ImportSourceCategory(category="Primary nickel",
                                 countries=[CountryShare(country="Canada", share_pct=40.0)]),
            ImportSourceCategory(category="Nickel-containing scrap",
                                 countries=[CountryShare(country="Canada", share_pct=20.0)]),
        ],
        world_production=[WorldProductionRow(country="Canada",
                                             production_latest_year=10000.0)],
    )


class MechanismAPerFormTests(unittest.TestCase):
    """Mechanism A: single-mineral sheets emit a bare parent/total row plus
    per-import-form rows that carry only their own imports/exports + shares."""

    def _rows(self, rec: ElementRecord) -> dict[str, dict[str, str]]:
        cols, rows = csv_export.build_rows([rec])
        rows = _read(cols, rows)
        return {r["import_category"]: r for r in rows}

    def test_parent_row_holds_summary_and_world(self) -> None:
        rows = self._rows(_per_form_fixture())
        parent = rows[""]
        self.assertEqual(parent["name"], "Antimony")
        self.assertEqual(parent["imports_for_consumption_total"], "44650")
        self.assertEqual(parent["exports_total"], "3281")
        self.assertEqual(parent["usgs_2025_total_primary_production"], "700")
        self.assertEqual(parent["net_import_reliance_pct"], "91")
        self.assertEqual(parent["china__mine_production"], "40000")
        self.assertEqual(parent["china__reserves"], "830000")

    def test_form_rows_carry_only_their_form_value(self) -> None:
        rows = self._rows(_per_form_fixture())
        # Oxide grabs the oxide salient value, NOT the sheet total.
        self.assertEqual(rows["Oxide"]["imports_for_consumption_total"], "39000")
        self.assertEqual(rows["Oxide"]["exports_total"], "2900")
        self.assertEqual(rows["Ore and concentrates"]["imports_for_consumption_total"], "600")
        # Fuzzy match: category "Unwrought metal and powder" -> salient "Unwrought, powder".
        self.assertEqual(rows["Unwrought metal and powder"]["imports_for_consumption_total"], "4500")
        # Everything non-form on a form row is N/A.
        for col in ("usgs_2025_total_mined_production", "usgs_2025_total_primary_production",
                    "consumption_apparent", "net_import_reliance_pct",
                    "china__mine_production", "china__reserves"):
            self.assertEqual(rows["Oxide"][col], "N/A", f"Oxide {col} should be N/A")
        # Import shares still land on the form row.
        self.assertEqual(rows["Oxide"]["china__imports_share_pct"], "66")
        self.assertEqual(rows["Ore and concentrates"]["mexico__imports_share_pct"], "86")

    def test_total_category_row_carries_sheet_total(self) -> None:
        rows = self._rows(_per_form_fixture())
        self.assertEqual(rows["Total metal and oxide"]["imports_for_consumption_total"], "44650")
        self.assertEqual(rows["Total metal and oxide"]["exports_total"], "3281")

    def test_no_total_category_gets_bare_parent_row(self) -> None:
        rows = self._rows(_no_total_category_fixture())
        # A bare parent row preserves the sheet total even with no Total category.
        self.assertIn("", rows)
        self.assertEqual(rows[""]["name"], "Nickel")
        self.assertEqual(rows[""]["imports_for_consumption_total"], "145000")
        self.assertEqual(rows[""]["usgs_2025_total_mined_production"], "10000")
        # Matched form gets its value; unmatched form is N/A (never the sheet total).
        self.assertEqual(rows["Primary nickel"]["imports_for_consumption_total"], "100000")
        self.assertEqual(rows["Nickel-containing scrap"]["imports_for_consumption_total"], "N/A")

    def test_renamed_columns_present(self) -> None:
        self.assertIn("usgs_2025_total_primary_production", csv_export.SUMMARY_COLUMNS)
        self.assertIn("usgs_2025_total_secondary_production", csv_export.SUMMARY_COLUMNS)
        self.assertNotIn("usgs_2025_total_primary_smelting", csv_export.SUMMARY_COLUMNS)
        self.assertNotIn("usgs_2025_total_secondary_smelting", csv_export.SUMMARY_COLUMNS)


class IronAndSteelSpecialCasingTests(unittest.TestCase):
    """End-to-end coverage for the iron-and-steel parent + sub-product
    special casing (user spec 2026-05-19). Pulls the live CSV produced
    by `python -m src.pipeline` rather than synthesizing a fixture —
    the special casing is in `_postprocess_record` + `_make_alias`,
    which sit upstream of `csv_export.build_rows`, so a fixture-only
    test would skip the code we care about.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import csv
        from src import config
        path = config.PROCESSED_DIR / "elements.csv"
        if not path.exists():
            raise unittest.SkipTest("elements.csv not present — run `python -m src.pipeline` first")
        with path.open() as f:
            reader = csv.DictReader(f)
            cls.rows = list(reader)

    def _row(self, name: str) -> dict[str, str]:
        return next(r for r in self.rows if r["name"] == name)

    def test_parent_row_primary_smelting_is_sum(self) -> None:
        """Iron and Steel parent's `usgs_2025_total_primary_production` equals
        Pig iron (21) + Raw steel (82) = 103. `mined_production` stays N/A
        (both rows are post-mine smelting per user spec)."""
        parent = self._row("Iron and Steel")
        self.assertEqual(parent["usgs_2025_total_primary_production"], "103")
        self.assertEqual(parent["usgs_2025_total_mined_production"], "N/A")

    def test_sub_product_rows_only_have_primary_and_country(self) -> None:
        """Pig iron / Raw steel rows: only `primary_smelting` summary and
        the refinery_production per-country block. Everything else N/A.

        Crucially the per-country values DIFFER between sub-products — the
        USGS World Production table splits into Pig iron / Raw steel
        sub-columns, so China shows pig iron 830 vs raw steel 980.
        """
        cases = (
            ("Iron and Steel (Pig iron)", "21", "830"),
            ("Iron and Steel (Raw steel)", "82", "980"),
        )
        for name, expected_primary, expected_china in cases:
            row = self._row(name)
            self.assertEqual(row["usgs_2025_total_primary_production"], expected_primary)
            # mined → N/A (was previously echoing the primary value)
            self.assertEqual(row["usgs_2025_total_mined_production"], "N/A")
            # All other summary fields blanked
            for c in ("usgs_2025_total_secondary_production",
                      "imports_for_consumption_total", "exports_total",
                      "consumption_apparent", "price_metal_average_dollars_per_pound",
                      "net_import_reliance_pct",
                      "government_stockpile_fy2025_potential_acquisitions"):
                self.assertEqual(row[c], "N/A", f"{name}: {c} should be N/A but is {row[c]!r}")
            # Per-country imports_share_pct block fully N/A
            import_cols = [c for c in row.keys() if c.endswith("__imports_share_pct")]
            self.assertTrue(import_cols)
            for c in import_cols:
                self.assertEqual(row[c], "N/A", f"{name}: {c} should be N/A")
            # Refinery block shows THIS sub-commodity's per-country value
            self.assertEqual(row["china__refinery_production"], expected_china,
                             f"{name}: china refinery should be {expected_china}")

    def test_parent_per_country_is_sum_of_sub_commodities(self) -> None:
        """Iron and Steel parent's per-country refinery = Pig iron + Raw
        steel (China 830 + 980 = 1810), consistent with the summary
        primary_smelting = 21 + 82 = 103."""
        parent = self._row("Iron and Steel")
        self.assertEqual(parent["china__refinery_production"], "1810")
        self.assertEqual(parent["united_states__refinery_production"], "103")


class TitaniumSplitTests(unittest.TestCase):
    """End-to-end coverage for the titanium parent + sub-product split.

    The "TITANIUM AND TITANIUM DIOXIDE" sheet stacks two complete salient
    sub-tables (sponge metal, TiO2 pigment). The generic summary blended
    them (imports 44,000 + 230,000 = 274,000; consumption/price/NIR from
    the first sub-table only). The split de-blends the parent and fans the
    two commodities into their own rows. Like the iron-and-steel test, this
    pulls the live CSV because the special casing sits in
    `_postprocess_record` + `_make_alias`, upstream of `build_rows`.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import csv
        from src import config
        path = config.PROCESSED_DIR / "elements.csv"
        if not path.exists():
            raise unittest.SkipTest("elements.csv not present — run `python -m src.pipeline` first")
        with path.open() as f:
            cls.rows = list(csv.DictReader(f))

    def _rows_named(self, name: str) -> list[dict[str, str]]:
        return [r for r in self.rows if r["name"] == name]

    def _row(self, name: str) -> dict[str, str]:
        matches = self._rows_named(name)
        self.assertEqual(len(matches), 1, f"expected exactly one {name!r} row, got {len(matches)}")
        return matches[0]

    def test_three_titanium_rows_total(self) -> None:
        """Parent + two sub-rows = 3 rows (was 2 blended rows)."""
        names = [r["name"] for r in self.rows if r["name"].startswith("Titanium")]
        self.assertEqual(
            sorted(names),
            ["Titanium", "Titanium (dioxide)", "Titanium (sponge/metal)"],
        )

    def test_parent_summary_is_deblended(self) -> None:
        """The parent keeps prose/identity but its blended summary numbers
        are nulled — the misleading 274,000 / 330,063 blend is gone."""
        parent = self._row("Titanium")
        self.assertEqual(parent["kind"], "primary")
        self.assertEqual(parent["import_category"], "")
        for c in ("usgs_2025_total_mined_production",
                  "usgs_2025_total_primary_production",
                  "usgs_2025_total_secondary_production",
                  "imports_for_consumption_total", "exports_total",
                  "consumption_apparent", "price_metal_average_dollars_per_pound",
                  "net_import_reliance_pct"):
            self.assertEqual(parent[c], "N/A", f"parent {c} should be N/A but is {parent[c]!r}")

    def test_no_titanium_row_carries_the_blend(self) -> None:
        """The summed-blend values (imports 274,000 / exports 330,063) must
        not appear on any titanium row anymore."""
        for r in self.rows:
            if not r["name"].startswith("Titanium"):
                continue
            self.assertNotEqual(r["imports_for_consumption_total"], "274000")
            self.assertNotEqual(r["exports_total"], "330063")

    def test_sponge_metal_row(self) -> None:
        """Titanium (sponge/metal): sponge sub-table figures + sponge imports."""
        row = self._row("Titanium (sponge/metal)")
        self.assertEqual(row["kind"], "sub_product")
        self.assertEqual(row["import_category"], "Sponge metal")
        # Production (US sponge ceased 2024) lands in primary_smelting = 0.
        self.assertEqual(row["usgs_2025_total_primary_production"], "0")
        self.assertEqual(row["imports_for_consumption_total"], "44000")
        self.assertEqual(row["exports_total"], "63")
        self.assertEqual(row["consumption_apparent"], "44000")
        self.assertEqual(row["price_metal_average_dollars_per_pound"], "12")
        self.assertEqual(row["net_import_reliance_pct"], "100")
        # Mine block stays N/A (titanium has no per-country world table).
        self.assertEqual(row["usgs_2025_total_mined_production"], "N/A")
        # Sponge import shares isolated to this row.
        self.assertEqual(row["japan__imports_share_pct"], "77")
        # TiO2's Canada share must NOT leak onto the sponge row.
        self.assertEqual(row["canada__imports_share_pct"], "N/A")

    def test_dioxide_row(self) -> None:
        """Titanium (dioxide): TiO2 sub-table figures, NIR = E (net exporter)."""
        row = self._row("Titanium (dioxide)")
        self.assertEqual(row["kind"], "sub_product")
        self.assertEqual(row["import_category"], "TiO pigment")
        self.assertEqual(row["usgs_2025_total_primary_production"], "1000000")
        self.assertEqual(row["imports_for_consumption_total"], "230000")
        self.assertEqual(row["exports_total"], "330000")
        self.assertEqual(row["consumption_apparent"], "900000")
        self.assertEqual(row["price_metal_average_dollars_per_pound"], "3200")
        # USGS marks TiO2 pigment NIR as "E" (net exporter) — sentinel survives.
        self.assertEqual(row["net_import_reliance_pct"], "E")
        # TiO2 import shares isolated to this row.
        self.assertEqual(row["canada__imports_share_pct"], "45")
        self.assertEqual(row["china__imports_share_pct"], "11")
        # Sponge's Japan share must NOT leak onto the dioxide row.
        self.assertEqual(row["japan__imports_share_pct"], "N/A")


class MechanismBGroupTests(unittest.TestCase):
    """Mechanism B: true multi-mineral group sheets. Each member alias carries
    only its own mineral's data (and splits per import form); the group parent
    collapses to a bare sum row. Pulls the live CSV (the logic is in
    pipeline._make_alias, upstream of build_rows)."""

    @classmethod
    def setUpClass(cls) -> None:
        import csv
        from src import config
        path = config.PROCESSED_DIR / "elements.csv"
        if not path.exists():
            raise unittest.SkipTest("elements.csv not present — run `python -m src.pipeline` first")
        with path.open() as f:
            cls.rows = list(csv.DictReader(f))

    def _named(self, *names: str) -> dict[str, dict[str, str]]:
        want = set(names)
        return {r["import_category"]: r for r in self.rows if r["name"] in want}

    def _exact(self, name: str) -> list[dict[str, str]]:
        return [r for r in self.rows if r["name"] == name or r["name"].startswith(name + " (")]

    def test_group_parents_collapse_to_one_sum_row(self) -> None:
        for name, imp, exp in (
            ("Zirconium and hafnium (grouped)", "18294", "12322"),
            ("Abrasives (manufactured)", "261000", "34600"),
        ):
            rs = [r for r in self.rows if r["name"] == name]
            self.assertEqual(len(rs), 1, f"{name} should collapse to one row")
            self.assertEqual(rs[0]["import_category"], "")
            self.assertEqual(rs[0]["imports_for_consumption_total"], imp)
            self.assertEqual(rs[0]["exports_total"], exp)

    def test_hafnium_carries_only_hafnium(self) -> None:
        rows = {r["import_category"]: r for r in self._exact("Hafnium")}
        self.assertEqual(rows[""]["imports_for_consumption_total"], "84")   # not the 18,294 group total
        self.assertEqual(rows["Hafnium, unwrought"]["imports_for_consumption_total"], "72")
        self.assertEqual(rows["Hafnium, wrought"]["imports_for_consumption_total"], "12")
        # Hafnium has no world table.
        self.assertEqual(rows[""]["china__mine_production"], "N/A")
        self.assertEqual(rows[""]["china__reserves"], "N/A")

    def test_zirconium_carries_only_zirconium_and_keeps_zircon_world(self) -> None:
        rows = {r["import_category"]: r for r in self._exact("Zirconium")}
        self.assertEqual(rows[""]["imports_for_consumption_total"], "18210")
        self.assertEqual(rows[""]["usgs_2025_total_mined_production"], "100000")
        # per-form values, not the member total
        self.assertEqual(rows["Zirconium ores and concentrates"]["imports_for_consumption_total"], "16000")
        self.assertEqual(rows["Zirconium, compounds"]["imports_for_consumption_total"], "1300")
        # zirconium owns the zircon mine table (on the bare row)
        self.assertEqual(rows[""]["china__mine_production"], "100")
        # a sibling's import form must not appear
        self.assertNotIn("Hafnium, unwrought", rows)

    def test_abrasives_members_split(self) -> None:
        sic = {r["import_category"]: r for r in self._exact("Silicon carbide")}
        self.assertEqual(sic[""]["imports_for_consumption_total"], "95000")
        self.assertEqual(sic[""]["usgs_2025_total_primary_production"], "30000")
        fused = {r["import_category"]: r for r in self._exact("Fused aluminum oxide")}
        self.assertEqual(fused[""]["imports_for_consumption_total"], "150000")
        self.assertEqual(fused[""]["usgs_2025_total_primary_production"], "20000")
        metallic = self._exact("Metallic abrasives")
        self.assertEqual(metallic[0]["imports_for_consumption_total"], "16000")
        self.assertEqual(metallic[0]["usgs_2025_total_primary_production"], "160000")
        # No silicon-carbide row carries a fused-alumina category (no sibling leak).
        self.assertFalse(any("fused" in r["import_category"].lower() for r in self._exact("Silicon carbide")))

    def test_superhard_and_downstream_are_all_na(self) -> None:
        for name in ("Superhard materials", "Gallium nitride (GaN)", "Diamond powders",
                     "Graphite anodes", "Lithium batteries"):
            rs = self._exact(name)
            self.assertEqual(len(rs), 1, f"{name} should be a single bare row")
            r = rs[0]
            for c in ("imports_for_consumption_total", "exports_total",
                      "usgs_2025_total_mined_production", "usgs_2025_total_primary_production",
                      "consumption_apparent", "net_import_reliance_pct"):
                self.assertEqual(r[c], "N/A", f"{name}: {c} should be N/A")

    def test_rare_earth_aliases_drop_group_world_table(self) -> None:
        """REE aliases keep their oxide price but must NOT inherit the group's
        REO mine production / reserves (was: China 270,000 / 44,000,000)."""
        cerium = next(r for r in self.rows if r["name"] == "Cerium")
        self.assertEqual(cerium["imports_for_consumption_total"], "N/A")
        self.assertEqual(cerium["china__mine_production"], "N/A")
        self.assertEqual(cerium["china__reserves"], "N/A")
        self.assertEqual(cerium["price_metal_average_dollars_per_pound"], "1.71")  # own oxide price kept
        # The group's lanthanum stockpile (1,100) must NOT be attributed per-REE.
        for name in ("Cerium", "Dysprosium", "Lanthanum", "Yttrium"):
            row = next(r for r in self.rows if r["name"] == name)
            self.assertEqual(
                row["government_stockpile_fy2025_potential_acquisitions"], "N/A",
                f"{name} should not inherit the group stockpile",
            )


if __name__ == "__main__":
    unittest.main()
