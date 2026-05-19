"""Regression test for the antimony pipeline.

Antimony exercises the parser features that bismuth doesn't touch:
- Multi-form salient stats (5 import forms, 5 export forms, no Total row).
- Multi-category Import Sources (Ore / Oxide / Unwrought / Total metal-and-oxide).
- World production with a Reserves column.
- "W" sentinel values for withheld US mine production.
"""

from __future__ import annotations

import unittest

from src import parser


class AntimonyRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = parser.parse_element_pdf("antimony")

    def test_identity(self) -> None:
        self.assertEqual(self.record.slug, "antimony")
        self.assertEqual(self.record.symbol, "Sb")
        self.assertTrue(self.record.source_url.endswith("mcs2026-antimony.pdf"))

    def test_units_note_verbatim(self) -> None:
        self.assertEqual(
            self.record.units_note,
            "(Data in metric tons, antimony content, unless otherwise specified)",
        )

    def test_latest_year_us_summary(self) -> None:
        # 2025e values from page 1 of the antimony MCS, hand-verified
        self.assertIsNone(self.record.mined_production_latest)   # withheld
        self.assertEqual(self.record.latest_year_sentinels.get("mined_production"), "W")
        self.assertEqual(self.record.primary_smelting_latest, 700.0)
        self.assertEqual(self.record.secondary_smelting_latest, 3500.0)
        # Imports total = 600 + 39,000 + 4,500 + 350 + 200 = 44,650
        self.assertEqual(self.record.imports_total_latest, 44650.0)
        # Exports total = 5 + 2,900 + 240 + 130 + 6 = 3,281
        self.assertEqual(self.record.exports_total_latest, 3281.0)
        self.assertEqual(self.record.apparent_consumption_latest, 45000.0)
        self.assertEqual(self.record.price_usd_per_pound_latest, 25.0)
        self.assertEqual(self.record.net_import_reliance_pct_latest, 91.0)

    def test_multi_category_import_sources(self) -> None:
        cats = {c.category: c for c in self.record.import_sources_by_category}
        self.assertIn("Ore and concentrates", cats)
        self.assertIn("Oxide", cats)
        self.assertIn("Unwrought metal and powder", cats)
        self.assertIn("Total metal and oxide", cats)

        oxide = {c.country: c.share_pct for c in cats["Oxide"].countries}
        self.assertEqual(oxide["China"], 66.0)
        self.assertEqual(oxide["Belgium"], 16.0)

    def test_world_production_reserves(self) -> None:
        rows = {r.country: r for r in self.record.world_production}
        self.assertEqual(rows["China"].production_latest_year, 40000.0)
        self.assertEqual(rows["China"].reserves, 830000.0)
        # Vietnam — earlier this row got bbox-merged into "220 220"; words fix it.
        self.assertEqual(rows["Vietnam"].production_prev_year, 220.0)
        self.assertEqual(rows["Vietnam"].production_latest_year, 220.0)
        self.assertEqual(rows["Vietnam"].reserves, 54000.0)
        # World total reserves are reported as ">2,000,000" — coerced to 2M, raw preserved
        wt = rows["World total (rounded)"]
        self.assertEqual(wt.reserves, 2000000.0)
        self.assertEqual(wt.reserves_raw, ">2,000,000")


class RareEarthsRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = parser.parse_element_pdf("rare-earths")

    def test_multi_row_nir(self) -> None:
        # Rare earths has NIR split into two sub-rows: compounds-and-metals (67%)
        # and mineral concentrates (E = net exporter).
        sec_rows = [r for r in self.record.salient_stats
                    if r.section and r.section.lower().startswith("net import reliance")]
        labels = {r.label for r in sec_rows}
        self.assertIn("Compounds and metals", labels)
        self.assertIn("Mineral concentrates", labels)
        cm = next(r for r in sec_rows if r.label == "Compounds and metals")
        mc = next(r for r in sec_rows if r.label == "Mineral concentrates")
        self.assertEqual(cm.values["2025e"], 67.0)
        self.assertIsNone(mc.values["2025e"])
        self.assertEqual(mc.raw_values["2025e"], "E")

    def test_per_oxide_price_quotes(self) -> None:
        forms = {pq.form for pq in self.record.price_quotes}
        self.assertTrue(any("Europium oxide" in f for f in forms))
        self.assertTrue(any("Samarium oxide" in f for f in forms))
        self.assertTrue(any("Gadolinium oxide" in f for f in forms))
        eu = next(pq for pq in self.record.price_quotes if pq.form.startswith("Europium oxide"))
        self.assertEqual(eu.values["2025e"], 27.0)


class ScandiumRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = parser.parse_element_pdf("scandium")

    def test_wrapped_nir_label_and_value(self) -> None:
        # Scandium's NIR label wraps across 2 lines ("Net import reliance as
        # a percentage of apparent" / "consumption"). Parser must merge.
        self.assertEqual(self.record.net_import_reliance_pct_latest, 100.0)

    def test_packed_price_cells_split(self) -> None:
        # The oxide price row's 5 cells are packed into 2 spans by PyMuPDF.
        # Parser should split and read all 5.
        oxide = next(pq for pq in self.record.price_quotes if pq.form.startswith("Scandium oxide"))
        # Each cell is a range like "890–1,000" — we keep raw verbatim, coerce to midpoint
        self.assertEqual(oxide.raw_values["2025e"], "640")
        self.assertEqual(oxide.values["2025e"], 640.0)


if __name__ == "__main__":
    unittest.main()
