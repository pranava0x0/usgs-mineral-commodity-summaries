"""Project paths and the element registry.

A single source of truth for which commodities we know how to fetch.
Adding a new element = one entry here + (usually) zero parser changes,
since MCS sheets share a common structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Source-shape taxonomy. Two records share a `kind` iff they come from the same
# PDF *structure* and need the same alias-derivation logic, not just the same
# vibe. Adding a new kind means committing to a new branch in pipeline._make_alias.
#
#   primary      — own MCS sheet, standard salient-stats + world-table layout.
#                  Also the "parent" for grouped sheets (rare-earths, PGM,
#                  zirconium-and-hafnium).
#   rare_earth   — alias against the rare-earths grouped sheet. Per-element
#                  oxide price quotes get filtered out via parent_filter;
#                  sheet-wide aggregates are blanked (they don't apply per-REE).
#   grouped      — alias against a grouped multi-commodity sheet that USGS does
#                  not disaggregate (platinum-group-metals, zirconium-and-hafnium).
#                  Members inherit parent verbatim — USGS reports at the group
#                  level only, so iridium and platinum carry the same record.
#   sub_product  — downstream product (gallium nitride, graphite anodes,
#                  silicon carbide). Inherits parent verbatim because the
#                  parent IS a single commodity whose figures cover it.
ElementKind = Literal["primary", "rare_earth", "grouped", "sub_product"]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
AUDIT_DIR = DATA_DIR / "audit"
VIEWER_DIR = PROJECT_ROOT / "viewer"

USER_AGENT = "CMIE-research/0.1 (https://github.com/local; contact: research@example.com)"
HOST_DELAY_S = 2.0  # min seconds between requests to a single host (CLAUDE.md §Network ethics)


@dataclass(frozen=True)
class Element:
    """A single MCS commodity sheet we know how to ingest."""

    slug: str             # filename-safe lowercase id, e.g. "bismuth"
    name: str             # display name, e.g. "Bismuth"
    symbol: str | None    # periodic table symbol if applicable
    mcs_url: str          # source PDF (the "traceback URL")
    kind: ElementKind = "primary"   # source-shape (see ElementKind)
    notes: str = ""       # any per-element parser hints
    parent_slug: str | None = None  # if set, this commodity is sourced from another's PDF
    parent_filter: str | None = None  # regex over salient row labels / price quote forms


# Edition currently targeted. MCS 2026 is published February 2026.
MCS_EDITION = "MCS 2026"
MCS_DATE = "2026-02"

BASE_MCS = "https://pubs.usgs.gov/periodicals/mcs2026"


def _mcs(slug: str) -> str:
    return f"{BASE_MCS}/mcs2026-{slug}.pdf"


# Primary elements with their own MCS sheets.
#
# Grouped parents — `platinum-group-metals`, `rare-earths`, `abrasives`,
# `zirconium-and-hafnium` — also live here. Individual constituents of those
# sheets (iridium, lanthanum, hafnium, silicon-carbide, ...) live in ALIASES.
#
# Slug naming follows the USGS file naming convention:
# https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-<slug>.pdf
ELEMENTS: dict[str, Element] = {
    "abrasives": Element(
        slug="abrasives", name="Abrasives (manufactured)", symbol=None, mcs_url=_mcs("abrasives"),
        notes="Covers fused aluminum oxide, silicon carbide, metallic abrasives. Closest USGS analog for 'superhard materials'.",
    ),
    "aluminum": Element(
        slug="aluminum", name="Aluminum", symbol="Al", mcs_url=_mcs("aluminum"),
        notes="USGS spelling: 'aluminum' (not aluminium). Covers primary metal; bauxite/alumina are separate sheets.",
    ),
    "antimony": Element(
        slug="antimony", name="Antimony", symbol="Sb", mcs_url=_mcs("antimony"),
        notes="Salient stats include 5 import + 5 export forms; no Total row. World table is Mine Production / Reserves.",
    ),
    "bismuth": Element(
        slug="bismuth", name="Bismuth", symbol="Bi", mcs_url=_mcs("bismuth"),
        notes="Byproduct of lead/tungsten/zinc; world table is Refinery production. No country-level reserves.",
    ),
    "chromium": Element(
        slug="chromium", name="Chromium", symbol="Cr", mcs_url=_mcs("chromium"),
    ),
    "cobalt": Element(
        slug="cobalt", name="Cobalt", symbol="Co", mcs_url=_mcs("cobalt"),
    ),
    "copper": Element(
        slug="copper", name="Copper", symbol="Cu", mcs_url=_mcs("copper"),
    ),
    "diamond": Element(
        slug="diamond", name="Diamond (industrial)", symbol="C", mcs_url=_mcs("diamond"),
        notes="USGS bundles industrial diamond (natural + synthetic) into one sheet. Diamond powders are inside it.",
    ),
    "gallium": Element(
        slug="gallium", name="Gallium", symbol="Ga", mcs_url=_mcs("gallium"),
    ),
    "germanium": Element(
        slug="germanium", name="Germanium", symbol="Ge", mcs_url=_mcs("germanium"),
    ),
    "graphite": Element(
        slug="graphite", name="Graphite (natural)", symbol="C", mcs_url=_mcs("graphite"),
        notes="Natural graphite only; synthetic graphite (anodes) is a downstream product.",
    ),
    "indium": Element(
        slug="indium", name="Indium", symbol="In", mcs_url=_mcs("indium"),
    ),
    "iron-and-steel": Element(
        slug="iron-and-steel", name="Iron and Steel", symbol="Fe",
        mcs_url=_mcs("iron-steel"),
        notes="USGS publishes the integrated 'iron-steel' sheet (raw steel + pig iron); iron ore and iron-and-steel scrap are separate sheets.",
    ),
    "lithium": Element(
        slug="lithium", name="Lithium", symbol="Li", mcs_url=_mcs("lithium"),
        notes="Domestic production W (withheld) — single producer. Lithium batteries are a downstream product.",
    ),
    "magnesium": Element(
        slug="magnesium", name="Magnesium", symbol="Mg", mcs_url=_mcs("magnesium-metal"),
        notes="USGS publishes 'magnesium-metal' and 'magnesium-compounds' separately; this entry tracks the metal sheet.",
    ),
    "manganese": Element(
        slug="manganese", name="Manganese", symbol="Mn", mcs_url=_mcs("manganese"),
    ),
    "molybdenum": Element(
        slug="molybdenum", name="Molybdenum", symbol="Mo", mcs_url=_mcs("molybdenum"),
    ),
    "nickel": Element(
        slug="nickel", name="Nickel", symbol="Ni", mcs_url=_mcs("nickel"),
    ),
    "niobium": Element(
        slug="niobium", name="Niobium (columbium)", symbol="Nb", mcs_url=_mcs("niobium"),
        notes="USGS uses 'niobium' in the modern sheet name; historically 'columbium'.",
    ),
    "platinum-group-metals": Element(
        slug="platinum-group-metals", name="Platinum-group metals (grouped)", symbol=None,
        mcs_url=_mcs("platinum-group"),
        notes="USGS 2026 filename is 'platinum-group' (the '-metals' suffix was dropped this edition). Grouped sheet covering iridium, palladium, platinum, rhodium, ruthenium, osmium. Per-PGM aliases inherit this verbatim.",
    ),
    "rare-earths": Element(
        slug="rare-earths", name="Rare Earths (grouped)", symbol=None, mcs_url=_mcs("rare-earths"),
        notes="Grouped sheet covering lanthanides + yttrium. Per-element price quotes for La, Ce, Pr, Nd, Sm, Eu, Gd. Heavy REEs not separately priced.",
    ),
    "rhenium": Element(
        slug="rhenium", name="Rhenium", symbol="Re", mcs_url=_mcs("rhenium"),
        notes="Transition metal — superalloy component. Byproduct of molybdenum/copper refining.",
    ),
    "scandium": Element(
        slug="scandium", name="Scandium", symbol="Sc", mcs_url=_mcs("scandium"),
        notes="Tiny sheet — no production section, no world table. Three priced grades.",
    ),
    "silicon": Element(
        slug="silicon", name="Silicon", symbol="Si", mcs_url=_mcs("silicon"),
        notes="USGS reports silicon metal + ferrosilicon together in this sheet. Silicon carbide is a manufactured abrasive (see abrasives).",
    ),
    "silver": Element(
        slug="silver", name="Silver", symbol="Ag", mcs_url=_mcs("silver"),
    ),
    "tantalum": Element(
        slug="tantalum", name="Tantalum", symbol="Ta", mcs_url=_mcs("tantalum"),
    ),
    "tellurium": Element(
        slug="tellurium", name="Tellurium", symbol="Te", mcs_url=_mcs("tellurium"),
    ),
    "tin": Element(
        slug="tin", name="Tin", symbol="Sn", mcs_url=_mcs("tin"),
    ),
    "titanium": Element(
        slug="titanium", name="Titanium", symbol="Ti", mcs_url=_mcs("titanium"),
        notes="USGS 2026 filename is 'titanium' (the '-and-titanium-dioxide' suffix was dropped this edition). Titanium mineral concentrates (ilmenite/rutile) is a separate sheet.",
    ),
    "tungsten": Element(
        slug="tungsten", name="Tungsten", symbol="W", mcs_url=_mcs("tungsten"),
        notes="Multiple W (withheld) cells. Imports / exports split by form (ores vs other forms).",
    ),
    "vanadium": Element(
        slug="vanadium", name="Vanadium", symbol="V", mcs_url=_mcs("vanadium"),
    ),
    "zinc": Element(
        slug="zinc", name="Zinc", symbol="Zn", mcs_url=_mcs("zinc"),
    ),
    "zirconium-and-hafnium": Element(
        slug="zirconium-and-hafnium", name="Zirconium and hafnium (grouped)", symbol=None,
        mcs_url=_mcs("zirconium-hafnium"),
        notes="USGS 2026 filename is 'zirconium-hafnium' (the '-and-' connector was dropped this edition). Per-element aliases inherit verbatim.",
    ),
}

# Sub-commodities and views that derive from a parent element's PDF.
# These don't have their own MCS sheets; they reference the parent's record
# and (optionally) filter to a specific row, price quote, or category.
#
# `kind` selects the alias-derivation branch in pipeline._make_alias:
#   sub_product  — inherit parent verbatim
#   rare_earth   — filter price to per-element oxide quote; blank sheet-wide aggregates
#   grouped      — inherit parent verbatim (USGS reports at group level only)
ALIASES: dict[str, Element] = {
    # Specialty / downstream products (sub_product)
    "diamond-powders": Element(
        slug="diamond-powders", name="Diamond powders", symbol="C", mcs_url=_mcs("diamond"),
        kind="sub_product", parent_slug="diamond",
        notes="Industrial diamond category — powder grades. No separate MCS sheet.",
    ),
    "gallium-nitride": Element(
        slug="gallium-nitride", name="Gallium nitride (GaN)", symbol="Ga", mcs_url=_mcs("gallium"),
        kind="sub_product", parent_slug="gallium",
        notes="Downstream semiconductor product. Inventory falls under gallium imports.",
    ),
    "graphite-anodes": Element(
        slug="graphite-anodes", name="Graphite anodes", symbol="C", mcs_url=_mcs("graphite"),
        kind="sub_product", parent_slug="graphite",
        notes="Downstream battery component. MCS reports natural graphite; anodes are largely synthetic and not separately tabulated.",
    ),
    "lithium-batteries": Element(
        slug="lithium-batteries", name="Lithium batteries", symbol="Li", mcs_url=_mcs("lithium"),
        kind="sub_product", parent_slug="lithium",
        notes="Finished good. No MCS line item — share parent lithium data.",
    ),
    "silicon-carbide": Element(
        slug="silicon-carbide", name="Silicon carbide", symbol=None, mcs_url=_mcs("abrasives"),
        kind="sub_product", parent_slug="abrasives",
        notes="Synthetic ceramic abrasive. Not a rare earth — covered in the abrasives sheet alongside fused aluminum oxide.",
    ),
    "superhard-materials": Element(
        slug="superhard-materials", name="Superhard materials", symbol=None, mcs_url=_mcs("abrasives"),
        kind="sub_product", parent_slug="abrasives",
        notes="No dedicated MCS sheet. Closest source: industrial diamond + abrasives. Pulls from abrasives.",
    ),
    # Individual rare-earth elements — all from the grouped Rare Earths sheet.
    "cerium": Element(slug="cerium", name="Cerium", symbol="Ce",
                      mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                      parent_filter=r"^Cerium oxide", notes="Light REE. Cerium oxide price quote available."),
    "dysprosium": Element(slug="dysprosium", name="Dysprosium", symbol="Dy",
                          mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                          notes="Heavy REE. No individual price quote in MCS 2026 (Apr-2025 China export controls cited)."),
    "erbium": Element(slug="erbium", name="Erbium", symbol="Er",
                      mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                      notes="Heavy REE. No individual price quote."),
    "europium": Element(slug="europium", name="Europium", symbol="Eu",
                        mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                        parent_filter=r"^Europium oxide", notes="Europium oxide price quote available."),
    "gadolinium": Element(slug="gadolinium", name="Gadolinium", symbol="Gd",
                          mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                          parent_filter=r"^Gadolinium oxide", notes="Gadolinium oxide price quote available."),
    "holmium": Element(slug="holmium", name="Holmium", symbol="Ho",
                       mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                       notes="Heavy REE. No individual price quote."),
    "lanthanum": Element(slug="lanthanum", name="Lanthanum", symbol="La",
                         mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                         parent_filter=r"^Lanthanum oxide", notes="Light REE. Lanthanum oxide price quote available."),
    "lutetium": Element(slug="lutetium", name="Lutetium", symbol="Lu",
                        mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                        notes="Heavy REE. No individual price quote."),
    "neodymium": Element(slug="neodymium", name="Neodymium", symbol="Nd",
                         mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                         parent_filter=r"^Neodymium oxide", notes="Light REE. Neodymium oxide price quote available."),
    "praseodymium": Element(slug="praseodymium", name="Praseodymium", symbol="Pr",
                            mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                            parent_filter=r"^Praseodymium oxide", notes="Light REE. Praseodymium oxide price quote available."),
    "samarium": Element(slug="samarium", name="Samarium", symbol="Sm",
                        mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                        parent_filter=r"^Samarium oxide", notes="Samarium oxide price quote available."),
    "terbium": Element(slug="terbium", name="Terbium", symbol="Tb",
                       mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                       notes="Heavy REE. No individual price quote."),
    "thulium": Element(slug="thulium", name="Thulium", symbol="Tm",
                       mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                       notes="Heavy REE. No individual price quote."),
    "ytterbium": Element(slug="ytterbium", name="Ytterbium", symbol="Yb",
                         mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                         notes="Heavy REE. No individual price quote."),
    "yttrium": Element(slug="yttrium", name="Yttrium", symbol="Y",
                       mcs_url=_mcs("rare-earths"), kind="rare_earth", parent_slug="rare-earths",
                       notes="Listed separately from heavy REEs in the rare-earths chapter."),
    # Platinum-group metals — inherit the grouped PGM sheet.
    # USGS reports total PGM production at the group level, but the 2026 World
    # Mine Production table breaks it into Palladium + Platinum sub-columns.
    # Per-metal aliases that match a sub-column (palladium, platinum) use
    # `parent_filter` to pick which sub-metal to surface; the rest (iridium,
    # osmium, rhodium, ruthenium) inherit the parent record with their
    # production columns blanked (no per-metal data).
    "iridium": Element(slug="iridium", name="Iridium", symbol="Ir",
                       mcs_url=_mcs("platinum-group"), kind="grouped",
                       parent_slug="platinum-group-metals",
                       notes="PGM — not a rare earth. USGS does not break out Ir mine production; inherits parent."),
    "osmium": Element(slug="osmium", name="Osmium", symbol="Os",
                      mcs_url=_mcs("platinum-group"), kind="grouped",
                      parent_slug="platinum-group-metals",
                      notes="PGM. USGS does not break out Os mine production; inherits parent."),
    "palladium": Element(slug="palladium", name="Palladium", symbol="Pd",
                         mcs_url=_mcs("platinum-group"), kind="grouped",
                         parent_slug="platinum-group-metals",
                         parent_filter="Palladium",
                         notes="PGM. Mine production from the Palladium sub-column of the PGM World Production table."),
    "platinum": Element(slug="platinum", name="Platinum", symbol="Pt",
                        mcs_url=_mcs("platinum-group"), kind="grouped",
                        parent_slug="platinum-group-metals",
                        parent_filter="Platinum",
                        notes="PGM. Mine production from the Platinum sub-column of the PGM World Production table."),
    "rhodium": Element(slug="rhodium", name="Rhodium", symbol="Rh",
                       mcs_url=_mcs("platinum-group"), kind="grouped",
                       parent_slug="platinum-group-metals",
                       notes="PGM. USGS does not break out Rh mine production; inherits parent."),
    "ruthenium": Element(slug="ruthenium", name="Ruthenium", symbol="Ru",
                         mcs_url=_mcs("platinum-group"), kind="grouped",
                         parent_slug="platinum-group-metals",
                         notes="PGM. USGS does not break out Ru mine production; inherits parent."),
    # Iron and Steel sub-products. The USGS sheet's Salient Statistics lists
    # "Pig iron production" and "Raw steel production" as separate US rows;
    # the World Production table is a single combined column (no split).
    # We fan out into two CSV rows so each sub-product gets its own salient
    # value in the summary block. The shared World Production data is
    # inherited verbatim (both rows show the same per-country production).
    "iron-and-steel-pig-iron": Element(
        slug="iron-and-steel-pig-iron", name="Iron and Steel (Pig iron)", symbol="Fe",
        mcs_url=_mcs("iron-steel"), kind="sub_product", parent_slug="iron-and-steel",
        parent_filter="Pig iron",
        notes="US pig iron production row from the iron-and-steel sheet.",
    ),
    "iron-and-steel-raw-steel": Element(
        slug="iron-and-steel-raw-steel", name="Iron and Steel (Raw steel)", symbol="Fe",
        mcs_url=_mcs("iron-steel"), kind="sub_product", parent_slug="iron-and-steel",
        parent_filter="Raw steel",
        notes="US raw steel production row from the iron-and-steel sheet.",
    ),
    # Zirconium + hafnium — share a single combined USGS sheet.
    # Same workflow as PGMs: parent holds the data, members inherit verbatim.
    "hafnium": Element(slug="hafnium", name="Hafnium", symbol="Hf",
                       mcs_url=_mcs("zirconium-hafnium"), kind="grouped",
                       parent_slug="zirconium-and-hafnium",
                       notes="Transition metal — not a rare earth. Co-extracted with zirconium; USGS reports them in a combined sheet."),
    "zirconium": Element(slug="zirconium", name="Zirconium", symbol="Zr",
                         mcs_url=_mcs("zirconium-hafnium"), kind="grouped",
                         parent_slug="zirconium-and-hafnium",
                         notes="Co-reported with hafnium in the combined sheet."),
}


def all_known() -> dict[str, Element]:
    """Union of primary elements + aliases."""
    out: dict[str, Element] = {}
    out.update(ELEMENTS)
    out.update(ALIASES)
    return out


def ensure_dirs() -> None:
    """Create the project's working directories if missing."""
    for d in (RAW_DIR, PROCESSED_DIR, AUDIT_DIR):
        d.mkdir(parents=True, exist_ok=True)
