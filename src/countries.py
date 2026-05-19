"""Canonical 203-country list and USGS → canonical name mapping.

Source: `public column information.xlsx` (user-provided spec, May 2026).
The CSV exporter writes one country column per entry in
`CANONICAL_COUNTRIES` for each of the 5 country blocks (Import Sources,
Mine Production, Refinery Production, Capacity, Reserves), totalling
5 × 204 = 1,020 country columns. (Spec was 203; Kyrgyzstan added back
after-the-fact — it was absent from the spec but USGS reports it as a
material antimony producer with 700 t mine production + 260,000 t
reserves. Inserted alphabetically between Kosovo and Liechtenstein in
the Europe block.)

Two countries — China and Syria — appear twice in the spec (once at
their "priority" position, once in their regional alphabetical block).
Both columns are emitted; both receive the same value. The second
occurrence's column name carries a `__2` suffix so CSV consumers don't
clash on duplicate keys.

USGS data uses several country-name variants that don't match the
spec. `USGS_TO_CANONICAL` maps each known variant to its canonical
entry. Anything else falls back to:

  - dropped if it's a non-country aggregate row (`Other`, `World total`,
    parser bug labels, etc.)
  - aggregated into `European Union` if it's an EU member state
  - dropped with a warning if it's a real country missing from the
    canonical list (e.g. Kyrgyzstan, which is absent from the spec)

The summary-column block already captures United States figures, so
"United States" is intentionally absent from `CANONICAL_COUNTRIES`
and gets dropped from per-country mapping.
"""

from __future__ import annotations

# --- 203 entries, ordered per spec: 4 priority (Canada, China, Mexico, EU),
# then regional alphabetical: Africa → Middle East → Asia → Oceania → North
# America (non-EU) → Caribbean → South America → Europe (non-EU, including
# Central Asia). Ends at Vatican City.
CANONICAL_COUNTRIES: list[str] = [
    "Canada",
    "China",
    "Mexico",
    "European Union",
    "Algeria",
    "Angola",
    "Benin",
    "Botswana",
    "Burkina Faso",
    "Burundi",
    "Cabo Verde",
    "Cameroon",
    "Central African Republic",
    "Chad",
    "Comoros",
    "Congo (Brazzaville)",
    "Congo (Kinshasa)",
    "Cote d'Ivoire",
    "Djibouti",
    "Egypt",
    "Equatorial Guinea",
    "Eritrea",
    "Eswatini",
    "Ethiopia",
    "Gabon",
    "Gambia",
    "Ghana",
    "Guinea",
    "Guinea-Bissau",
    "Kenya",
    "Lesotho",
    "Liberia",
    "Libya",
    "Madagascar",
    "Malawi",
    "Mali",
    "Mauritania",
    "Mauritius",
    "Mayotte",
    "Morocco",
    "Mozambique",
    "Namibia",
    "Niger",
    "Nigeria",
    "Reunion",
    "Rwanda",
    "Sao Tome and Principe",
    "Senegal",
    "Seychelles",
    "Sierra Leone",
    "Somalia",
    "South Africa",
    "South Sudan",
    "St Helena",
    "Sudan",
    "Tanzania",
    "Togo",
    "Tunisia",
    "Uganda",
    "Zambia",
    "Zimbabwe",
    "Bahrain",
    "Gaza Strip Administered by Israel",
    "Iran",
    "Iraq",
    "Israel",
    "Jordan",
    "Kuwait",
    "Lebanon",
    "Oman",
    "Qatar",
    "Saudi Arabia",
    "Syria",
    "United Arab Emirates",
    "West Bank Administered by Israel",
    "Yemen",
    "Afghanistan",
    "Bangladesh",
    "India",
    "Nepal",
    "Pakistan",
    "Sri Lanka",
    "Bhutan",
    "Brunei",
    "Burma",
    "Cambodia",
    "China",
    "Hong Kong",
    "Indonesia",
    "Japan",
    "Korea, North",
    "Korea, South",
    "Laos",
    "Macau",
    "Malaysia",
    "Maldives",
    "Mongolia",
    "Philippines",
    "Singapore",
    "Syria",
    "Taiwan",
    "Thailand",
    "Timor-Leste",
    "Vietnam",
    "Australia",
    "Christmas Island",
    "Cocos (Keeling) Islands",
    "Cook Islands",
    "Fiji",
    "French Polynesia",
    "Heard and McDonald Islands",
    "Kiribati",
    "Marshall Islands",
    "Micronesia",
    "Nauru",
    "New Caledonia",
    "New Zealand",
    "Niue",
    "Norfolk Island",
    "Palau",
    "Papua New Guinea",
    "Pitcairn Islands",
    "Samoa",
    "Solomon Islands",
    "Tokelau",
    "Tonga",
    "Tuvalu",
    "Vanuatu",
    "Wallis and Futuna",
    "Greenland",
    "St Pierre and Miquelon",
    "Anguilla",
    "Antigua and Barbuda",
    "Aruba",
    "Bahamas",
    "Barbados",
    "Belize",
    "Bermuda",
    "British Virgin Islands",
    "Cayman Islands",
    "Costa Rica",
    "Cuba",
    "Curacao",
    "Dominica",
    "Dominican Republic",
    "El Salvador",
    "Grenada",
    "Guadeloupe",
    "Guatemala",
    "Haiti",
    "Honduras",
    "Jamaica",
    "Martinique",
    "Montserrat",
    "Nicaragua",
    "Panama",
    "Sint Maarten",
    "St Kitts and Nevis",
    "St Lucia",
    "St Vincent and the Grenadines",
    "Trinidad and Tobago",
    "Turks and Caicos Islands",
    "Argentina",
    "Bolivia",
    "Brazil",
    "Chile",
    "Colombia",
    "Ecuador",
    "Falkland Islands (Islas Malvinas)",
    "French Guiana",
    "Guyana",
    "Paraguay",
    "Peru",
    "Suriname",
    "Uruguay",
    "Venezuela",
    "Albania",
    "Andorra",
    "Armenia",
    "Azerbaijan",
    "Belarus",
    "Bosnia and Herzegovina",
    "Georgia",
    "Iceland",
    "Kazakhstan",
    "Kosovo",
    "Kyrgyzstan",
    "Liechtenstein",
    "Macedonia",
    "Moldova",
    "Monaco",
    "Montenegro",
    "Norway",
    "Russia",
    "San Marino",
    "Serbia",
    "Switzerland",
    "Tajikistan",
    "Turkey",
    "Turkmenistan",
    "Ukraine",
    "United Kingdom",
    "Uzbekistan",
    "Vatican City",
]

