"""Pydantic models for one MCS commodity record.

Every numeric field carries its source URL (traceback). Optional fields are
explicitly typed `Optional[...]` and render in the viewer as "Not available"
rather than blanks (per CLAUDE.md §Data handling).

Conventions:
- All quantities are in the unit the PDF declared on its subtitle
  (captured verbatim as `units_note`).
- A value of `None` means "not reported / NA"; a value of `0.0` means
  the PDF showed an em-dash "—" (USGS convention for zero).
- Non-numeric sentinels live in `raw_values`: "W" (Withheld), "E"
  (Net exporter), ">95" (greater-than approximation), "<5", etc.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Pydantic v2: forbid unknown keys at model boundaries (CLAUDE.md §Testing).
StrictBase = ConfigDict(extra="forbid", populate_by_name=True)

YEAR_COLUMNS = ("2021", "2022", "2023", "2024", "2025e")

# Mirrors src.config.ElementKind — kept in sync so the viewer / CSV can filter.
RecordKind = Literal["primary", "rare_earth", "grouped", "sub_product"]


class YearSeries(BaseModel):
    """A single labeled row of the Salient Statistics table, one value per year.

    `values[year]` is the *numeric* coercion for downstream math; `raw_values[year]`
    keeps the literal token from the PDF so we can faithfully display ">95",
    "W" (withheld), "E" (net exporter), or qualifiers that don't survive
    rounding. When the original cell is parseable as a number, `raw_values`
    holds the cleaned text without commas.
    """

    model_config = StrictBase

    label: str                                # row label, footnotes stripped
    footnote: Optional[str] = None            # any numeric footnote attached to the label
    section: Optional[str] = None             # parent section header, e.g. "Imports for consumption"
    subsection: Optional[str] = None          # one nesting level deeper, e.g. "Smelter" under "Production"
    values: dict[str, Optional[float]]        # coerced floats; None if non-numeric or "NA"
    raw_values: dict[str, Optional[str]] = Field(default_factory=dict)


class CountryShare(BaseModel):
    """One country / share entry from the Import Sources line."""

    model_config = StrictBase

    country: str
    share_pct: Optional[float]                # None if the source listed "other" or unspecified


class ImportSourceCategory(BaseModel):
    """One sub-category of Import Sources (e.g. 'Oxide', 'Ore and concentrates').

    Elements like antimony break import sources into multiple commodity forms;
    the bismuth-style single-list version becomes `category=None`.
    """

    model_config = StrictBase

    category: Optional[str] = None
    countries: list[CountryShare] = Field(default_factory=list)


class WorldProductionRow(BaseModel):
    """One row of the World Refinery / Mine Production and Reserves table."""

    model_config = StrictBase

    country: str
    production_prev_year: Optional[float] = None   # MCS prior-year value (e.g. 2024)
    production_latest_year: Optional[float] = None # MCS latest-year value (e.g. 2025e)
    capacity: Optional[float] = None
    reserves: Optional[float] = None
    production_prev_raw: Optional[str] = None      # original token, preserves "W" / ">N" / "E" / commas
    production_latest_raw: Optional[str] = None
    reserves_raw: Optional[str] = None
    note: Optional[str] = None                     # e.g. "footnote 7" indicating "Reported"
    # Per-metal latest-year production for grouped sheets that break the table
    # into sub-columns (PGM splits Mine Production into Palladium + Platinum).
    # Empty for elements whose world-production table has a single production
    # column. Keys are the sub-metal display name as printed in the PDF
    # header (e.g. "Palladium", "Platinum").
    sub_metal_production_latest: dict[str, Optional[float]] = Field(default_factory=dict)


class PriceQuote(BaseModel):
    """A row from the Price section (some sheets list several priced forms)."""

    model_config = StrictBase

    form: str                                  # e.g. "Lanthanum oxide, 99.5% minimum"
    unit_note: Optional[str] = None            # column-header description, e.g. "$/kg"
    values: dict[str, Optional[float]] = Field(default_factory=dict)
    raw_values: dict[str, Optional[str]] = Field(default_factory=dict)


class ElementRecord(BaseModel):
    """The complete MCS record for one commodity."""

    model_config = StrictBase

    # Identity / provenance
    slug: str
    name: str
    symbol: Optional[str] = None
    kind: RecordKind = "primary"              # source-shape; mirrors config.ElementKind
    parent_slug: Optional[str] = None         # set when this record was derived from another's PDF
    source_url: str                           # traceback URL — the original USGS PDF
    edition: str                              # e.g. "MCS 2026"
    edition_date: str                         # e.g. "2026-02"
    captured_at: str                          # ISO date the scraper ran
    pdf_sha256: str                           # detect re-issued PDFs
    pdf_page_count: int

    # Verbatim labels
    units_note: str                           # verbatim subtitle of the sheet
    price_unit_note: Optional[str] = None     # the price-row label, e.g. "Price, average, dollars per pound"
    price_footnote_text: Optional[str] = None # the footnote text describing the price basis

    # Verbatim prose blocks
    domestic_use_summary: Optional[str] = None
    events_trends_summary: Optional[str] = None
    world_resources_summary: Optional[str] = None
    substitutes_summary: Optional[str] = None
    recycling_summary: Optional[str] = None

    # Salient Statistics — full flat list of rows, plus convenience aggregations below
    salient_stats: list[YearSeries] = Field(default_factory=list)
    price_quotes: list[PriceQuote] = Field(default_factory=list)

    # Latest-year top-level columns (the user's "single-row CSV" view)
    latest_year: str = "2025e"
    mined_production_latest: Optional[float] = None
    primary_smelting_latest: Optional[float] = None      # "Refinery" / "Primary" row
    secondary_smelting_latest: Optional[float] = None    # "Secondary (scrap)" / "Secondary" row
    imports_total_latest: Optional[float] = None         # explicit Total row, or sum across forms
    exports_total_latest: Optional[float] = None
    apparent_consumption_latest: Optional[float] = None
    price_usd_per_pound_latest: Optional[float] = None   # representative price (first price row)
    net_import_reliance_pct_latest: Optional[float] = None

    # Withheld / net-exporter markers for the latest year so the viewer / CSV
    # can show "W" or "E" instead of a blank when USGS suppresses the number.
    latest_year_sentinels: dict[str, str] = Field(default_factory=dict)

    # Government Stockpile — FY 2025 Potential Acquisitions. Summed across
    # material rows when the sheet lists more than one (e.g. tungsten lists
    # "Ores and concentrates" + "Tungsten"; both contribute). None when the
    # sheet says "Not available" or no Stockpile section exists.
    stockpile_fy2025_potential_acquisitions: Optional[float] = None

    # Per-country breakdowns
    import_sources_flat: list[CountryShare] = Field(default_factory=list)  # bismuth-style single list
    import_sources_by_category: list[ImportSourceCategory] = Field(default_factory=list)
    import_sources_range: Optional[str] = None            # e.g. "2021-24"

    world_production_label: Optional[str] = None          # exact section header from the PDF
    world_production_year_prev: Optional[str] = None      # verbatim prev-year header from the PDF (e.g. "2024")
    world_production_year_latest: Optional[str] = None    # verbatim latest-year header from the PDF (e.g. "2025" or "2025e")
    world_production: list[WorldProductionRow] = Field(default_factory=list)

    # Footnotes referenced anywhere in the sheet (raw text by index/letter)
    footnotes: dict[str, str] = Field(default_factory=dict)


class ElementBundle(BaseModel):
    """The viewer's data file shape — one or more ElementRecords."""

    model_config = StrictBase

    edition: str
    generated_at: str
    elements: list[ElementRecord]
