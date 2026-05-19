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
        """8 identity + 9 summary + 5 × 203 country = 1,032 columns."""
        self.assertEqual(len(self.cols), 1032)

    def test_first_columns_are_identity_then_summary(self) -> None:
        # Identity (8)
        self.assertEqual(self.cols[:8], list(csv_export.IDENTITY_COLUMNS))
        # Summary (9)
        self.assertEqual(self.cols[8:17], list(csv_export.SUMMARY_COLUMNS))

    def test_country_blocks_appear_in_expected_order(self) -> None:
        slugs = canonical_slugs()
        # Block 1 — Import Sources
        self.assertEqual(self.cols[17], f"{slugs[0]}__imports_share_pct")
        self.assertEqual(self.cols[17 + 202], f"{slugs[202]}__imports_share_pct")
        # Block 2 — Mine Production
        self.assertEqual(self.cols[220], f"{slugs[0]}__mine_production")
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

    def test_eu_rollup_for_member_states(self) -> None:
        """USGS country rows for EU members (Belgium, Germany, Italy) aggregate
        into the canonical 'European Union' column."""
        antimony = {r["import_category"]: r for r in self.rows if r["name"].startswith("Antimony")}
        # Italy (9%) in Ore-and-concentrates
        self.assertEqual(antimony["Ore and concentrates"]["european_union__imports_share_pct"], "9")
        # Belgium (16%) in Oxide
        self.assertEqual(antimony["Oxide"]["european_union__imports_share_pct"], "16")
        # Bismuth's Germany (13%) rolls up
        bism = next(r for r in self.rows if r["name"] == "Bismuth")
        self.assertEqual(bism["european_union__imports_share_pct"], "13")

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


if __name__ == "__main__":
    unittest.main()
