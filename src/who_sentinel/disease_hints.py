"""Curated disease keyword → GHO IndicatorCode hints (supplement to live Indicator search)."""

from __future__ import annotations

import re
from typing import Any

# Keywords match the lowercase query as substrings; tuples ("word", "tb") use \btoken\b
# regex matching so short tokens like "tb" don't fire on "stable" or "tabular".
DISEASE_HINT_GROUPS: list[dict[str, Any]] = [
    {
        "keywords": ("cholera", "v. cholerae"),
        "indicators": [
            {
                "code": "CHOLERA_0000000001",
                "rationale": "Number of reported cases of cholera (annual, country)",
                "caveat": "Annual reported cases; not incidence if surveillance coverage varies.",
            },
            {
                "code": "CHOLERA_0000000003",
                "rationale": "Cholera case fatality rate (annual, country)",
                "verify_with_indicator_name": "Confirm CFR definition in GHO metadata for this code.",
            },
        ],
    },
    {
        "keywords": ("malaria", "plasmodium"),
        "indicators": [
            {
                "code": "MALARIA_CONF_CASES",
                "rationale": "Number of confirmed malaria cases",
            },
            {
                "code": "MALARIA_1STLINE_TREATED",
                "rationale": "Malaria cases treated with first-line courses (incl. ACTs)",
            },
        ],
    },
    {
        "keywords": ("measles", "rubeola"),
        "indicators": [
            {
                "code": "mslv",
                "rationale": "Measles immunization coverage among one-year-olds (%)",
            },
        ],
    },
    {
        "keywords": ("tuberculosis", ("word", "tb")),
        "indicators": [
            {
                "code": "MDG_0000000020",
                "rationale": "Incidence of tuberculosis (per 100 000 population per year)",
            },
        ],
    },
    {
        "keywords": ("influenza", "h5n1", "h7n9", "h1n1"),
        "indicators": [
            {
                "code": "WHS3_51",
                "rationale": "H5N1 influenza — number of reported cases",
            },
        ],
    },
]


def _keyword_matches(kw: Any, q: str) -> bool:
    """Match a single curated keyword spec against a normalized lowercase query."""
    if isinstance(kw, str):
        return kw.strip().lower() in q
    if isinstance(kw, tuple) and len(kw) == 2 and kw[0] == "word":
        token = str(kw[1]).strip().lower()
        if not token:
            return False
        return re.search(rf"\b{re.escape(token)}\b", q) is not None
    return False


def _group_matches(group: dict[str, Any], q: str) -> bool:
    return any(_keyword_matches(kw, q) for kw in group["keywords"])


def curated_hints_for_query(disease_query: str) -> list[dict[str, Any]]:
    """Return curated indicator hints whose keyword groups match the query."""
    q = disease_query.strip().lower()
    if not q:
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for group in DISEASE_HINT_GROUPS:
        if not _group_matches(group, q):
            continue
        for ind in group["indicators"]:
            code = str(ind["code"])
            if code in seen:
                continue
            seen.add(code)
            row: dict[str, Any] = {
                "IndicatorCode": code,
                "IndicatorName": ind.get("rationale", ""),
                "source": "curated_hint",
            }
            if "caveat" in ind:
                row["caveat"] = str(ind["caveat"])
            if "verify_with_indicator_name" in ind:
                row["verify_with_indicator_name"] = str(ind["verify_with_indicator_name"])
            out.append(row)
    return out


def curated_groups_matched_count(disease_query: str) -> int:
    """How many keyword groups in DISEASE_HINT_GROUPS match the query (any keyword in group)."""
    q = disease_query.strip().lower()
    if not q:
        return 0
    return sum(1 for group in DISEASE_HINT_GROUPS if _group_matches(group, q))


def merge_indicator_candidates(
    curated: list[dict[str, Any]],
    search_rows: list[dict[str, str]],
    *,
    search_limit: int = 25,
) -> list[dict[str, Any]]:
    """Curated hints first, then GHO search results; dedupe by IndicatorCode."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in curated:
        code = row.get("IndicatorCode") or ""
        if not code or code in seen:
            continue
        seen.add(code)
        merged.append(dict(row))

    for row in search_rows:
        code = row.get("IndicatorCode") or ""
        if not code or code in seen:
            continue
        seen.add(code)
        merged.append(
            {
                "IndicatorCode": code,
                "IndicatorName": row.get("IndicatorName", ""),
                "source": "gho_search",
            }
        )
        if len(merged) >= search_limit:
            break

    return merged
