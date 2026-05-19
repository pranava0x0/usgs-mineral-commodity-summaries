"""Regression tests for the long-format CSV exporter.

Each row of `elements.csv` is one (element, salient-stats form) pair. The
exporter doesn't try to round-trip per-country imports or per-element
latest-year summary — those live in `elements.json`. The CSV's job is
to make the salient-stats matrix pandas-friendly without 800 sparse
form-specific columns.
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
    YearSeries,
)


def _antimony_fixture() -> ElementRecord:
    """A tiny ElementRecord with a representative salient_stats set."""
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
        price_unit_note="Price, metal, average, dollars per pound",
        salient_stats=[
            YearSeries(
                label="Mine (recoverable antimony)",
                section="Production",
                values={"2021": 0.0, "2022": 0.0, "2023": 0.0, "2024": 0.0, "2025e": None},
                raw_values={"2021": "—", "2022": "—", "2023": "—", "2024": "—", "2025e": "W"},
            ),
            YearSeries(
                label="Oxide",
                section="Imports for consumption",
                values={"2021": 19100.0, "2022": 17000.0, "2023": 14000.0, "2024": 24000.0, "2025e": 39000.0},
                raw_values={"2021": "19100", "2022": "17000", "2023": "14000", "2024": "24000", "2025e": "39000"},
            ),
            YearSeries(
                label="Antimony articles",
                section="Imports for consumption",
                footnote="1",
                values={"2021": 514.0, "2022": 1790.0, "2023": 1620.0, "2024": 323.0, "2025e": 350.0},
            ),
        ],
        # Imports / world-production deliberately set but NOT exposed by the
        # exporter — they live in elements.json. The fixture proves the
        # exporter ignores them rather than crashing.
        import_sources_by_category=[
            ImportSourceCategory(
                category="Oxide",
                countries=[CountryShare(country="China", share_pct=66.0)],
            ),
        ],
        world_production=[
            WorldProductionRow(country="China", production_latest_year=40000.0),
        ],
    )


def _dysprosium_fixture() -> ElementRecord:
    """Heavy REE alias with no salient_stats — should still emit one placeholder row."""
    return ElementRecord(
        slug="dysprosium",
        name="Dysprosium",
        symbol="Dy",
        kind="rare_earth",
        parent_slug="rare-earths",
        source_url="https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-rare-earths.pdf",
        edition="MCS 2026",
        edition_date="2026-02",
        captured_at="2026-05-18",
        pdf_sha256="cafef00d",
        pdf_page_count=2,
        units_note="[Data in metric tons, rare-earth-oxide (REO) equivalent, unless otherwise specified]",
        salient_stats=[],  # heavy REE — no per-element rows
    )


def _read(columns: list[str], rows: list[dict[str, str]]) -> list[dict[str, str]]:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "") for c in columns})
    buf.seek(0)
    return list(csv.DictReader(buf))


class LongFormatCsvTests(unittest.TestCase):
    def setUp(self) -> None:
        records = [_antimony_fixture(), _dysprosium_fixture()]
        cols, rows = csv_export.build_rows(records)
        self.cols = cols
        self.rows = _read(cols, rows)

    def test_one_row_per_salient_form(self) -> None:
        """Antimony has 3 salient rows → 3 CSV rows."""
        antimony = [r for r in self.rows if r["name"] == "Antimony"]
        self.assertEqual(len(antimony), 3)
        labels = [r["label"] for r in antimony]
        self.assertEqual(labels, ["Mine (recoverable antimony)", "Oxide", "Antimony articles"])

    def test_year_columns_are_generic(self) -> None:
        """Year columns are bare 2021..2025e — no form prefix.

        This is the whole point of the long format: a "2021" column with
        a Silicon Carbide row, instead of a `production__silicon_carbide__2021`
        column with one populated row out of 50.
        """
        for yr in ("2021", "2022", "2023", "2024", "2025e"):
            self.assertIn(yr, self.cols, f"missing year column {yr}")

    def test_sentinel_preserved_in_year_cell(self) -> None:
        """USGS sentinel tokens (W, em-dash → 0) appear in the year columns."""
        mine = next(r for r in self.rows if r["label"] == "Mine (recoverable antimony)")
        self.assertEqual(mine["2025e"], "W")    # withheld → sentinel verbatim
        self.assertEqual(mine["2024"], "0")     # em-dash → 0 (USGS "produced zero")

    def test_footnote_column_carries_label_footnote(self) -> None:
        """Row labels that USGS marked with a numbered footnote round-trip."""
        articles = next(r for r in self.rows if r["label"] == "Antimony articles")
        self.assertEqual(articles["footnote"], "1")
        mine = next(r for r in self.rows if r["label"] == "Mine (recoverable antimony)")
        self.assertEqual(mine["footnote"], "")  # no footnote → empty

    def test_no_salient_stats_emits_placeholder_row(self) -> None:
        """Heavy REE aliases (Dysprosium, Erbium, …) have empty salient_stats.
        We still emit one row per element so they're discoverable by name in
        the CSV — section/label/years are blank to signal 'see parent record'.
        """
        dysprosium = [r for r in self.rows if r["name"] == "Dysprosium"]
        self.assertEqual(len(dysprosium), 1)
        self.assertEqual(dysprosium[0]["section"], "")
        self.assertEqual(dysprosium[0]["label"], "")
        self.assertEqual(dysprosium[0]["2025e"], "")

    def test_no_per_country_columns(self) -> None:
        """The long-format CSV deliberately doesn't expose per-country
        imports or world-production data. Those live in elements.json. A
        column like 'china_imports_share_pct' or 'australia_production_2025'
        showing up would be a regression.
        """
        leaked = [c for c in self.cols if c.endswith(("_imports_share_pct", "_capacity", "_reserves"))
                                       or "_production_" in c]
        self.assertEqual(leaked, [], f"per-country columns leaked: {leaked[:5]}")

    def test_no_latest_summary_columns(self) -> None:
        """Latest-year summary fields don't appear in the long-format CSV —
        they're per-element facts, and duplicating them across every form
        row would be waste. They remain in elements.json."""
        leaked = [c for c in self.cols if c.endswith("_latest")]
        self.assertEqual(leaked, [], f"latest-year columns leaked: {leaked[:5]}")

    def test_compact_column_count(self) -> None:
        """The whole point of the rewrite: tight, fixed-shape header.
        13 columns, not 2,300+."""
        self.assertEqual(len(self.cols), 13)


if __name__ == "__main__":
    unittest.main()
