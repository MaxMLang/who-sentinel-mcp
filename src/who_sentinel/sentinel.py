from __future__ import annotations

import re
import statistics
from typing import Any

from who_sentinel.clients.don import DonClient, filter_outbreak_rows, outbreak_summary_row
from who_sentinel.clients.gho import GhoClient
from who_sentinel.countries import resolve_country
from who_sentinel.country_aliases import country_text_hints
from who_sentinel.disease_hints import (
    curated_groups_matched_count,
    curated_hints_for_query,
    merge_indicator_candidates,
)

# Words too generic to be evidence that an IndicatorName actually covers a disease query.
_DISEASE_QUERY_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "into", "out", "outbreak", "outbreaks",
    "case", "cases", "disease", "diseases", "epidemic", "epidemics", "pandemic",
    "incidence", "rate", "rates", "data", "infection", "infections", "report",
    "reports", "death", "deaths", "country", "countries", "year", "years",
})


def _disease_query_tokens(disease_q: str) -> list[str]:
    """Alphabetic tokens >=3 chars from the disease query, minus generic stopwords."""
    raw = re.findall(r"[a-zA-Z]+", (disease_q or "").lower())
    return [t for t in raw if len(t) >= 3 and t not in _DISEASE_QUERY_STOPWORDS]


def _validate_indicator_for_disease(
    meta: dict[str, Any] | None,
    disease_q: str,
) -> dict[str, Any]:
    tokens = _disease_query_tokens(disease_q)
    name = ((meta or {}).get("IndicatorName") or "").lower()

    if not tokens:
        return {
            "confidence": "unknown",
            "reason": "Disease query has no distinctive tokens to compare against IndicatorName.",
            "matched_disease_tokens": [],
        }
    if not name:
        return {
            "confidence": "unknown",
            "reason": "No IndicatorName available from GHO metadata.",
            "matched_disease_tokens": [],
        }

    matched = [t for t in tokens if t in name]
    if matched:
        return {"confidence": "ok", "matched_disease_tokens": matched}
    return {
        "confidence": "warning",
        "reason": (
            "IndicatorName shares no distinctive keywords with your disease query. "
            "Confirm this is the right code, or re-call with confirm_indicator=True."
        ),
        "matched_disease_tokens": [],
        "indicator_name": (meta or {}).get("IndicatorName"),
    }


def _pct_deviation(latest: float, baseline_mean: float) -> float | None:
    if baseline_mean == 0:
        return None
    return round(100.0 * (latest - baseline_mean) / baseline_mean, 2)


def _clamp_prior_years(n: int | None) -> int:
    if n is None:
        return 10
    return max(1, min(20, int(n)))


