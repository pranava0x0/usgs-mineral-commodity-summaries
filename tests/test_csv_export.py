"""Regression test for the CSV exporter's long-format shape.

The CSV emits one row per (element, import-source category) so multi-category
sheets like antimony round-trip as 4 rows whose only differing data is the
country-share block. The viewer's JSON still keeps one record per element —
this test guards the CSV side.
"""

from __future__ import annotations

import csv
import io
import unittest

from src import csv_export
from src.models import (
    CountryShare,
    ElementRecord,
    ImportSourceCategory,
    WorldProductionRow,
)


def _antimony_fixture() -> ElementRecord:
    """A tiny ElementRecord that mirrors antimony's import-source shape.

    Uses just enough fields for the exporter to run; not a full parse.
    """
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
                    CountryShare(country="Italy", share_pct=9.0),
                    CountryShare(country="other", share_pct=5.0),
                ],
            ),
            ImportSourceCategory(
                category="Oxide",
                countries=[
                    CountryShare(country="China", share_pct=66.0),
                    CountryShare(country="Belgium", share_pct=16.0),
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
        world_production=[
            WorldProductionRow(country="China", production_latest_year=40000.0),
        ],
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
                    CountryShare(country="Germany", share_pct=13.0),
                ],
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

    def test_antimony_has_four_rows(self) -> None:
        antimony = [r for r in self.rows if r["slug"] == "antimony"]
        self.assertEqual(len(antimony), 4)
        cats = [r["import_category"] for r in antimony]
        self.assertEqual(
            cats,
            ["Ore and concentrates", "Oxide", "Unwrought metal and powder", "Total metal and oxide"],
        )

    def test_country_share_isolated_per_category(self) -> None:
        antimony = {r["import_category"]: r for r in self.rows if r["slug"] == "antimony"}
        # Ore-and-concentrates row has Mexico=86 but China=N/A
        self.assertEqual(antimony["Ore and concentrates"]["imports__mexico"], "86")
        self.assertEqual(antimony["Ore and concentrates"]["imports__china"], "N/A")
        # Oxide row has China=66 but Mexico=N/A
        self.assertEqual(antimony["Oxide"]["imports__china"], "66")
        self.assertEqual(antimony["Oxide"]["imports__mexico"], "N/A")

    def test_non_country_columns_identical_across_category_rows(self) -> None:
        antimony = [r for r in self.rows if r["slug"] == "antimony"]
        for col in ("primary_smelting_latest", "units_note", "world_prod__china__latest"):
            values = {r[col] for r in antimony}
            self.assertEqual(len(values), 1, f"{col} differs across antimony category rows: {values}")

    def test_bismuth_single_row_with_blank_category(self) -> None:
        bism = [r for r in self.rows if r["slug"] == "bismuth"]
        self.assertEqual(len(bism), 1)
        self.assertEqual(bism[0]["import_category"], "")
        self.assertEqual(bism[0]["imports__china"], "56")
        self.assertEqual(bism[0]["imports__germany"], "13")

    def test_flat_imports_column_axis(self) -> None:
        # No legacy imports__<cat>__<country> columns (those had >1 "__" segment).
        multi = [c for c in self.cols if c.startswith("imports__") and c.count("__") > 1]
        self.assertEqual(multi, [])

    def test_missing_values_render_as_na(self) -> None:
        """User instruction: every missing cell must read 'N/A' — never blank.

        The antimony fixture leaves most fields None (apparent_consumption,
        net_import_reliance, etc.); those must surface as 'N/A' so a CSV
        consumer can never confuse a missing reading with a present zero.
        """
        antimony = next(r for r in self.rows if r["slug"] == "antimony")
        # Numeric latest-year fields the fixture didn't set
        self.assertEqual(antimony["mined_production_latest"], "N/A")
        self.assertEqual(antimony["apparent_consumption_latest"], "N/A")
        self.assertEqual(antimony["net_import_reliance_pct_latest"], "N/A")
        # Text identity fields the fixture didn't set
        self.assertEqual(antimony["parent_slug"], "N/A")
        self.assertEqual(antimony["price_unit_note"], "N/A")
        # The country that's not in this row's category renders "N/A"
        self.assertEqual(antimony["imports__china"], "N/A")  # Ore-and-concentrates row
        # No bare empty values in numeric/country slots
        suspect_cols = [c for c in self.cols
                        if c.startswith(("imports__", "world_prod__", "world_reserves__",
                                         "salient__", "price__"))
                        and not c.endswith("_raw")]
        for c in suspect_cols:
            self.assertNotEqual(antimony[c], "",
                                f"{c!r} is blank for antimony — should be a value or 'N/A'")


if __name__ == "__main__":
    unittest.main()
