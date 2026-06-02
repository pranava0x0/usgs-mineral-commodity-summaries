"""Canonical country list and USGS → canonical name mapping.

User-revised spec (2026-05-19): replaces the earlier 204-entry public-column
list with a focused 94-entry alphabetical list. EU member states are now
listed individually (no rollup); United States is a regular country column.
Countries with no material USGS coverage are dropped from the axis (their
data, if any, stays in elements.json).

The CSV exporter writes one country column per entry in `CANONICAL_COUNTRIES`
for each of the 5 country blocks (Import Sources, Mine Production, Refinery
Production, Capacity, Reserves) → 5 × 94 = 470 country columns.
"""

from __future__ import annotations

import re
import unicodedata


CANONICAL_COUNTRIES: list[str] = [
    "Angola",
    "Argentina",
    "Armenia",
    "Australia",
    "Austria",
    "Bahrain",
    "Belgium",
    "Bhutan",
    "Bolivia",
    "Botswana",
    "Brazil",
    "Bulgaria",
    "Burma (Myanmar)",
    "Burundi",
    "Canada",
    "Chile",
    "China",
    "Congo (Kinshasa) / DRC",
    "Côte d'Ivoire",
    "Cuba",
    "Czechia",
    "Egypt",
    "Estonia",
    "Ethiopia",
    "Finland",
    "France",
    "Gabon",
    "Georgia",
    "Germany",
    "Ghana",
    "Greece",
    "Greenland",
    "Guatemala",
    "Guinea",
    "Hungary",
    "Iceland",
    "India",
    "Indonesia",
    "Iran",
    "Ireland",
    "Israel",
    "Italy",
    "Japan",
    "Kazakhstan",
    "Kyrgyzstan",
    "Laos",
    "Latvia",
    "Madagascar",
    "Malaysia",
    "Mali",
    "Mexico",
    "Mongolia",
    "Morocco",
    "Mozambique",
    "Namibia",
    "Netherlands",
    "New Caledonia",
    "Nigeria",
    "North Korea",
    "Norway",
    "Oman",
    "Pakistan",
    "Papua New Guinea",
    "Peru",
    "Philippines",
    "Poland",
    "Portugal",
    "Qatar",
    "Russia",
    "Rwanda",
    "Saudi Arabia",
    "Senegal",
    "Serbia",
    "Sierra Leone",
    "Singapore",
    "South Africa",
    "South Korea",
    "Spain",
    "Sri Lanka",
    "Sweden",
    "Taiwan",
    "Tajikistan",
    "Tanzania",
    "Thailand",
    "Turkey",
    "Ukraine",
    "United Arab Emirates",
    "United Kingdom",
    "United States",
    "Uzbekistan",
    "Venezuela",
    "Vietnam",
    "Zambia",
    "Zimbabwe",
]

assert len(CANONICAL_COUNTRIES) == 94, f"Expected 94 entries, got {len(CANONICAL_COUNTRIES)}"


def _slugify(name: str) -> str:
    """ASCII-only column-name slug. Strips diacritics (`Côte` → `cote`),
    lowercases, and collapses runs of non-alphanumerics to single underscores."""
    normalized = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")


def canonical_slugs() -> list[str]:
    """One column-safe slug per entry, in spec order. (No duplicates in the
    94-entry list; the `__2` suffix logic from the prior spec is gone.)"""
    return [_slugify(name) for name in CANONICAL_COUNTRIES]


# USGS row labels that match a canonical entry by something other than the
# exact spelling. Listed canonically (left = literal USGS text we've seen,
# right = canonical entry). Matching is case-sensitive on the USGS side
# (USGS is internally consistent on capitalisation per row).
USGS_TO_CANONICAL: dict[str, str] = {
    # Korea — USGS uses "Korea, Republic of" and "Korea, North"
    "Korea, Republic of": "South Korea",
    "Republic of Korea": "South Korea",
    "Korea, North": "North Korea",
    # Burma vs Myanmar — USGS uses "Burma"
    "Burma": "Burma (Myanmar)",
    # Congo — USGS uses "Congo (Kinshasa)"
    "Congo (Kinshasa)": "Congo (Kinshasa) / DRC",
    # Côte d'Ivoire — USGS uses curly apostrophe variant
    "Côte d’Ivoire": "Côte d'Ivoire",
    "Côte d'Ivoire": "Côte d'Ivoire",
    "Cote d'Ivoire": "Côte d'Ivoire",
}


# Non-country labels that USGS uses (or that our parser sometimes emits as
# a bug) — always dropped from the CSV. The previous spec also excluded
# "United States" from this set because the summary block carried US data;
# the new spec includes United States as a regular country column, so it's
# no longer in this list.
NON_COUNTRY_LABELS: set[str] = {
    "Other", "Others", "other", "others",
    "Other countries", "World total (rounded)", "World total",
    "Chile and Turkey",                         # parser-merge bug
}


def _lookup(s: str) -> str | None:
    """Direct match against the canonical set + USGS variant map."""
    if s in NON_COUNTRY_LABELS:
        return None
    if s in USGS_TO_CANONICAL:
        return USGS_TO_CANONICAL[s]
    if s in _CANONICAL_SET:
        return s
    return None


def map_country(usgs_name: str) -> str | None:
    """Translate a USGS row's country name to a canonical entry, or return
    None if the row should be dropped from the CSV.

    Drops:
      - non-country labels (`Other`, `World total`, parser bugs)
      - countries absent from the 94-entry canonical list
      - scandium prose-as-country parser bug (long pseudo-sentences)

    EU rollup is gone — Germany / France / Italy / etc. are direct entries.
    """
    if not usgs_name:
        return None
    s = usgs_name.strip()

    # Scandium prose-as-country parser bug (a sentence ends up as a country name).
    if len(s) > 60 or "imported from" in s.lower() or "domestic trade" in s.lower():
        return None

    # Try the full string first — country names with intentional parens
    # ("Congo (Kinshasa)", "Côte d'Ivoire" with literal apostrophe variants)
    # must not be stripped before the lookup.
    direct = _lookup(s)
    if direct is not None or s in NON_COUNTRY_LABELS:
        return direct

    # Strip a trailing commodity qualifier and retry — parenthetical
    # ("Sweden (concentrate)" → "Sweden", "United States (copper telluride)" →
    # "United States") or comma-delimited ("Turkey, refined borates" → "Turkey",
    # "Bolivia, ulexite" → "Bolivia"; boron's world table tags every country
    # with its borate form). Applied ONLY after the full-string lookup miss, so
    # names whose comma/parens are intrinsic ("Korea, Republic of",
    # "Congo (Kinshasa)") are matched above and never reach here. No canonical
    # entry contains a comma, so the comma split can't truncate a real name.
    stripped = re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()  # drop trailing (...)
    stripped = stripped.split(",", 1)[0].strip()           # drop trailing , qualifier
    if stripped != s and stripped:
        return _lookup(stripped)

    return None


_CANONICAL_SET: set[str] = set(CANONICAL_COUNTRIES)