def run_surveillance_synthesis(
    gho: GhoClient,
    don: DonClient,
    disease: str,
    country: str,
    indicator_code: str | None,
    *,
    prior_years_for_baseline: int | None = None,
    baseline_latest_year: int | None = None,
    confirm_indicator: bool = False,
) -> dict[str, Any]:
    """Merge DON recent narrative signal with GHO historical baseline statistics."""

    cc = resolve_country(gho, country)
    if not cc.get("ok"):
        return {
            "status": "needs_country",
            "country_resolution": cc,
            "disease_query": disease,
            "indicator_code": indicator_code,
        }

    iso3 = str(cc.get("iso3"))
    disease_q = disease.strip()

    if not indicator_code or not indicator_code.strip():
        curated = curated_hints_for_query(disease_q)
        groups_n = curated_groups_matched_count(disease_q)
        search_rows = gho.search_indicators(disease_q, top=15)
        merged = merge_indicator_candidates(curated, search_rows, search_limit=40)
        payload: dict[str, Any] = {
            "status": "needs_indicator",
            "message": (
                "Pass indicator_code from indicator_candidates (curated hints are listed first when "
                "they match your disease keywords; confirm the code fits your analytic question)."
            ),
            "country_resolution": cc,
            "disease_query": disease_q,
            "indicator_candidates": merged,
            "curated_match_count": len(curated),
            "curated_keyword_groups_matched": groups_n,
        }
        if len(merged) > 8 or groups_n > 1:
            payload["indicator_selection_guidance"] = (
                "Many candidate indicators or multiple disease-keyword groups matched. "
                "Use search_gho_indicators to narrow IndicatorCode choices, then "
                "list_gho_indicator_dimensions to confirm dimensions (e.g. COUNTRY, YEAR) "
                "before interpreting values."
            )
        return payload

    code = indicator_code.strip()
    meta = gho.get_indicator_meta(code)

    code_validation = _validate_indicator_for_disease(meta, disease_q)
    if code_validation["confidence"] == "warning" and not confirm_indicator:
        curated = curated_hints_for_query(disease_q)
        search_rows = gho.search_indicators(disease_q, top=15)
        merged = merge_indicator_candidates(curated, search_rows, search_limit=40)
        return {
            "status": "indicator_validation_warning",
            "country_resolution": cc,
            "disease_query": disease_q,
            "indicator_code": code,
            "indicator": meta,
            "code_provenance": "user_supplied",
            "code_validation": code_validation,
            "indicator_candidates": merged,
            "message": (
                "Refused to compute a baseline because the chosen IndicatorName does not "
                "appear to match your disease query. Re-call with confirm_indicator=True "
                "to override, or pick a different IndicatorCode from indicator_candidates."
            ),
        }

    series = gho.fetch_country_year_series(code, iso3, max_points=30)
    numeric_rows = [r for r in series if r.get("numeric_value") is not None]
    if len(numeric_rows) < 2:
        return {
            "status": "insufficient_gho",
            "country_resolution": cc,
            "indicator": meta,
            "code_provenance": "user_supplied",
            "code_validation": code_validation,
            "series_points": len(numeric_rows),
            "note": "Not enough yearly numeric points to compute a baseline.",
        }

    n_prior = _clamp_prior_years(prior_years_for_baseline)

    if baseline_latest_year is not None:
        anchor = int(baseline_latest_year)
        matching = [r for r in numeric_rows if r.get("year") == anchor]
        if not matching:
            years_avail = sorted({r.get("year") for r in numeric_rows if r.get("year") is not None})
            return {
                "status": "baseline_year_not_found",
                "country_resolution": cc,
                "indicator": meta,
                "requested_baseline_latest_year": anchor,
                "years_available": years_avail,
                "note": "No GHO point for this indicator/country in the requested year.",
            }
        latest_row = matching[0]
    else:
        latest_row = numeric_rows[0]

    latest_year = latest_row.get("year")
    latest_val = float(latest_row["numeric_value"])  # type: ignore[arg-type]
    latest_low = latest_row.get("value_low")
    latest_high = latest_row.get("value_high")

    ly = int(latest_year) if latest_year is not None else 0
    prior = [r for r in numeric_rows if r.get("year") is not None and int(r["year"]) < ly]  # type: ignore[arg-type]
    window = prior[:n_prior]
    years_used = [r.get("year") for r in window]
    vals = [float(r["numeric_value"]) for r in window]  # type: ignore[arg-type]
    baseline_mean = float(statistics.mean(vals)) if vals else float("nan")

    pct = _pct_deviation(latest_val, baseline_mean) if vals else None

    method = "anchored_year_vs_prior" if baseline_latest_year is not None else "latest_series_year_vs_prior"
    if baseline_latest_year is None and prior_years_for_baseline is None:
        method_key = "latest_completed_year_vs_mean_of_up_to_10_prior_years_in_series"
    else:
        method_key = f"custom_{method}_mean_of_{n_prior}_prior_years"

    recent = don.list_recent(limit=40)
    country_name = str(cc.get("name") or "")
    country_hints = country_text_hints(iso3, country_name)
    matched = filter_outbreak_rows(recent, disease_q, country_hints=country_hints)
    top = [outbreak_summary_row(r) for r in matched[:5]]

    direction = "above" if pct is not None and pct > 0 else "below" if pct is not None and pct < 0 else "near"
    alert = (
        f"Latest GHO value for {country_name} ({iso3}) on '{meta.get('IndicatorName') if meta else code}' "
        f"is {latest_val} ({latest_year}). "
    )
    if pct is None:
        alert += "Baseline could not be computed."
    else:
        alert += (
            f"Compared to the mean of the prior {len(vals)} year(s) in GHO ({years_used}), "
            f"this is {abs(pct):.2f}% {direction} that baseline."
        )

    if top:
        alert += f" DON reports matching disease/country hints: {len(matched)} (showing up to 5 excerpts)."
    else:
        alert += " No recent DON items matched the disease/country text filters in the scanned window."

    if baseline_latest_year is not None:
        desc = (
            f"Series is GHO annual values for this indicator and country, newest first. "
            f"Anchor year={latest_year}, value={latest_val}. "
            f"Baseline mean uses up to {n_prior} older year(s) strictly before the anchor ({years_used}). "
            f"Deviation compares anchor to the mean of those prior years."
        )
    elif prior_years_for_baseline is not None:
        desc = (
            f"Latest year in series={latest_year}, value={latest_val}. "
            f"Baseline mean uses up to {n_prior} prior year(s) ({years_used}). "
            f"Deviation compares latest to the mean of those prior years."
        )
    else:
        desc = (
            f"Series is GHO annual values for this indicator and country, newest first. "
            f"Latest year={latest_year}, value={latest_val}. "
            f"Baseline mean uses up to {n_prior} older consecutive points in that series "
            f"(years {years_used}). "
            f"Deviation compares latest only to the mean of those prior years."
        )

    baseline_assumptions = [
        "Baseline compares the anchor or latest series year to the arithmetic mean of prior years in the GHO series (not a formal trend or forecast model).",
        "Series may have gaps; years without a numeric value are omitted from the mean.",
        "WHO publishes Low/High bounds on some rows; when absent, only point estimates are available.",
    ]

    latest_payload: dict[str, Any] = {
        "year": latest_year,
        "value": latest_val,
        "gho_last_updated": latest_row.get("gho_last_updated"),
        "period_begin": latest_row.get("period_begin"),
        "period_end": latest_row.get("period_end"),
    }
    if latest_low is not None:
        latest_payload["value_low"] = latest_low
    if latest_high is not None:
        latest_payload["value_high"] = latest_high

    return {
        "status": "ok",
        "contextual_alert": alert,
        "country_resolution": cc,
        "indicator": meta,
        "code_provenance": "user_supplied",
        "code_validation": code_validation,
        "latest": latest_payload,
        "baseline": {
            "method": method_key,
            "description": desc,
            "assumptions": baseline_assumptions,
            "prior_years_requested": n_prior,
            "baseline_latest_year_param": baseline_latest_year,
            "latest_year": latest_year,
            "latest_value": latest_val,
            "prior_years": years_used,
            "prior_values": vals,
            "prior_year_count": len(vals),
            "mean_of_prior_years": baseline_mean,
            "mean_prior_years": baseline_mean,
            "percent_deviation_latest_vs_prior_mean": pct,
            "percent_deviation_vs_mean": pct,
        },
        "don_matches": top,
    }


