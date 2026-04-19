from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import httpx

from who_sentinel.cache import MISS, TTLCache, country_registry_ttl_sec
from who_sentinel.constants import DEFAULT_CACHE_TTL_SEC, gho_base_url
from who_sentinel.http_retry import request_get_with_retry

_INDICATOR_CODE_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _validate_indicator_code(code: str) -> str:
    code = code.strip()
    if not _INDICATOR_CODE_RE.match(code):
        raise ValueError("Invalid indicator code format.")
    return code


class GhoClient:
    """WHO GHO OData client (per-indicator entity sets)."""

    def __init__(
        self,
        base_url: str | None = None,
        cache: TTLCache | None = None,
        timeout_sec: float = 45.0,
    ) -> None:
        self.base_url = (base_url or gho_base_url()).rstrip("/")
        self.cache = cache or TTLCache(default_ttl_sec=DEFAULT_CACHE_TTL_SEC)
        self._client = httpx.Client(timeout=timeout_sec, headers={"Accept": "application/json"})

    def close(self) -> None:
        self._client.close()

    @property
    def client(self) -> httpx.Client:
        return self._client

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        r = request_get_with_retry(
            self._client,
            url,
            params=params,
            headers={"Accept": "application/json"},
        )
        return r.json()

    def search_indicators(self, query: str, top: int = 40) -> list[dict[str, str]]:
        q = query.strip()
        if len(q) < 2:
            return []
        inner = q.replace("'", "''")
        flt = f"contains(IndicatorName,'{inner}')"
        cache_key = f"gho:indsearch:{flt}:{top}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        data = self._get_json(
            "Indicator",
            {"$filter": flt, "$top": str(top), "$orderby": "IndicatorName"},
        )
        rows = data.get("value") or []
        out = [
            {"IndicatorCode": r.get("IndicatorCode", ""), "IndicatorName": r.get("IndicatorName", "")}
            for r in rows
            if r.get("IndicatorCode")
        ]
        self.cache.set(cache_key, out)
        return out

    def get_indicator_meta(self, indicator_code: str) -> dict[str, str] | None:
        code = _validate_indicator_code(indicator_code)
        cache_key = f"gho:indmeta:{code}"
        cached = self.cache.get(cache_key, default=MISS)
        if cached is not MISS:
            return cached  # type: ignore[no-any-return]

        safe = code.replace("'", "''")
        data = self._get_json("Indicator", {"$filter": f"IndicatorCode eq '{safe}'", "$top": "1"})
        rows = data.get("value") or []
        if not rows:
            self.cache.set(cache_key, None, ttl_sec=3600.0)
            return None
        r = rows[0]
        meta = {
            "IndicatorCode": r.get("IndicatorCode", code),
            "IndicatorName": r.get("IndicatorName", ""),
        }
        self.cache.set(cache_key, meta)
        return meta

    def fetch_country_year_series(
        self,
        indicator_code: str,
        iso3: str,
        max_points: int = 30,
    ) -> list[dict[str, Any]]:
        """Return yearly rows for a country (ISO3), newest first."""
        code = _validate_indicator_code(indicator_code)
        iso = iso3.strip().upper()
        if len(iso) != 3:
            raise ValueError("Country must be a 3-letter ISO3 code.")

        cache_key = f"gho:series:v4:{code}:{iso}:{max_points}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        flt = f"SpatialDim eq '{iso}' and TimeDimType eq 'YEAR'"
        data = self._get_json(
            code,
            {
                "$filter": flt,
                "$orderby": "TimeDim desc",
                "$top": str(max_points),
            },
        )
        rows = data.get("value") or []
        out: list[dict[str, Any]] = []
        for r in rows:
            low = r.get("Low")
            high = r.get("High")
            pt: dict[str, Any] = {
                "year": r.get("TimeDim"),
                "numeric_value": r.get("NumericValue"),
                "value": r.get("Value"),
                "spatial_dim": r.get("SpatialDim"),
                "indicator_code": r.get("IndicatorCode"),
                "gho_last_updated": r.get("Date"),
                "period_begin": r.get("TimeDimensionBegin"),
                "period_end": r.get("TimeDimensionEnd"),
            }
            if low is not None:
                try:
                    pt["value_low"] = float(low)
                except (TypeError, ValueError):
                    pt["value_low"] = low
            if high is not None:
                try:
                    pt["value_high"] = float(high)
                except (TypeError, ValueError):
                    pt["value_high"] = high
            out.append(pt)
        self.cache.set(cache_key, out)
        return out

    def numeric_bounds_for_country_year(
        self,
        indicator_code: str,
        year: int,
    ) -> tuple[float | None, float | None]:
        """Approximate global min/max for COUNTRY rows for a given year (two OData queries)."""
        code = _validate_indicator_code(indicator_code)
        cache_key = f"gho:bounds:{code}:{year}"
        cached = self.cache.get(cache_key, default=MISS)
        if cached is not MISS:
            return cached  # type: ignore[no-any-return]

        flt = f"TimeDim eq {int(year)} and SpatialDimType eq 'COUNTRY'"
        lo = self._get_json(code, {"$filter": flt, "$orderby": "NumericValue asc", "$top": "1"})
        hi = self._get_json(code, {"$filter": flt, "$orderby": "NumericValue desc", "$top": "1"})
        lv = (lo.get("value") or [{}])[0].get("NumericValue")
        hv = (hi.get("value") or [{}])[0].get("NumericValue")
        pair = (float(lv) if lv is not None else None, float(hv) if hv is not None else None)
        self.cache.set(cache_key, pair)
        return pair

    def latest_year_with_country_data(self, indicator_code: str) -> int | None:
        """Most recent year with any COUNTRY-scoped row for this indicator (or None)."""
        code = _validate_indicator_code(indicator_code)
        cache_key = f"gho:latest_country_year:{code}"
        cached = self.cache.get(cache_key, default=MISS)
        if cached is not MISS:
            return cached  # type: ignore[no-any-return]

        data = self._get_json(
            code,
            {
                "$filter": "SpatialDimType eq 'COUNTRY' and TimeDimType eq 'YEAR'",
                "$orderby": "TimeDim desc",
                "$top": "1",
            },
        )
        rows = data.get("value") or []
        year: int | None = None
        if rows:
            raw = rows[0].get("TimeDim")
            try:
                year = int(raw) if raw is not None else None
            except (TypeError, ValueError):
                year = None
        self.cache.set(cache_key, year, ttl_sec=86400.0)
        return year

    def latest_value_for_country(
        self,
        indicator_code: str,
        iso3: str,
    ) -> dict[str, Any] | None:
        series = self.fetch_country_year_series(indicator_code, iso3, max_points=5)
        for row in series:
            if row.get("numeric_value") is not None:
                return row
            if row.get("value") is not None:
                return row
        return None

    def fetch_odata_pages(
        self,
        path: str,
        page_size: int = 1000,
        extra_params: dict[str, str] | None = None,
        max_pages: int = 100,
    ) -> list[dict[str, Any]]:
        """Follow @odata.nextLink until exhausted (GHO caps $top at 1000)."""
        out: list[dict[str, Any]] = []
        url = f"{self.base_url}/{path.lstrip('/')}"
        params: dict[str, Any] | None = dict(extra_params or {})
        params["$top"] = str(page_size)
        pages = 0
        while url and pages < max_pages:
            r = request_get_with_retry(
                self._client,
                url,
                params=params,
                headers={"Accept": "application/json"},
            )
            data = r.json()
            out.extend(data.get("value") or [])
            nxt = data.get("@odata.nextLink")
            url = urljoin(f"{self.base_url}/", nxt.strip()) if isinstance(nxt, str) and nxt.strip() else ""
            params = None
            pages += 1
        return out

    def get_region_countries_full(self) -> list[dict[str, Any]]:
        """All rows from RegionCountry (WHO country/region reference)."""
        cache_key = "gho:RegionCountry:full:v1"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        rows = self.fetch_odata_pages(
            "RegionCountry",
            page_size=1000,
            extra_params={"$orderby": "CountryName"},
        )
        ttl = country_registry_ttl_sec()
        self.cache.set(cache_key, rows, ttl_sec=ttl)
        return rows

    def list_indicator_dimensions(
        self,
        indicator_code: str,
        language: str = "EN",
        top: int = 50,
    ) -> list[dict[str, str]]:
        """Dimensions available for an indicator (e.g. COUNTRY, YEAR) from IndicatorDimension."""
        code = _validate_indicator_code(indicator_code)
        safe = code.replace("'", "''")
        lang = language.replace("'", "''")
        flt = f"IndicatorCode eq '{safe}' and Language eq '{lang}'"
        cache_key = f"gho:inddim:{code}:{language}:{top}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        lim = max(1, min(int(top), 100))
        data = self._get_json(
            "IndicatorDimension",
            {"$filter": flt, "$top": str(lim), "$orderby": "Dimension"},
        )
        rows = data.get("value") or []
        out = [
            {
                "Dimension": str(r.get("Dimension") or ""),
                "DimensionName": str(r.get("DimensionName") or ""),
                "IndicatorCode": str(r.get("IndicatorCode") or code),
            }
            for r in rows
        ]
        self.cache.set(cache_key, out)
        return out

    def get_api_entity_catalog(self) -> list[dict[str, Any]]:
        """Entity sets from GET /api (thousands of per-indicator collections + metadata tables)."""
        cache_key = "gho:api_root_catalog:v1"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        r = request_get_with_retry(
            self._client,
            self.base_url,
            headers={"Accept": "application/json"},
        )
        data = r.json()
        catalog = list(data.get("value") or [])
        ttl = country_registry_ttl_sec()
        self.cache.set(cache_key, catalog, ttl_sec=ttl)
        return catalog
