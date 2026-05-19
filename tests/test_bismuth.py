"""Regression test for the bismuth pipeline.

This is the eval-as-loop test (CLAUDE.md §Testing) — every field the user
asked for is asserted against the literal values printed on the MCS sheet.
If we ever break extraction, this fails loudly.

Run:
    python -m unittest tests.test_bismuth
"""

from __future__ import annotations

import unittest

from src import parser
from src.parser import _to_float


class ToFloatTests(unittest.TestCase):
    def test_em_dash_is_zero(self) -> None:
        self.assertEqual(_to_float("—"), (0.0, "—"))

    def test_na_is_none(self) -> None:
        self.assertEqual(_to_float("NA"), (None, "NA"))
        self.assertEqual(_to_float("na"), (None, "NA"))
        self.assertEqual(_to_float("")[0], None)

    def test_comma_separated_int(self) -> None:
        self.assertEqual(_to_float("1,980")[0], 1980.0)
        self.assertEqual(_to_float("14,000")[0], 14000.0)

    def test_decimal(self) -> None:
        self.assertAlmostEqual(_to_float("3.74")[0], 3.74)

    def test_garbage_logs_and_returns_none(self) -> None:
        self.assertIsNone(_to_float("garbage")[0])

    def test_withheld_sentinel(self) -> None:
        self.assertEqual(_to_float("W"), (None, "W"))

    def test_net_exporter_sentinel(self) -> None:
        self.assertEqual(_to_float("E"), (None, "E"))

    def test_greater_than(self) -> None:
        v, raw = _to_float(">95")
        self.assertEqual(v, 95.0)
        self.assertEqual(raw, ">95")

    def test_less_than(self) -> None:
        v, raw = _to_float("<5")
        self.assertEqual(v, 5.0)
        self.assertEqual(raw, "<5")


class BismuthRecordTests(unittest.TestCase):
    """End-to-end: parse the cached bismuth PDF and check every reported value."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.record = parser.parse_element_pdf("bismuth")

    def test_identity(self) -> None:
        self.assertEqual(self.record.slug, "bismuth")
        self.assertEqual(self.record.name, "Bismuth")
        self.assertEqual(self.record.symbol, "Bi")
        self.assertTrue(self.record.source_url.endswith("mcs2026-bismuth.pdf"))
        self.assertEqual(self.record.pdf_page_count, 2)

    def test_units_note_verbatim(self) -> None:
        self.assertEqual(
            self.record.units_note,
            "(Data in metric tons unless otherwise specified)",
        )

    def test_latest_year_us_summary(self) -> None:
        # All 2025e values from the bismuth PDF, hand-verified
        self.assertIsNone(self.record.mined_production_latest)  # not reported for byproduct
        self.assertEqual(self.record.primary_smelting_latest, 0.0)
        self.assertEqual(self.record.secondary_smelting_latest, 80.0)
        self.assertEqual(self.record.imports_total_latest, 1500.0)
        self.assertEqual(self.record.exports_total_latest, 540.0)
        self.assertEqual(self.record.apparent_consumption_latest, 1000.0)
        self.assertEqual(self.record.price_usd_per_pound_latest, 20.0)
        self.assertEqual(self.record.net_import_reliance_pct_latest, 92.0)

    def test_salient_stats_has_every_row(self) -> None:
        labels = [r.label for r in self.record.salient_stats]
        # The non-section-header rows we expect from the bismuth sheet
        expected_substrings = [
            "Refinery", "Secondary (scrap)",
            "Total",  # imports total (footnote 1)
            "Apparent", "Reported",
            "Price, average, dollars per pound",
            "Stocks, yearend",
            "Net import reliance",
        ]
        for sub in expected_substrings:
            self.assertTrue(
                any(sub in l for l in labels),
                f"missing row containing {sub!r}; got {labels!r}",
            )

    def test_imports_and_exports_totals_2024(self) -> None:
        # second hand-verified year — 2024
        totals = {
            (r.label, r.footnote): r.values["2024"]
            for r in self.record.salient_stats
        }
        self.assertEqual(totals[("Total", "1")], 1800.0)
        self.assertEqual(totals[("Total", "2")], 1050.0)

    def test_import_sources(self) -> None:
        # Bismuth is single-category; flat list and the by-category list (length 1) agree.
        shares = {cs.country: cs.share_pct for cs in self.record.import_sources_flat}
        self.assertEqual(shares["China"], 56.0)
        self.assertEqual(shares["Republic of Korea"], 22.0)
        self.assertEqual(shares["Germany"], 13.0)
        self.assertEqual(shares["other"], 9.0)
        self.assertEqual(self.record.import_sources_range, "2021-24")
        self.assertEqual(len(self.record.import_sources_by_category), 1)
        self.assertIsNone(self.record.import_sources_by_category[0].category)

    def test_world_production(self) -> None:
        by_country = {row.country: row for row in self.record.world_production}
        self.assertEqual(by_country["China"].production_latest_year, 14000.0)
        self.assertEqual(by_country["China"].production_prev_year, 14000.0)
        self.assertEqual(by_country["Korea, Republic of"].production_latest_year, 1000.0)
        # Laos has footnote 7 ("Reported")
        self.assertEqual(by_country["Laos"].production_prev_year, 492.0)
        self.assertEqual(by_country["Laos"].production_latest_year, 500.0)
        self.assertIn("7", (by_country["Laos"].note or ""))
        self.assertEqual(by_country["World total (rounded)"].production_latest_year, 16000.0)
        # capacity column is "NA" everywhere for bismuth, so should be None
        for r in self.record.world_production:
            self.assertIsNone(r.capacity)
        # reserves not reported at country level for bismuth
        for r in self.record.world_production:
            self.assertIsNone(r.reserves)

    def test_footnotes(self) -> None:
        self.assertIn("Hong Kong", self.record.footnotes.get("6", ""))
        self.assertIn("Reported", self.record.footnotes.get("7", ""))
        self.assertIn("Fastmarkets", self.record.footnotes.get("4", ""))
        self.assertIn("Estimated", self.record.footnotes.get("e", ""))

    def test_price_footnote_is_captured(self) -> None:
        self.assertIn("Rotterdam", self.record.price_footnote_text or "")


if __name__ == "__main__":
    unittest.main()
