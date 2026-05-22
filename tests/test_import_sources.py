"""Regression tests for the Import Sources / country-share parser.

Covers bugs found in the 2026-05-22 audit:
  - scandium: a prose prefix was captured as the country ("Although … Japan").
  - chromium: comma-separated countries dropped ("Taiwan, 16%, Finland, 12%, …").
  - niobium: trailing prose captured as fake countries ("was ferroniobium, 22%").
  - magnesium: category labels containing "%" or longer than 80 chars were
    dropped / merged ("Magnesium metal (99.8% purity)", "Combined total (…)").
"""

from __future__ import annotations

import types
import unittest

from src import parser


class CountryShareListTests(unittest.TestCase):
    def _p(self, seg: str) -> list[tuple[str, float]]:
        return [(c.country, c.share_pct) for c in parser._parse_country_share_list(seg)]

    def test_comma_separated_entries(self) -> None:
        # chromium stainless steel — countries separated by "," not ";", with a
        # footnote digit on "China,9 6%".
        self.assertEqual(
            self._p("Taiwan, 16%, Finland, 12%, India, 11%, China,9 6%; others, 55%"),
            [("Taiwan", 16.0), ("Finland", 12.0), ("India", 11.0),
             ("China", 6.0), ("others", 55.0)],
        )

    def test_prose_prefix_keeps_trailing_country(self) -> None:
        # scandium — the real country sits at the end of a prose sentence.
        self.assertEqual(
            self._p("Although there are no domestic trade codes for scandium "
                    "materials exclusively, shipping records indicated scandium "
                    "oxide was imported from Japan, 89%; and China, 11%"),
            [("Japan", 89.0), ("China", 11.0)],
        )

    def test_trailing_prose_is_rejected(self) -> None:
        # niobium — "…68% was ferroniobium, 22% was niobium metal" must NOT
        # become countries.
        self.assertEqual(
            self._p("Brazil, 67%; Canada, 28%; and other, 5%. Of U.S. niobium "
                    "material imports (by niobium content), 68% was ferroniobium, "
                    "22% was niobium metal, 9% was niobium oxide."),
            [("Brazil", 67.0), ("Canada", 28.0), ("other", 5.0)],
        )

    def test_footnote_between_country_and_percent(self) -> None:
        self.assertEqual(
            self._p("China,9 6%; Japan,6 89%"),
            [("China", 6.0), ("Japan", 89.0)],
        )

    def test_multiword_and_parenthesized_countries(self) -> None:
        self.assertEqual(
            self._p("Congo (Kinshasa), 9%; United Arab Emirates, 5%; South Africa, 48%"),
            [("Congo (Kinshasa)", 9.0), ("United Arab Emirates", 5.0),
             ("South Africa", 48.0)],
        )

    def test_decimal_shares(self) -> None:
        self.assertEqual(self._p("China, 12.5%; other, 87.5%"),
                         [("China", 12.5), ("other", 87.5)])


class ImportCategoryDetectionTests(unittest.TestCase):
    """`_CATEGORY_HEAD` must accept labels with '%' and long labels."""

    def _cats(self, body: str):
        header = types.SimpleNamespace(text=f"Import Sources (2021–24): {body}")
        _flat, cats, _dr = parser._parse_import_sources(header, [])
        return cats

    def test_percent_and_long_labels(self) -> None:
        # magnesium: first category label contains "99.8%"; last is ~92 chars.
        body = (
            "Magnesium metal (99.8% purity): Israel, 47%; Turkey, 31%; and other, 22%. "
            "Magnesium alloys (magnesium content): Czechia, 26%; and other, 74%. "
            "Combined total (includes magnesium content of alloys, metal, powder, "
            "scrap, sheet, and other): Israel, 20%; and other, 80%."
        )
        cats = self._cats(body)
        labels = [c.category for c in cats]
        self.assertIn("Magnesium metal (99.8% purity)", labels)
        self.assertIn(
            "Combined total (includes magnesium content of alloys, metal, powder, "
            "scrap, sheet, and other)",
            labels,
        )
        metal = next(c for c in cats if c.category == "Magnesium metal (99.8% purity)")
        self.assertEqual(metal.countries[0].country, "Israel")
        self.assertEqual(metal.countries[0].share_pct, 47.0)


if __name__ == "__main__":
    unittest.main()
