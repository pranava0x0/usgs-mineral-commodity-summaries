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
        world_production_year_prev="2024",
        world_production_year_latest="2025e",
        world_production=[
            WorldProductionRow(
                country="China",
                production_prev_year=40000.0,
                production_latest_year=40000.0,
            ),
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
        antimony = [r for r in self.rows if r["name"].startswith("Antimony")]
        self.assertEqual(len(antimony), 4)
        cats = [r["import_category"] for r in antimony]
        self.assertEqual(
            cats,
            ["Ore and concentrates", "Oxide", "Unwrought metal and powder", "Total metal and oxide"],
        )

    def test_multi_row_name_annotated_with_category(self) -> None:
        """When an element is split across multiple CSV rows (one per import
        category), each row's `name` cell carries the disambiguating category
        in parentheses so a viewer / Sheets user can tell rows apart without
        having to read the separate `import_category` column. Single-row
        elements (bismuth) keep the bare name.
        """
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
        # Bismuth has one row → no parenthesised tail.
        bismuth_names = [r["name"] for r in self.rows if r["name"].startswith("Bismuth")]
        self.assertEqual(bismuth_names, ["Bismuth"])

    def test_country_share_isolated_per_category(self) -> None:
        antimony = {r["import_category"]: r for r in self.rows if r["name"].startswith("Antimony")}
        # Ore-and-concentrates row has Mexico=86 but China=N/A
        self.assertEqual(antimony["Ore and concentrates"]["mexico_imports_share_pct"], "86")
        self.assertEqual(antimony["Ore and concentrates"]["china_imports_share_pct"], "N/A")
        # Oxide row has China=66 but Mexico=N/A
        self.assertEqual(antimony["Oxide"]["china_imports_share_pct"], "66")
        self.assertEqual(antimony["Oxide"]["mexico_imports_share_pct"], "N/A")

    def test_non_country_columns_identical_across_category_rows(self) -> None:
        antimony = [r for r in self.rows if r["name"].startswith("Antimony")]
        # World production is duplicated across all category rows for an
        # element (USGS doesn't categorise it), so the year-tagged column
        # must read the same on every row.
        for col in ("primary_smelting_latest", "units_note", "china_production_2025e"):
            values = {r[col] for r in antimony}
            self.assertEqual(len(values), 1, f"{col} differs across antimony category rows: {values}")

    def test_sentinel_merged_into_value_column(self) -> None:
        """Mixed-type cells: USGS sentinels (W/E/>N/<N/NA) appear verbatim in
        the value column. No companion *_sentinel or *_raw columns exist.

        The exporter previously emitted `mined_production_latest=N/A` PLUS
        `mined_production_latest_sentinel=W` for a withheld antimony cell;
        consumers had to read both. The single mixed-type column simplifies
        that — the value column carries the sentinel verbatim and pandas users
        coerce to numeric via `pd.to_numeric(col, errors="coerce")` when they
        want NaN-on-sentinel semantics.
        """
        # Synthesize a fresh fixture so the assertion is hermetic. Antimony
        # in MCS 2026 has `mined_production_latest=None` with the W sentinel.
        from src.csv_export import build_rows  # local — keep top-level imports tidy
        rec = _antimony_fixture()
        rec.mined_production_latest = None
        rec.latest_year_sentinels = {"mined_production": "W"}
        rec.net_import_reliance_pct_latest = 50.0
        rec.latest_year_sentinels["net_import_reliance"] = ">50"
        # Replace records and rebuild
        cols, rows = build_rows([rec])
        rows = _read(cols, rows)
        antimony = next(r for r in rows if r["name"].startswith("Antimony"))

        # Sentinel surfaces in the value column
        self.assertEqual(antimony["mined_production_latest"], "W")
        self.assertEqual(antimony["net_import_reliance_pct_latest"], ">50")

        # Companion columns are gone
        leaked = [c for c in cols if c.endswith(("_sentinel", "_raw"))]
        self.assertEqual(leaked, [], f"sentinel/raw companion columns leaked: {leaked[:5]}")

    def test_world_production_columns_use_pdf_years(self) -> None:
        """User instruction: country world-prod columns are named after the
        actual year tokens captured from the PDF's table sub-header.

        The antimony fixture sets year_prev='2024' and year_latest='2025e'.
        The exporter must emit china_production_2024 and china_production_2025e
        — never the placeholders 'prev'/'latest' or a bare 'world_prod__*'
        legacy column.
        """
        self.assertIn("china_production_2024", self.cols)
        self.assertIn("china_production_2025e", self.cols)
        # Legacy column names are gone
        legacy = [c for c in self.cols if c.startswith(("world_prod__", "world_reserves__", "imports__"))]
        self.assertEqual(legacy, [], f"legacy columns leaked: {legacy[:5]}")
        # Values populate
        antimony = next(r for r in self.rows if r["name"].startswith("Antimony"))
        self.assertEqual(antimony["china_production_2024"], "40000")
        self.assertEqual(antimony["china_production_2025e"], "40000")

    def test_bismuth_single_row_with_blank_category(self) -> None:
        bism = [r for r in self.rows if r["name"] == "Bismuth"]
        self.assertEqual(len(bism), 1)
        self.assertEqual(bism[0]["import_category"], "")
        self.assertEqual(bism[0]["china_imports_share_pct"], "56")
        self.assertEqual(bism[0]["germany_imports_share_pct"], "13")

    def test_missing_values_render_as_na(self) -> None:
        """User instruction: every missing cell must read 'N/A' — never blank.

        The antimony fixture leaves most fields None (apparent_consumption,
        net_import_reliance, etc.); those must surface as 'N/A' so a CSV
        consumer can never confuse a missing reading with a present zero.
        """
        antimony = next(r for r in self.rows if r["name"].startswith("Antimony"))
        # Numeric latest-year fields the fixture didn't set
        self.assertEqual(antimony["mined_production_latest"], "N/A")
        self.assertEqual(antimony["apparent_consumption_latest"], "N/A")
        self.assertEqual(antimony["net_import_reliance_pct_latest"], "N/A")
        # Text identity fields the fixture didn't set
        self.assertEqual(antimony["price_unit_note"], "N/A")
        # The country that's not in this row's category renders "N/A"
        self.assertEqual(antimony["china_imports_share_pct"], "N/A")  # Ore-and-concentrates row
        # No bare empty values in per-country slots. Match per-country column
        # families specifically and skip *_raw (genuinely empty if no sentinel)
        # and *_sentinel (a different "withheld marker" column-family entirely).
        import re as _re
        country_col = _re.compile(
            r"_(imports_share_pct|production_\d{4}e?|capacity|reserves)$"
        )
        suspect_cols = [c for c in self.cols
                        if country_col.search(c) and not c.endswith("_raw")]
        for c in suspect_cols:
            self.assertNotEqual(antimony[c], "",
                                f"{c!r} is blank for antimony — should be a value or 'N/A'")


if __name__ == "__main__":
    unittest.main()
