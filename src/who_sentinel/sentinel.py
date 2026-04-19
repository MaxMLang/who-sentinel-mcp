from __future__ import annotations

import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from who_sentinel.clients.don import DonClient, filter_outbreak_rows, outbreak_summary_row
from who_sentinel.clients.gho import GhoClient
from who_sentinel.countries import resolve_country
from who_sentinel.disease_hints import (
    curated_groups_matched_count,
    curated_hints_for_query,
    merge_indicator_candidates,
)


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
    series = gho.fetch_country_year_series(code, iso3, max_points=30)
    numeric_rows = [r for r in series if r.get("numeric_value") is not None]
    if len(numeric_rows) < 2:
        return {
            "status": "insufficient_gho",
            "country_resolution": cc,
            "indicator": meta,
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

    # DON: pull a wider net then filter (country name + ISO3; ISO3 uses word-boundary match)
    recent = don.list_recent(limit=40)
    country_name = str(cc.get("name") or "")
    country_hints = [h for h in (country_name, iso3) if h]
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


# --- Vulnerability index (heuristic; not an official WHO index) ---

_VULN_INDICATORS: list[dict[str, Any]] = [
    {
        "id": "immunization_dtp3",
        "label": "DTP3 immunization coverage among 1-year-olds (%)",
        "code": "WHS4_100",
        "higher_is_better": True,
        "invert": False,
    },
    {
        "id": "immunization_pol3",
        "label": "Polio (Pol3) immunization coverage among 1-year-olds (%)",
        "code": "WHS4_544",
        "higher_is_better": True,
        "invert": False,
    },
    {
        "id": "hospital_beds_per_10k",
        "label": "Hospital beds (per 10 000 population)",
        "code": "WHS6_102",
        "higher_is_better": True,
        "invert": False,
    },
    {
        "id": "diarrhoea_attributable_to_water",
        "label": "Attributable fraction of diarrhoea to inadequate water",
        "code": "WSH_20_WAT",
        "higher_is_better": False,
        "invert": False,
    },
]


def _scale_to_score(
    value: float,
    lo: float | None,
    hi: float | None,
    *,
    higher_is_better: bool,
) -> float | None:
    if lo is None or hi is None or hi == lo:
        return None
    t = (value - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    if not higher_is_better:
        t = 1.0 - t
    return round(100.0 * t, 2)


def _vuln_one_component(
    gho: GhoClient,
    iso3: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    code = spec["code"]
    latest = gho.latest_value_for_country(code, iso3)
    if not latest or latest.get("numeric_value") is None:
        return {
            "id": spec["id"],
            "label": spec["label"],
            "code": code,
            "missing": True,
        }
    val = float(latest["numeric_value"])  # type: ignore[arg-type]
    cy = latest.get("year")
    if cy is not None:
        year_for_bounds = int(cy)
    else:
        dyn = gho.latest_year_with_country_data(code)
        if dyn is None:
            return {
                "id": spec["id"],
                "label": spec["label"],
                "code": code,
                "missing": True,
                "missing_reason": "no_country_year_anchor",
            }
        year_for_bounds = dyn
    lo, hi = gho.numeric_bounds_for_country_year(code, year_for_bounds)
    scr = _scale_to_score(val, lo, hi, higher_is_better=bool(spec["higher_is_better"]))
    return {
        "id": spec["id"],
        "label": spec["label"],
        "code": code,
        "year_used_for_global_bounds": year_for_bounds,
        "global_min": lo,
        "global_max": hi,
        "country_latest_year": latest.get("year"),
        "country_value": val,
        "component_score_0_100": scr,
        "missing": False,
    }


_VULN_MIN_COMPONENTS_FOR_OVERALL = 2


def compute_spatial_vulnerability_index(gho: GhoClient, country: str) -> dict[str, Any]:
    """Heuristic 0-100 score (higher = more resilient / lower vulnerability for most components)."""

    cc = resolve_country(gho, country)
    if not cc.get("ok"):
        return {"status": "needs_country", "country_resolution": cc}

    iso3 = str(cc.get("iso3"))
    name = str(cc.get("name"))

    components: list[dict[str, Any]] = []
    scores: list[float] = []

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {
            ex.submit(_vuln_one_component, gho, iso3, spec): spec["id"]
            for spec in _VULN_INDICATORS
        }
        for fut in as_completed(futs):
            entry = fut.result()
            components.append(entry)
            if entry.get("component_score_0_100") is not None:
                scores.append(float(entry["component_score_0_100"]))

    components.sort(key=lambda x: x.get("id") or "")

    overall: float | None
    if len(scores) >= _VULN_MIN_COMPONENTS_FOR_OVERALL:
        overall = round(sum(scores) / len(scores), 2)
    else:
        overall = None

    return {
        "status": "ok",
        "disclaimer": "Heuristic composite score based on selected GHO indicators; not an official WHO index.",
        "country": {"iso3": iso3, "name": name},
        "overall_resilience_score_0_100": overall,
        "components_used_for_overall": len(scores),
        "components_total": len(components),
        "min_components_required_for_overall": _VULN_MIN_COMPONENTS_FOR_OVERALL,
        "components": components,
        "note": "Components fetched in parallel; outbound HTTP is rate-limited globally.",
    }
