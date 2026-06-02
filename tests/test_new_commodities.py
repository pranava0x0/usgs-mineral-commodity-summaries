"""Regression tests for commodities added 2026-06-02 to align with the
**2025 USGS Critical Minerals List** (BACKLOG §"New ideas" #1b).

Ten sheets were added: boron, lead, phosphate, potash (new on the 2025 list)
plus arsenic, barite, beryllium, cesium, fluorspar, rubidium (2022-list
leftovers). Values below are hand-verified against the MCS 2026 PDFs (cached
under data/raw/ as fixtures).

Also covers three parser fixes shipped alongside:
  - `XX` ("Not applicable") recognized as a sentinel (boron, arsenic use it).
  - Bounded import-source shares ("Peru, >99%") no longer dropped (phosphate).
  - Wrapped unit sub-headers no longer mis-banded as world-table rows
    (arsenic's "(arsenic trioxide, / gross weight)").

Run:
    python -m unittest tests.test_new_commodities
"""

from __future__ import annotations

import unittest

from src import parser
from src.parser import _to_float, _world_cell_has_data


class XXSentinelTests(unittest.TestCase):
    """`XX` = USGS "Not applicable" — distinct from NA, must not warn-and-guess."""

    def test_xx_is_none_with_raw_preserved(self) -> None:
        self.assertEqual(_to_float("XX"), (None, "XX"))
        self.assertEqual(_to_float("xx"), (None, "XX"))

    def test_world_cell_has_data_recognizes_sentinels_not_prose(self) -> None:
        for good in ("0", "1,900", ">10,000,000", "—", "NA", "W", "E", "XX"):
            self.assertTrue(_world_cell_has_data(good), good)
        for junk in ("", None, "(arsenic trioxide,", "gross weight)", "Large"):
            self.assertFalse(_world_cell_has_data(junk), junk)


class BoronRecordTests(unittest.TestCase):
    """Boron — new on the 2025 list. US production withheld; net exporter."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.record = parser.parse_element_pdf("boron")

    def test_identity_and_units(self) -> None:
        self.assertEqual(self.record.name, "Boron")
        self.assertEqual(self.record.symbol, "B")
        self.assertEqual(
            self.record.units_note,
            "(Data in thousand metric tons unless otherwise specified)",
        )

    def test_summary(self) -> None:
        # US is a net exporter of borates (NIR = E); production is withheld.
        self.assertEqual(self.record.net_import_reliance_pct_latest, None)
        self.assertEqual(self.record.imports_total_latest, 205.0)
        self.assertEqual(self.record.exports_total_latest, 860.0)

    def test_import_sources_turkey_dominant(self) -> None:
        # Boron lists its sources under a named "All forms" category (not the
        # unnamed flat list), so read across categories.
        shares = {
            cs.country: cs.share_pct
            for cat in self.record.import_sources_by_category
            for cs in cat.countries
        }
        self.assertEqual(shares["Turkey"], 90.0)
        self.assertEqual(shares["Bolivia"], 6.0)

    def test_world_table_turkey_refined_borates(self) -> None:
        by = {r.country: r for r in self.record.world_production}
        self.assertEqual(by["Turkey, refined borates"].production_latest_year, 1500.0)


class LeadRecordTests(unittest.TestCase):
    """Lead — new on the 2025 list. Large secondary (recycled) production."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.record = parser.parse_element_pdf("lead")

    def test_summary(self) -> None:
        self.assertEqual(self.record.mined_production_latest, 280.0)
        self.assertEqual(self.record.secondary_smelting_latest, 1000.0)
        self.assertEqual(self.record.net_import_reliance_pct_latest, 33.0)

    def test_world_table(self) -> None:
        by = {r.country: r for r in self.record.world_production}
        self.assertEqual(by["United States"].production_latest_year, 280.0)
        self.assertEqual(by["United States"].reserves, 4600.0)
        self.assertEqual(by["China"].production_latest_year, 1900.0)


