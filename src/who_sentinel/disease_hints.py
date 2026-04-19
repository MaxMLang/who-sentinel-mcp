"""Curated + auto-generated disease keyword → IndicatorCode hints.

The list is loaded from ``data/disease_hints.json`` so the auto-generated half
can be refreshed weekly by ``scripts/refresh_disease_hints.py`` without code
changes. The curated overlay is editorial and survives the refresh.
"""

from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any

_HINTS_RESOURCE = files("who_sentinel.data").joinpath("disease_hints.json")


def _load_topics() -> list[dict[str, Any]]:
    with _HINTS_RESOURCE.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    topics = data.get("topics") or []
    return [t for t in topics if isinstance(t, dict)]


_TOPICS: list[dict[str, Any]] = _load_topics()


def _topic_matches(topic: dict[str, Any], q: str) -> bool:
    for kw in topic.get("keywords") or []:
        if isinstance(kw, str) and kw.strip().lower() in q:
            return True
    for tok in topic.get("word_keywords") or []:
        if not isinstance(tok, str) or not tok.strip():
            continue
        if re.search(rf"\b{re.escape(tok.strip().lower())}\b", q):
            return True
    return False


def curated_hints_for_query(disease_query: str) -> list[dict[str, Any]]:
    """Indicator hints whose topic keywords match the query (curated first, then auto-generated)."""
    q = (disease_query or "").strip().lower()
    if not q:
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for topic in _TOPICS:
        if not _topic_matches(topic, q):
            continue

        for ind in topic.get("curated") or []:
            code = str(ind.get("code") or "")
            if not code or code in seen:
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

        for ind in topic.get("auto_generated") or []:
            code = str(ind.get("code") or "")
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(
                {
                    "IndicatorCode": code,
                    "IndicatorName": str(ind.get("name") or ""),
                    "source": "auto_generated_from_gho",
                }
            )
    return out


def curated_groups_matched_count(disease_query: str) -> int:
    """How many topics match the query (any keyword in the topic)."""
    q = (disease_query or "").strip().lower()
    if not q:
        return 0
    return sum(1 for t in _TOPICS if _topic_matches(t, q))


def merge_indicator_candidates(
    curated: list[dict[str, Any]],
    search_rows: list[dict[str, str]],
    *,
    search_limit: int = 25,
) -> list[dict[str, Any]]:
    """Curated hints first, then GHO live search results; dedupe by IndicatorCode."""
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
