from __future__ import annotations

from typing import Any

from who_sentinel.country_aliases import ALIASES_TO_ISO3, norm_alias
from who_sentinel.clients.gho import GhoClient


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _row_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "iso3": row.get("CountryCode"),
        "name": row.get("CountryName"),
        "region_code": row.get("RegionCode"),
        "region_name": row.get("RegionName"),
    }


def _ok(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "iso3": row.get("CountryCode"),
        "name": row.get("CountryName"),
        "region_code": row.get("RegionCode"),
        "region_name": row.get("RegionName"),
        "candidates": [],
        "error": None,
        "source": "gho_region_country",
    }


def _ambiguous(cands: list[dict[str, Any]], msg: str) -> dict[str, Any]:
    return {
        "ok": False,
        "iso3": None,
        "name": None,
        "region_code": None,
        "region_name": None,
        "candidates": [_row_public(r) for r in cands[:25]],
        "error": msg,
        "source": "gho_region_country",
    }


def resolve_country(gho: GhoClient, country: str) -> dict[str, Any]:
    """
    Resolve a user string to WHO GHO RegionCountry (full table + aliases).

    Uses the complete RegionCountry OData feed (cached), not a single contains() query.
    """
    raw = country.strip()
    if not raw:
        return {"ok": False, "error": "Empty country.", "candidates": [], "source": "gho_region_country"}

    cache_key = f"ccres:{_norm(raw)}"
    hit = gho.cache.get(cache_key)
    if hit is not None:
        return hit  # type: ignore[no-any-return]

    rows = gho.get_region_countries_full()
    by_code: dict[str, dict[str, Any]] = {}
    by_name_exact: dict[str, dict[str, Any]] = {}

    for row in rows:
        code = row.get("CountryCode")
        name = row.get("CountryName")
        if not code or not isinstance(name, str) or not name.strip():
            continue
        cu = str(code).upper()[:3]
        by_code[cu] = row
        nn = _norm(name)
        if nn not in by_name_exact:
            by_name_exact[nn] = row

    # 1) ISO3 direct
    if len(raw) == 3 and raw.isalpha() and raw.upper() in by_code:
        out = _ok(by_code[raw.upper()])
        gho.cache.set(cache_key, out)
        return out

    # 2) Curated aliases → ISO3 (only if present in this GHO table)
    alias_key = norm_alias(raw)
    iso_from_alias = ALIASES_TO_ISO3.get(alias_key)
    if iso_from_alias and iso_from_alias in by_code:
        out = _ok(by_code[iso_from_alias])
        gho.cache.set(cache_key, out)
        return out

    qn = _norm(raw)

    # 3) Exact country name (normalized)
    if qn in by_name_exact:
        out = _ok(by_name_exact[qn])
        gho.cache.set(cache_key, out)
        return out

    # 4) Substring match on official name (e.g. "congo" → COD + COG)
    matches = [
        row
        for row in rows
        if isinstance(row.get("CountryName"), str) and qn and qn in _norm(row["CountryName"])
    ]
    if len(matches) == 1:
        out = _ok(matches[0])
        gho.cache.set(cache_key, out)
        return out
    if len(matches) > 1:
        out = _ambiguous(matches, "Multiple countries match; pass a full official name or ISO3 code.")
        gho.cache.set(cache_key, out)
        return out

    # 5) Prefix match on first word (e.g. "Korea" still ambiguous — will list)
    if qn:
        prefix_hits = [
            row
            for row in rows
            if isinstance(row.get("CountryName"), str)
            and _norm(row["CountryName"]).startswith(qn)
        ]
        if len(prefix_hits) == 1:
            out = _ok(prefix_hits[0])
            gho.cache.set(cache_key, out)
            return out
        if len(prefix_hits) > 1:
            out = _ambiguous(prefix_hits, "Several country names start with this text; use ISO3 or full name.")
            gho.cache.set(cache_key, out)
            return out

    out = {
        "ok": False,
        "iso3": None,
        "name": None,
        "region_code": None,
        "region_name": None,
        "candidates": [],
        "error": "No match in WHO GHO RegionCountry. Use list_gho_countries or a 3-letter ISO3 code.",
        "source": "gho_region_country",
        "registry_country_count": len(by_code),
    }
    gho.cache.set(cache_key, out)
    return out


def filter_countries(
    rows: list[dict[str, Any]],
    query: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Client-side filter over RegionCountry rows."""
    lim = max(1, min(int(limit), 500))
    if not query or not query.strip():
        slim = [_row_public(r) for r in rows[:lim]]
        return slim

    qn = _norm(query)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row.get("CountryName"), str):
            continue
        name = _norm(row["CountryName"])
        code = str(row.get("CountryCode") or "").upper()
        if qn in name or qn in code.lower():
            out.append(_row_public(row))
        if len(out) >= lim:
            break
    return out
