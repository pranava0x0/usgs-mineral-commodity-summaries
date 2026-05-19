"""Project paths and the element registry.

A single source of truth for which commodities we know how to fetch.
Adding a new element = one entry here + (usually) zero parser changes,
since MCS sheets share a common structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
ELEMENTS: dict[str, Element] = {
    "bismuth": Element(
        slug="bismuth", name="Bismuth", symbol="Bi", mcs_url=_mcs("bismuth"),
        notes="Byproduct of lead/tungsten/zinc; world table is Refinery production. No country-level reserves.",
    ),
    "antimony": Element(
        slug="antimony", name="Antimony", symbol="Sb", mcs_url=_mcs("antimony"),
        notes="Salient stats include 5 import + 5 export forms; no Total row. World table is Mine Production / Reserves.",
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
    "lithium": Element(
        slug="lithium", name="Lithium", symbol="Li", mcs_url=_mcs("lithium"),
        notes="Domestic production W (withheld) — single producer. Lithium batteries are a downstream product.",
    ),
    "molybdenum": Element(
        slug="molybdenum", name="Molybdenum", symbol="Mo", mcs_url=_mcs("molybdenum"),
    ),
    "rare-earths": Element(
        slug="rare-earths", name="Rare Earths (grouped)", symbol=None, mcs_url=_mcs("rare-earths"),
        notes="Grouped sheet covering lanthanides + yttrium. Per-element price quotes for La, Ce, Pr, Nd, Sm, Eu, Gd. Heavy REEs not separately priced.",
    ),
    "scandium": Element(
        slug="scandium", name="Scandium", symbol="Sc", mcs_url=_mcs("scandium"),
        notes="Tiny sheet — no production section, no world table. Three priced grades.",
    ),
    "tellurium": Element(
        slug="tellurium", name="Tellurium", symbol="Te", mcs_url=_mcs("tellurium"),
    ),
    "tungsten": Element(
        slug="tungsten", name="Tungsten", symbol="W", mcs_url=_mcs("tungsten"),
        notes="Multiple W (withheld) cells. Imports / exports split by form (ores vs other forms).",
    ),
    "diamond": Element(
        slug="diamond", name="Diamond (industrial)", symbol="C", mcs_url=_mcs("diamond"),
        notes="USGS bundles industrial diamond (natural + synthetic) into one sheet. Diamond powders are inside it.",
    ),
    "abrasives": Element(
        slug="abrasives", name="Abrasives (manufactured)", symbol=None, mcs_url=_mcs("abrasives"),
        notes="Covers fused aluminum oxide, silicon carbide, metallic abrasives. Closest USGS analog for 'superhard materials'.",
    ),
}

# Sub-commodities and views that derive from a parent element's PDF.
# These don't have their own MCS sheets; they reference the parent's record
# and (optionally) filter to a specific row, price quote, or category.
ALIASES: dict[str, Element] = {
    # Specialty / downstream products
    "diamond-powders": Element(
        slug="diamond-powders", name="Diamond powders", symbol="C", mcs_url=_mcs("diamond"),
        parent_slug="diamond",
        notes="Industrial diamond category — powder grades. No separate MCS sheet.",
    ),
    "gallium-nitride": Element(
        slug="gallium-nitride", name="Gallium nitride (GaN)", symbol="Ga", mcs_url=_mcs("gallium"),
        parent_slug="gallium",
        notes="Downstream semiconductor product. Inventory falls under gallium imports.",
    ),
    "graphite-anodes": Element(
        slug="graphite-anodes", name="Graphite anodes", symbol="C", mcs_url=_mcs("graphite"),
        parent_slug="graphite",
        notes="Downstream battery component. MCS reports natural graphite; anodes are largely synthetic and not separately tabulated.",
    ),
    "lithium-batteries": Element(
        slug="lithium-batteries", name="Lithium batteries", symbol="Li", mcs_url=_mcs("lithium"),
        parent_slug="lithium",
        notes="Finished good. No MCS line item — share parent lithium data.",
    ),
    "superhard-materials": Element(
        slug="superhard-materials", name="Superhard materials", symbol=None, mcs_url=_mcs("abrasives"),
        parent_slug="abrasives",
        notes="No dedicated MCS sheet. Closest source: industrial diamond + abrasives. Pulls from abrasives.",
    ),
    # Individual rare-earth elements — all from the grouped Rare Earths sheet.
    "dysprosium": Element(slug="dysprosium", name="Dysprosium", symbol="Dy",
                          mcs_url=_mcs("rare-earths"), parent_slug="rare-earths",
                          notes="Heavy REE. No individual price quote in MCS 2026 (Apr-2025 China export controls cited)."),
    "erbium": Element(slug="erbium", name="Erbium", symbol="Er",
                      mcs_url=_mcs("rare-earths"), parent_slug="rare-earths",
                      notes="Heavy REE. No individual price quote."),
    "europium": Element(slug="europium", name="Europium", symbol="Eu",
                        mcs_url=_mcs("rare-earths"), parent_slug="rare-earths",
                        parent_filter=r"^Europium oxide", notes="Europium oxide price quote available."),
    "gadolinium": Element(slug="gadolinium", name="Gadolinium", symbol="Gd",
                          mcs_url=_mcs("rare-earths"), parent_slug="rare-earths",
                          parent_filter=r"^Gadolinium oxide", notes="Gadolinium oxide price quote available."),
    "holmium": Element(slug="holmium", name="Holmium", symbol="Ho",
                       mcs_url=_mcs("rare-earths"), parent_slug="rare-earths",
                       notes="Heavy REE. No individual price quote."),
    "lutetium": Element(slug="lutetium", name="Lutetium", symbol="Lu",
                        mcs_url=_mcs("rare-earths"), parent_slug="rare-earths",
                        notes="Heavy REE. No individual price quote."),
    "samarium": Element(slug="samarium", name="Samarium", symbol="Sm",
                        mcs_url=_mcs("rare-earths"), parent_slug="rare-earths",
                        parent_filter=r"^Samarium oxide", notes="Samarium oxide price quote available."),
    "terbium": Element(slug="terbium", name="Terbium", symbol="Tb",
                       mcs_url=_mcs("rare-earths"), parent_slug="rare-earths",
                       notes="Heavy REE. No individual price quote."),
    "thulium": Element(slug="thulium", name="Thulium", symbol="Tm",
                       mcs_url=_mcs("rare-earths"), parent_slug="rare-earths",
                       notes="Heavy REE. No individual price quote."),
    "ytterbium": Element(slug="ytterbium", name="Ytterbium", symbol="Yb",
                         mcs_url=_mcs("rare-earths"), parent_slug="rare-earths",
                         notes="Heavy REE. No individual price quote."),
    "yttrium": Element(slug="yttrium", name="Yttrium", symbol="Y",
                       mcs_url=_mcs("rare-earths"), parent_slug="rare-earths",
                       notes="Listed separately from heavy REEs in the rare-earths chapter."),
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
