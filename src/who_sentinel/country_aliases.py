"""Common English aliases and ISO3 shortcuts → GHO CountryCode (WHO RegionCountry)."""

from __future__ import annotations

# Keys: normalized with _norm_alias (lowercase, collapsed whitespace, no punctuation variants handled separately).
ALIASES_TO_ISO3: dict[str, str] = {
    # United States
    "usa": "USA",
    "u s a": "USA",
    "us": "USA",
    "united states": "USA",
    "united states of america": "USA",
    "america": "USA",
    # United Kingdom
    "uk": "GBR",
    "u k": "GBR",
    "united kingdom": "GBR",
    "great britain": "GBR",
    "britain": "GBR",
    "england": "GBR",
    "scotland": "GBR",
    "wales": "GBR",
    "northern ireland": "GBR",
    # Korea
    "south korea": "KOR",
    "korea": "KOR",
    "republic of korea": "KOR",
    "north korea": "PRK",
    "democratic peoples republic of korea": "PRK",
    "dprk": "PRK",
    # China (WHO GHO RegionCountry does not list separate ISO3 for Taiwan/HK/Mac in this table)
    "china": "CHN",
    "peoples republic of china": "CHN",
    "prc": "CHN",
    # Russia / USSR legacy
    "russia": "RUS",
    "russian federation": "RUS",
    "ussr": "RUS",
    "soviet union": "RUS",
    # EU shortcuts (map to member — users should prefer ISO3)
    "vietnam": "VNM",
    "viet nam": "VNM",
    "laos": "LAO",
    "czech republic": "CZE",
    "czechia": "CZE",
    "bolivia": "BOL",
    "venezuela": "VEN",
    "syria": "SYR",
    "syrian arab republic": "SYR",
    "iran": "IRN",
    "iran islamic republic of": "IRN",
    "moldova": "MDA",
    "palestine": "PSE",
    "state of palestine": "PSE",
    "tanzania": "TZA",
    "united republic of tanzania": "TZA",
    "swaziland": "SWZ",
    "eswatini": "SWZ",
    "burma": "MMR",
    "myanmar": "MMR",
    "ivory coast": "CIV",
    "cote divoire": "CIV",
    "côte divoire": "CIV",
    "the gambia": "GMB",
    "gambia": "GMB",
    "democratic republic of the congo": "COD",
    "drc": "COD",
    "dr congo": "COD",
    "republic of the congo": "COG",
    "congo brazzaville": "COG",
    "uae": "ARE",
    "united arab emirates": "ARE",
    "micronesia": "FSM",
    "federated states of micronesia": "FSM",
}


def norm_alias(s: str) -> str:
    t = " ".join(s.strip().lower().split())
    for ch in ".'’":
        t = t.replace(ch, "")
    return t
