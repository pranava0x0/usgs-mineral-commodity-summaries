"""Top-country coverage + mapping checks.

Emulates a manual "check each document for the top countries" audit for
China, Mexico, Canada, New Zealand, Australia, Japan, Korea:
  - mapping unit tests (USGS spelling -> canonical column);
  - live-CSV spot values verified against the source PDFs;
  - per-country coverage (each present country is captured across many sheets).

New Zealand is intentionally absent — it is not in the 94-country canonical
list AND appears in zero MCS 2026 sheets. The test pins both facts so a future
NZ-reporting edition is caught.
"""

from __future__ import annotations

import csv
import unittest

from src import config
from src.countries import CANONICAL_COUNTRIES, canonical_slugs, map_country

# Countries USGS writes with their canonical spelling.
_DIRECT = ["China", "Mexico", "Canada", "Australia", "Japan"]


class CountryMappingTests(unittest.TestCase):
    def test_direct_canonical_names_map_to_themselves(self) -> None:
        for c in _DIRECT:
            self.assertIn(c, CANONICAL_COUNTRIES)
            self.assertEqual(map_country(c), c)

    def test_korea_variants_map_to_south_north(self) -> None:
        self.assertEqual(map_country("Korea, Republic of"), "South Korea")
        self.assertEqual(map_country("Republic of Korea"), "South Korea")
        self.assertEqual(map_country("Korea, North"), "North Korea")

    def test_new_zealand_is_absent(self) -> None:
        # Not in the 94-country list and not reported by any MCS 2026 sheet.
        self.assertNotIn("New Zealand", CANONICAL_COUNTRIES)
        self.assertNotIn("new_zealand", canonical_slugs())
        self.assertIsNone(map_country("New Zealand"))

    def test_top_country_columns_exist(self) -> None:
        slugs = set(canonical_slugs())
        for s in ("china", "mexico", "canada", "australia", "japan",
                  "south_korea", "north_korea"):
            self.assertIn(s, slugs)

    def test_non_country_labels_drop(self) -> None:
        for label in ("Other", "others", "World total (rounded)"):
            self.assertIsNone(map_country(label))


class TopCountryDataTests(unittest.TestCase):
    """Spot-check verified (row, country-column, value) tuples against the live
    CSV — the same values a human would read off each commodity's PDF."""

    @classmethod
    def setUpClass(cls) -> None:
        path = config.PROCESSED_DIR / "elements.csv"
        if not path.exists():
            raise unittest.SkipTest("elements.csv not present — run `python -m src.pipeline` first")
        with path.open() as f:
            cls.rows = list(csv.DictReader(f))

    def _cell(self, name: str, col: str) -> str:
        row = next((r for r in self.rows if r["name"] == name), None)
        self.assertIsNotNone(row, f"CSV row {name!r} not found")
        return row[col]

    def test_verified_spot_values(self) -> None:
        # (CSV row name, country column, expected cell) — each cross-checked
        # against the source USGS PDF.
        cases = [
            # Japan
            ("Scandium", "japan__imports_share_pct", "89"),
            ("Titanium (sponge/metal)", "japan__imports_share_pct", "77"),
            # China
            ("Scandium", "china__imports_share_pct", "11"),
            ("Chromium (Stainless steel)", "china__imports_share_pct", "6"),
            ("Antimony (Oxide)", "china__imports_share_pct", "66"),
            ("Antimony", "china__mine_production", "40000"),
            ("Magnesium (Magnesium metal (99.8% purity))", "china__imports_share_pct", "6"),
            # India (sibling check on chromium's recovered comma-list)
            ("Chromium (Stainless steel)", "india__imports_share_pct", "11"),
            # Mexico
            ("Antimony (Ore and concentrates)", "mexico__imports_share_pct", "86"),
            # Canada
            ("Titanium (dioxide)", "canada__imports_share_pct", "45"),
            # Korea (USGS "Republic of Korea" -> south_korea column)
            ("Bismuth", "south_korea__imports_share_pct", "22"),
            ("Molybdenum (Ferromolybdenum)", "south_korea__imports_share_pct", "21"),
        ]
        for name, col, expected in cases:
            self.assertEqual(self._cell(name, col), expected, f"{name} :: {col}")

    def test_each_top_country_is_captured_across_many_sheets(self) -> None:
        """Coverage guard: each present top country must carry non-N/A data in
        at least N distinct CSV rows (across any of the 5 country blocks).
        Thresholds sit well below current actuals to avoid flakiness."""
        blocks = ("imports_share_pct", "mine_production", "refinery_production",
                  "capacity", "reserves")
        minimums = {
            "china": 30, "canada": 30, "australia": 15,
            "mexico": 12, "japan": 10, "south_korea": 10,
        }
        for slug, minimum in minimums.items():
            hits = 0
            for r in self.rows:
                if any(r.get(f"{slug}__{b}", "N/A") not in ("N/A", "") for b in blocks):
                    hits += 1
            self.assertGreaterEqual(
                hits, minimum,
                f"{slug} captured in only {hits} rows (expected >= {minimum})",
            )

    def test_new_zealand_has_no_columns(self) -> None:
        ny_cols = [c for c in self.rows[0].keys() if c.startswith("new_zealand__")]
        self.assertEqual(ny_cols, [])


class CountriesJsonArtifactTests(unittest.TestCase):
    """viewer/countries.json (the country-view axis) must stay a faithful copy
    of src/countries.py — single source of truth, no drift."""

    def test_viewer_countries_json_matches_source(self) -> None:
        import json
        path = config.VIEWER_DIR / "countries.json"
        if not path.exists():
            raise unittest.SkipTest("viewer/countries.json not generated — run the pipeline")
        data = json.loads(path.read_text(encoding="utf-8"))
        expected = [
            {"name": name, "slug": slug}
            for name, slug in zip(CANONICAL_COUNTRIES, canonical_slugs())
        ]
        self.assertEqual(data, expected)


if __name__ == "__main__":
    unittest.main()
