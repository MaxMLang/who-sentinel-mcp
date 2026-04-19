from __future__ import annotations

import atexit
import json
import logging
import os
import time
import traceback
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from who_sentinel import metrics
from who_sentinel.cache import TTLCache, country_registry_ttl_sec, effective_cache_ttl_sec
from who_sentinel.clients.don import (
    DonClient,
    don_public_url,
    filter_outbreak_rows,
    outbreak_narrative_text,
    outbreak_summary_row,
)
from who_sentinel.clients.gho import GhoClient
from who_sentinel.constants import (
    ATTRIBUTION_PREFIX,
    GHO_MAX_TOP,
    RESPONSE_DISCLAIMER_SHORT,
    SERVER_INSTRUCTIONS,
)
from who_sentinel.countries import filter_countries, resolve_country
from who_sentinel.extract import extract_outbreak_metadata as extract_meta
from who_sentinel.extract import extract_result_to_dict
from who_sentinel.logging_config import configure_logging
from who_sentinel.rate_limit import http_budget_per_minute
from who_sentinel.sentinel import (
    compute_spatial_vulnerability_index,
    run_compare_gho_countries,
    run_surveillance_synthesis,
)
from who_sentinel.static_docs import GHO_BASICS, LIMITATIONS, TRUST_AND_USE

_cache = TTLCache()
_gho = GhoClient(cache=_cache)
_don = DonClient()

atexit.register(_gho.close)
atexit.register(_don.close)

_log = logging.getLogger("who_sentinel")

mcp = FastMCP("who-sentinel", instructions=SERVER_INSTRUCTIONS)


@mcp.resource("who-sentinel://docs/gho-basics", mime_type="text/markdown")
def resource_gho_basics() -> str:
    return GHO_BASICS


@mcp.resource("who-sentinel://docs/limitations", mime_type="text/markdown")
def resource_limitations() -> str:
    return LIMITATIONS


@mcp.resource("who-sentinel://docs/trust-and-use", mime_type="text/markdown")
def resource_trust_and_use() -> str:
    return TRUST_AND_USE


def _json_out(payload: Any) -> str:
    if isinstance(payload, dict):
        meta = payload.get("who_sentinel_meta")
        if not isinstance(meta, dict):
            meta = {}
        meta = {
            **meta,
            "disclaimer": RESPONSE_DISCLAIMER_SHORT,
            "data_licensing": "CC BY 4.0 (see attribution prefix in responses).",
        }
        payload = {**payload, "who_sentinel_meta": meta}
    return ATTRIBUTION_PREFIX + json.dumps(payload, ensure_ascii=False, indent=2)


def _err_out(exc: BaseException) -> str:
    payload: dict[str, Any] = {"error": str(exc), "error_type": type(exc).__name__}
    if _log.isEnabledFor(logging.DEBUG):
        payload["traceback"] = traceback.format_exc()
    return _json_out(payload)


def _run_tool(tool_name: str, body: Callable[[], str]) -> str:
    t0 = time.perf_counter()
    try:
        return body()
    finally:
        # Record after the call so get_server_limits reports counts of *prior* calls.
        metrics.record_tool(tool_name)
        _log.info("tool=%s duration_ms=%.1f", tool_name, (time.perf_counter() - t0) * 1000.0)


@mcp.tool()
def search_gho_indicators(query: str) -> str:
    """Search WHO GHO indicators by keyword (IndicatorName contains query). Returns IndicatorCode rows."""

    def _inner() -> str:
        try:
            rows = _gho.search_indicators(query.strip(), top=40)
            return _json_out({"indicators": rows, "truncated_to": 40})
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("search_gho_indicators", _inner)


@mcp.tool()
def list_gho_countries(query: str | None = None, limit: int = 300) -> str:
    """List countries from the full WHO GHO RegionCountry table (cached). Optional substring/code filter."""

    def _inner() -> str:
        try:
            rows = _gho.get_region_countries_full()
            filtered = filter_countries(rows, query, limit)
            return _json_out(
                {
                    "total_in_registry": len(rows),
                    "count_returned": len(filtered),
                    "countries": filtered,
                }
            )
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("list_gho_countries", _inner)