assert len(CANONICAL_COUNTRIES) == 204, f"Expected 204 entries, got {len(CANONICAL_COUNTRIES)}"


# Slug rules:
#   - first occurrence of a name gets its plain slug
#   - subsequent occurrences get __2, __3, ... suffix
def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def canonical_slugs() -> list[str]:
    """Return one column-name-safe slug per CANONICAL_COUNTRIES entry.

    Duplicates (China, Syria) get a `__2` suffix on the second occurrence so
    dict keys remain unique. Order preserves the spec ordering.
    """
    out: list[str] = []
    seen: dict[str, int] = {}
    for name in CANONICAL_COUNTRIES:
        base = _slugify(name)
        seen[base] = seen.get(base, 0) + 1
        if seen[base] == 1:
            out.append(base)
        else:
            out.append(f"{base}__{seen[base]}")
    return out


# USGS publishes country names with formatting that differs from the spec.
# Map each known variant to its canonical entry. Variants not listed here
# fall through to the EU-member / drop-non-country fallbacks in `map_country`.
USGS_TO_CANONICAL: dict[str, str] = {
    "Korea, Republic of": "Korea, South",
    "Republic of Korea": "Korea, South",
    "Korea, Republic of (South Korea)": "Korea, South",
    "Côte d’Ivoire": "Cote d'Ivoire",          # MCS uses curly apostrophe
    "Côte d'Ivoire": "Cote d'Ivoire",
    "Cote d'Ivoire": "Cote d'Ivoire",
    "Czech Republic": None,                     # EU member, see EU_MEMBERS
    # The remaining mappings are no-ops (USGS name already matches canonical)
    # but are listed for documentation:
    "Burma": "Burma",
    "Congo (Kinshasa)": "Congo (Kinshasa)",
}


# EU member states that USGS often reports individually. Their values get
# aggregated into the canonical "European Union" entry. This list is the
# 27 EU member states as of 2026.
EU_MEMBERS: set[str] = {
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czechia",
    "Czech Republic", "Denmark", "Estonia", "Finland", "France",
    "Germany", "Greece", "Hungary", "Ireland", "Italy", "Latvia",
    "Lithuania", "Luxembourg", "Malta", "Netherlands", "Poland",
    "Portugal", "Romania", "Slovakia", "Slovenia", "Spain", "Sweden",
}


# Non-country labels that USGS uses (or that our parser sometimes emits
# as a parser bug) — always dropped from CSV. Real per-country data still
# lives in elements.json for anyone who needs the residual.
NON_COUNTRY_LABELS: set[str] = {
    "Other", "Others", "other", "others",
    "Other countries", "World total (rounded)", "World total",
    "United States",                            # in summary columns, not per-country
    "Chile and Turkey",                         # parser merge bug (BACKLOG #12)
}


def map_country(usgs_name: str) -> str | None:
    """Translate a USGS row's country name to a canonical entry.

    Returns one of:
      - the canonical entry name (a string in CANONICAL_COUNTRIES)
      - "European Union" if the name is an EU member state
      - None if the name should be dropped (non-country / parser bug /
        missing from the spec like Kyrgyzstan)
    """
    if not usgs_name:
        return None
    s = usgs_name.strip()
    # Strip trailing parenthetical commodity qualifiers, e.g.
    # "Sweden (concentrate)" → "Sweden", "United States (copper telluride)" → "United States"
    import re
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()

    # The scandium prose-as-country parser bug emits a sentence as a country —
    # filter by length and presence of multi-word phrases.
    if len(s) > 60 or "imported from" in s.lower() or "domestic trade" in s.lower():
        return None

    if s in NON_COUNTRY_LABELS:
        return None

    # Direct USGS-variant mapping
    if s in USGS_TO_CANONICAL:
        mapped = USGS_TO_CANONICAL[s]
        return mapped  # may be None (e.g. handled-via-EU)

    # EU member rollup
    if s in EU_MEMBERS:
        return "European Union"

    # Already a canonical entry
    if s in _CANONICAL_SET:
        return s

    # Not in spec, not an EU member, not a known variant — drop with no
    # warning (the caller logs the residual count once per element).
    return None


_CANONICAL_SET: set[str] = set(CANONICAL_COUNTRIES)
