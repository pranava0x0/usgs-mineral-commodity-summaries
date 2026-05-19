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

    def test_antimony_has_four_rows(self) -> None:
        antimony = [r for r in self.rows if r["name"].startswith("Antimony")]
        self.assertEqual(len(antimony), 4)
        cats = [r["import_category"] for r in antimony]
        self.assertEqual(
            cats,
            ["Ore and concentrates", "Oxide", "Unwrought metal and powder", "Total metal and oxide"],
        )

    def test_multi_row_name_annotated_with_category(self) -> None:
        antimony_names = [r["name"] for r in self.rows if r["name"].startswith("Antimony")]
        self.assertEqual(
            antimony_names,
            [
                "Antimony (Ore and concentrates)",
                "Antimony (Oxide)",
                "Antimony (Unwrought metal and powder)",
                "Antimony (Total metal and oxide)",
            ],
        )
        bismuth_names = [r["name"] for r in self.rows if r["name"].startswith("Bismuth")]
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
        self.assertEqual(antimony["usgs_2025_total_primary_smelting"], "700")
        # Government stockpile populates
        self.assertEqual(antimony["government_stockpile_fy2025_potential_acquisitions"], "700")
        # Unset summary fields become N/A
        self.assertEqual(antimony["usgs_2025_total_mined_production"], "N/A")

    def test_non_country_columns_identical_across_category_rows(self) -> None:
        antimony = [r for r in self.rows if r["name"].startswith("Antimony")]
        # World production / reserves are duplicated across all category rows.
        for col in ("usgs_2025_total_primary_smelting", "units_note",
                    "china__mine_production", "china__reserves"):
            values = {r[col] for r in antimony}
            self.assertEqual(len(values), 1, f"{col} differs across antimony category rows: {values}")

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
        """Iron and Steel parent's `usgs_2025_total_primary_smelting` equals
        Pig iron (21) + Raw steel (82) = 103. `mined_production` stays N/A
        (both rows are post-mine smelting per user spec)."""
        parent = self._row("Iron and Steel")
        self.assertEqual(parent["usgs_2025_total_primary_smelting"], "103")
        self.assertEqual(parent["usgs_2025_total_mined_production"], "N/A")

    def test_sub_product_rows_only_have_primary_and_country(self) -> None:
        """Pig iron / Raw steel rows: only `primary_smelting` summary and
        the refinery_production per-country block. Everything else N/A."""
        for name, expected in (("Iron and Steel (Pig iron)", "21"),
                               ("Iron and Steel (Raw steel)", "82")):
            row = self._row(name)
            self.assertEqual(row["usgs_2025_total_primary_smelting"], expected)
            # mined → N/A (was previously echoing the primary value)
            self.assertEqual(row["usgs_2025_total_mined_production"], "N/A")
            # All other summary fields blanked
            for c in ("usgs_2025_total_secondary_smelting",
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
            # Refinery block IS populated — China is a known iron-and-steel producer
            self.assertEqual(row["china__refinery_production"], "830")


if __name__ == "__main__":
    unittest.main()