@mcp.tool()
def resolve_gho_country(country: str) -> str:
    """Resolve a country name or ISO3 using the full GHO RegionCountry registry (includes WHO region fields)."""

    def _inner() -> str:
        try:
            return _json_out(resolve_country(_gho, country))
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("resolve_gho_country", _inner)


@mcp.tool()
def list_gho_indicator_dimensions(indicator_code: str, language: str = "EN", limit: int = 50) -> str:
    """List OData dimensions for an indicator (e.g. COUNTRY, YEAR) from GHO IndicatorDimension."""

    def _inner() -> str:
        try:
            rows = _gho.list_indicator_dimensions(indicator_code.strip(), language=language.strip() or "EN", top=limit)
            return _json_out({"indicator_code": indicator_code.strip(), "dimensions": rows})
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("list_gho_indicator_dimensions", _inner)


@mcp.tool()
def list_gho_entity_sets(name_contains: str | None = None, limit: int = 200) -> str:
    """Browse entity sets exposed by GET /api (Indicator, RegionCountry, and thousands of per-indicator collections)."""

    def _inner() -> str:
        try:
            cats = _gho.get_api_entity_catalog()
            lim = max(1, min(int(limit), 2000))
            needle = (name_contains or "").strip().lower()
            out: list[dict[str, Any]] = []
            for item in cats:
                name = str(item.get("name") or "")
                url = str(item.get("url") or "")
                if needle and needle not in name.lower() and needle not in url.lower():
                    continue
                out.append({"name": name, "kind": item.get("kind"), "url": url})
                if len(out) >= lim:
                    break
            return _json_out(
                {
                    "total_catalog_entries": len(cats),
                    "count_returned": len(out),
                    "entity_sets": out,
                    "note": "Most names are IndicatorCode-backed data entity sets; use search_gho_indicators to pick codes.",
                }
            )
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("list_gho_entity_sets", _inner)


@mcp.tool()
def get_latest_outbreaks(limit: int = 5, disease_query: str | None = None) -> str:
    """List recent Disease Outbreak News items (newest first). Optionally filter by disease keyword."""

    def _inner() -> str:
        try:
            lim = max(1, min(int(limit), 100))
            fetch_n = lim if not disease_query else min(100, max(lim * 6, 25))
            rows = _don.list_recent(fetch_n)
            filtered = filter_outbreak_rows(rows, disease_query, None)
            use = filtered if disease_query else rows
            summaries = [outbreak_summary_row(r) for r in use[:lim]]
            return _json_out(
                {
                    "count_returned": len(summaries),
                    "disease_query": disease_query,
                    "items": summaries,
                }
            )
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("get_latest_outbreaks", _inner)


@mcp.tool()
def get_full_report(don_id: str) -> str:
    """Fetch a full DON record by its Id (UUID)."""

    def _inner() -> str:
        try:
            row = _don.get_by_id(don_id.strip())
            if not row:
                return _json_out({"error": "Not found", "don_id": don_id})
            slim = {
                k: row.get(k)
                for k in (
                    "Id",
                    "Title",
                    "PublicationDate",
                    "PublicationDateAndTime",
                    "UrlName",
                    "ItemDefaultUrl",
                    "Summary",
                    "Overview",
                    "Response",
                    "Assessment",
                    "Advice",
                    "Epidemiology",
                    "DonId",
                )
            }
            slim["public_url"] = don_public_url(row)
            return _json_out(slim)
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("get_full_report", _inner)


@mcp.tool()
def surveillance_synthesis(
    disease: str,
    country: str,
    indicator_code: str | None = None,
    prior_years_for_baseline: int | None = None,
    baseline_latest_year: int | None = None,
) -> str:
    """Research-oriented DON + GHO synthesis (not outbreak response or clinical use); verify IndicatorCode against GHO metadata."""

    def _inner() -> str:
        try:
            out = run_surveillance_synthesis(
                _gho,
                _don,
                disease,
                country,
                indicator_code,
                prior_years_for_baseline=prior_years_for_baseline,
                baseline_latest_year=baseline_latest_year,
            )
            return _json_out(out)
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("surveillance_synthesis", _inner)