def run_compare_gho_countries(
    gho: GhoClient,
    indicator_code: str,
    country_a: str,
    country_b: str,
) -> dict[str, Any]:
    """Compare latest GHO value and recent overlap for one indicator across two countries."""
    ca = resolve_country(gho, country_a)
    cb = resolve_country(gho, country_b)
    if not ca.get("ok"):
        return {"status": "needs_country", "which": "country_a", "country_resolution": ca}
    if not cb.get("ok"):
        return {"status": "needs_country", "which": "country_b", "country_resolution": cb}

    iso_a = str(ca.get("iso3"))
    iso_b = str(cb.get("iso3"))
    code = indicator_code.strip()
    meta = gho.get_indicator_meta(code)

    sa = gho.fetch_country_year_series(code, iso_a, max_points=30)
    sb = gho.fetch_country_year_series(code, iso_b, max_points=30)

    def latest_nr(series: list[dict[str, Any]]) -> dict[str, Any] | None:
        for r in series:
            if r.get("numeric_value") is not None:
                return r
        return None

    la = latest_nr(sa)
    lb = latest_nr(sb)
    years_a = {r.get("year") for r in sa if r.get("numeric_value") is not None and r.get("year") is not None}
    years_b = {r.get("year") for r in sb if r.get("numeric_value") is not None and r.get("year") is not None}
    overlap = sorted(years_a & years_b, reverse=True)

    comparison_notes: list[str] = []
    if len(overlap) < 3:
        comparison_notes.append(
            f"Few overlapping years with numeric data ({len(overlap)}); comparing latest values may be misleading if reporting years differ."
        )
    ya = la.get("year") if la else None
    yb = lb.get("year") if lb else None
    if la and lb and ya is not None and yb is not None and ya != yb:
        comparison_notes.append(f"Latest numeric rows use different years ({ya} vs {yb}).")

    out: dict[str, Any] = {
        "status": "ok",
        "indicator": meta,
        "country_a": {**ca, "iso3": iso_a},
        "country_b": {**cb, "iso3": iso_b},
        "overlap_years_count": len(overlap),
        "overlap_years_sample": overlap[:15],
        "series_a_latest": la,
        "series_b_latest": lb,
        "comparison_notes": comparison_notes,
    }

    if la and lb and la.get("numeric_value") is not None and lb.get("numeric_value") is not None:
        va = float(la["numeric_value"])  # type: ignore[arg-type]
        vb = float(lb["numeric_value"])  # type: ignore[arg-type]
        out["delta_a_minus_b"] = round(va - vb, 6)
        if vb != 0:
            out["ratio_a_over_b"] = round(va / vb, 6)
        else:
            out["ratio_a_over_b"] = None

    return out


