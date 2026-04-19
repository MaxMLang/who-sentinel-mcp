"""Country name resolution: pycountry + a small overlay for nicknames WHO/pycountry don't catch."""

from __future__ import annotations

import pycountry

# pycountry does not know "DRC", "the Gambia", USSR/Soviet Union, etc.
# Keep this overlay tight; everything else should fall through to pycountry.
_OVERLAY_TO_ISO3: dict[str, str] = {
    "us": "USA",
    "u s a": "USA",
    "america": "USA",
    "uk": "GBR",
    "u k": "GBR",
    "great britain": "GBR",
    "britain": "GBR",
    "england": "GBR",
    "scotland": "GBR",
    "wales": "GBR",
    "northern ireland": "GBR",
    "south korea": "KOR",
    "korea": "KOR",
    "north korea": "PRK",
    "dprk": "PRK",
    "prc": "CHN",
    "ussr": "RUS",
    "soviet union": "RUS",
    "drc": "COD",
    "dr congo": "COD",
    "congo brazzaville": "COG",
    "burma": "MMR",
    "the gambia": "GMB",
    "ivory coast": "CIV",
    "cote divoire": "CIV",
    "swaziland": "SWZ",
    "uae": "ARE",
    "micronesia": "FSM",
    "syria": "SYR",
    "iran": "IRN",
    "moldova": "MDA",
    "tanzania": "TZA",
    "vietnam": "VNM",
    "laos": "LAO",
    "czech republic": "CZE",
    "bolivia": "BOL",
    "venezuela": "VEN",
    "palestine": "PSE",
    "russia": "RUS",
    "vatican": "VAT",
    "holy see": "VAT",
}

# Extra textual forms to use for DON narrative substring matching beyond what pycountry exposes.
# Many DONs use short/colloquial spellings.
_EXTRA_TEXT_HINTS: dict[str, list[str]] = {
    "USA": ["United States", "US", "U.S.", "America"],
    "GBR": ["United Kingdom", "UK", "U.K.", "Britain", "England"],
    "KOR": ["South Korea", "Republic of Korea"],
    "PRK": ["North Korea", "DPRK"],
    "RUS": ["Russia"],
    "CHN": ["China"],
    "COD": ["DRC", "DR Congo", "Democratic Republic of the Congo"],
    "COG": ["Congo-Brazzaville", "Republic of the Congo"],
    "MMR": ["Burma", "Myanmar"],
    "GMB": ["The Gambia", "Gambia"],
    "CIV": ["Ivory Coast", "Côte d'Ivoire"],
    "TZA": ["Tanzania", "United Republic of Tanzania"],
    "VNM": ["Vietnam", "Viet Nam"],
    "IRN": ["Iran"],
    "SYR": ["Syria"],
    "ARE": ["UAE", "United Arab Emirates"],
    "VEN": ["Venezuela"],
    "BOL": ["Bolivia"],
    "MDA": ["Moldova"],
    "SWZ": ["Eswatini", "Swaziland"],
    "CZE": ["Czechia", "Czech Republic"],
    "PSE": ["Palestine", "State of Palestine"],
    "FSM": ["Micronesia", "Federated States of Micronesia"],
    "VAT": ["Holy See", "Vatican"],
}


def norm_alias(s: str) -> str:
    t = " ".join((s or "").strip().lower().split())
    for ch in ".'’":
        t = t.replace(ch, "")
    return t


def iso3_for_alias(name: str) -> str | None:
    """Resolve a free-text country name to ISO3, or None if no confident match."""
    if not name or not name.strip():
        return None
    raw = name.strip()
    key = norm_alias(raw)

    if key in _OVERLAY_TO_ISO3:
        return _OVERLAY_TO_ISO3[key]

    try:
        c = pycountry.countries.lookup(raw)
        return getattr(c, "alpha_3", None)
    except LookupError:
        pass

    # Last-resort fuzzy search; pycountry returns a list ordered by score.
    try:
        hits = pycountry.countries.search_fuzzy(raw)
    except LookupError:
        return None
    return getattr(hits[0], "alpha_3", None) if hits else None


def country_text_hints(iso3: str, canonical_name: str | None = None) -> list[str]:
    """All textual forms worth substring-matching against narrative text for this country."""
    iso = (iso3 or "").upper()
    out: list[str] = []
    if canonical_name and canonical_name.strip():
        out.append(canonical_name.strip())

    try:
        c = pycountry.countries.get(alpha_3=iso)
    except (KeyError, LookupError):
        c = None
    if c is not None:
        for attr in ("name", "official_name", "common_name"):
            val = getattr(c, attr, None)
            if val and val not in out:
                out.append(val)

    for form in _EXTRA_TEXT_HINTS.get(iso, []):
        if form not in out:
            out.append(form)
    if iso and iso not in out:
        out.append(iso)
    return out