@mcp.tool()
def compare_gho_countries(
    indicator_code: str,
    country_a: str,
    country_b: str,
) -> str:
    """Compare one GHO indicator across two countries; check overlap_years and comparison_notes—latest years may differ."""

    def _inner() -> str:
        try:
            out = run_compare_gho_countries(_gho, indicator_code, country_a, country_b)
            return _json_out(out)
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("compare_gho_countries", _inner)


@mcp.tool()
def get_server_limits() -> str:
    """Effective cache TTLs, OData limits, logging/rate-limit env, and in-process metrics for this server."""

    def _inner() -> str:
        try:
            return _json_out(
                {
                    "who_sentinel_cache_ttl_sec": effective_cache_ttl_sec(),
                    "who_sentinel_country_registry_ttl_sec": country_registry_ttl_sec(),
                    "gho_odata_max_top": GHO_MAX_TOP,
                    "who_sentinel_log_level": os.environ.get("WHO_SENTINEL_LOG_LEVEL", "WARNING"),
                    "who_sentinel_effective_log_level": logging.getLevelName(logging.getLogger().getEffectiveLevel()),
                    "who_sentinel_max_http_per_minute": http_budget_per_minute(),
                    "metrics": metrics.snapshot(),
                    "note": "Prefer cached tools; avoid rapid repeated calls to WHO endpoints.",
                }
            )
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("get_server_limits", _inner)


@mcp.tool()
def extract_outbreak_metadata(don_id: str) -> str:
    """Regex/heuristic case & CFR hints from DON text (non-clinical); always verify figures in the published report."""

    def _inner() -> str:
        try:
            row = _don.get_by_id(don_id.strip())
            if not row:
                return _json_out({"error": "Not found", "don_id": don_id})
            text = outbreak_narrative_text(row)
            er = extract_meta(text)
            payload = extract_result_to_dict(er)
            payload["don_id"] = row.get("Id")
            payload["title"] = row.get("Title")
            payload["public_url"] = don_public_url(row)
            return _json_out(payload)
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("extract_outbreak_metadata", _inner)


@mcp.tool()
def spatial_vulnerability_index(country: str) -> str:
    """Heuristic composite score from a few GHO indicators—not an official WHO index; not for individual or clinical decisions."""

    def _inner() -> str:
        try:
            out = compute_spatial_vulnerability_index(_gho, country)
            return _json_out(out)
        except Exception as e:  # noqa: BLE001
            return _err_out(e)

    return _run_tool("spatial_vulnerability_index", _inner)


@mcp.prompt(name="who_sentinel_workflow", description="Recommended steps for disease surveillance with this MCP")
def who_sentinel_workflow() -> list[dict[str, Any]]:
    """Guide the model through country resolution, indicator choice, and synthesis."""
    text = (
        "Use WHO-Sentinel in this order:\n"
        "1) Resolve the country: use resolve_gho_country or list_gho_countries (full WHO RegionCountry table).\n"
        "2) If surveillance_synthesis returns needs_indicator, pick indicator_code from "
        "indicator_candidates (curated hints first), matching the disease to the indicator semantics.\n"
        "3) Call search_gho_indicators if you need more codes.\n"
        "4) Use get_latest_outbreaks / get_full_report for DON narrative; extract_outbreak_metadata for numeric hints.\n"
        "5) compare_gho_countries for two-country indicator comparison; list_gho_indicator_dimensions for COUNTRY/YEAR.\n"
        "6) get_server_limits and resources who-sentinel://docs/* (including trust-and-use) for limits and policy context.\n"
        "7) spatial_vulnerability_index is a heuristic composite—not an official WHO score.\n"
        "Outputs are prefixed with WHO data attribution; this is not clinical advice."
    )
    return [{"role": "user", "content": {"type": "text", "text": text}}]


def main() -> None:
    configure_logging()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