# --- INFORM Risk Index passthrough (HDX HAPI) ----------------------------------------
# We stopped computing a homegrown vulnerability composite. The tool now fetches the
# published INFORM Risk Index (UN OCHA / EC JRC) for a country via HDX HAPI and
# returns its scores as-is, so consumers see a peer-reviewed methodology instead of
# our own weights. INFORM is updated twice yearly.

_INFORM_LINKS = {
    "methodology": "https://drmkc.jrc.ec.europa.eu/inform-index/INFORM-Risk/Methodology",
    "dataset": "https://data.humdata.org/dataset/inform-risk-index",
    "api_endpoint": "https://hapi.humdata.org/api/v1/coordination-context/national-risk",
}


def _inform_scores_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_risk_0_10": row.get("overall_risk"),
        "hazard_exposure_risk_0_10": row.get("hazard_exposure_risk"),
        "vulnerability_risk_0_10": row.get("vulnerability_risk"),
        "coping_capacity_risk_0_10": row.get("coping_capacity_risk"),
        "risk_class": row.get("risk_class"),
        "global_rank": row.get("global_rank"),
    }


def fetch_inform_risk_index(gho: GhoClient, hdx: Any, country: str) -> dict[str, Any]:
    """Return the latest INFORM Risk Index row for a country, with metadata."""
    cc = resolve_country(gho, country)
    if not cc.get("ok"):
        return {"status": "needs_country", "country_resolution": cc}

    iso3 = str(cc.get("iso3"))
    name = str(cc.get("name"))

    try:
        row = hdx.get_inform_national_risk(iso3)
    except RuntimeError as e:
        return {
            "status": "needs_config",
            "error": str(e),
            "country": {"iso3": iso3, "name": name},
            "links": _INFORM_LINKS,
        }

    if not row:
        return {
            "status": "no_data",
            "country": {"iso3": iso3, "name": name},
            "links": _INFORM_LINKS,
            "note": "INFORM Risk Index has no published row for this country in the current release.",
        }

    return {
        "status": "ok",
        "country": {"iso3": iso3, "name": name},
        "source": "INFORM Risk Index (UN OCHA / EC JRC) via HDX HAPI",
        "license": "CC BY 4.0",
        "scores": _inform_scores_payload(row),
        "data_quality": {
            "missing_indicators_pct": row.get("meta_missing_indicators_pct"),
            "average_recentness_years": row.get("meta_avg_recentness_years"),
        },
        "reference_period": {
            "start": row.get("reference_period_start"),
            "end": row.get("reference_period_end"),
        },
        "resource_hdx_id": row.get("resource_hdx_id"),
        "links": _INFORM_LINKS,
        "note": (
            "INFORM combines 50+ indicators across hazard & exposure, vulnerability, and lack "
            "of coping capacity. Scores run 0 (lowest risk) to 10 (highest)."
        ),
    }