class PotashRecordTests(unittest.TestCase):
    """Potash — new on the 2025 list. Canada dominates production."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.record = parser.parse_element_pdf("potash")

    def test_summary(self) -> None:
        self.assertEqual(self.record.imports_total_latest, 5600.0)
        self.assertEqual(self.record.net_import_reliance_pct_latest, 92.0)

    def test_world_table_canada_leads(self) -> None:
        by = {r.country: r for r in self.record.world_production}
        self.assertEqual(by["Canada"].production_latest_year, 15000.0)
        self.assertEqual(by["United States"].reserves, 970000.0)


class BerylliumRecordTests(unittest.TestCase):
    """Beryllium — US is the leading producer. World reserves NA (prose-only)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.record = parser.parse_element_pdf("beryllium")

    def test_summary(self) -> None:
        self.assertEqual(self.record.mined_production_latest, 230.0)
        self.assertEqual(self.record.imports_total_latest, 10.0)
        self.assertEqual(self.record.exports_total_latest, 15.0)

    def test_world_table_and_prose_not_mixed(self) -> None:
        # The World Resources prose block must NOT leak into the world table:
        # only real countries + the world total survive.
        by = {r.country: r for r in self.record.world_production}
        self.assertEqual(by["United States"].production_latest_year, 230.0)
        self.assertEqual(by["China"].production_latest_year, 77.0)
        self.assertIn("World total (rounded)", by)
        for country in by:
            self.assertTrue(country[0].isalpha() or country.startswith("World"))


class PhosphateImportSourceFixTests(unittest.TestCase):
    """Bounded share regression: "Peru, >99%" must be recovered, not dropped."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.record = parser.parse_element_pdf("phosphate")

    def test_peru_import_share_recovered(self) -> None:
        shares = {cs.country: cs.share_pct for cs in self.record.import_sources_flat}
        # The ">" bound is dropped to a plain float (share_pct is numeric),
        # mirroring _to_float(">95") -> 95.0. The point is Peru is no longer lost.
        self.assertEqual(shares.get("Peru"), 99.0)

    def test_world_table_has_no_junk_rows(self) -> None:
        for r in self.record.world_production:
            self.assertTrue(r.country[0].isalpha(), f"junk world row: {r.country!r}")


class ArsenicWorldRowGuardTests(unittest.TestCase):
    """Wrapped unit sub-header must not appear as a world-table 'country'."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.record = parser.parse_element_pdf("arsenic")

    def test_no_unit_subheader_rows(self) -> None:
        countries = [r.country for r in self.record.world_production]
        self.assertNotIn("(arsenic trioxide,", countries)
        self.assertNotIn("gross weight)", countries)
        # Real data still present.
        by = {r.country: r for r in self.record.world_production}
        self.assertEqual(by["China"].production_latest_year, 24000.0)
        self.assertEqual(by["Peru"].production_prev_year, 31000.0)


class ProseOnlySheetTests(unittest.TestCase):
    """Cesium and rubidium are qualitative sheets (like scandium): USGS reports
    no salient-stats table and no world table — only prose + a units note.
    Asserting 0 rows guards against a future parser change inventing data."""

    def _assert_prose_only(self, slug: str) -> None:
        rec = parser.parse_element_pdf(slug)
        self.assertEqual(len(rec.salient_stats), 0, f"{slug} salient should be empty")
        self.assertEqual(len(rec.world_production), 0, f"{slug} world should be empty")
        self.assertTrue(rec.units_note, f"{slug} should still capture the units note")
        self.assertTrue(
            rec.domestic_use_summary, f"{slug} should capture the narrative prose"
        )

    def test_cesium(self) -> None:
        self._assert_prose_only("cesium")

    def test_rubidium(self) -> None:
        self._assert_prose_only("rubidium")


if __name__ == "__main__":
    unittest.main()
