"""Tiny HDX HAPI client; today we only call the INFORM national-risk endpoint."""

from __future__ import annotations

import os
from typing import Any

import httpx

from who_sentinel.constants import hdx_hapi_base_url
from who_sentinel.http_retry import request_get_with_retry

HDX_APP_ID_ENV = "WHO_SENTINEL_HDX_APP_ID"


def hdx_app_identifier() -> str | None:
    val = os.environ.get(HDX_APP_ID_ENV, "").strip()
    return val or None


class HdxHapiClient:
    """Read-only client for https://hapi.humdata.org (HDX Humanitarian API)."""

    def __init__(self, base_url: str | None = None, timeout_sec: float = 30.0) -> None:
        self.base_url = (base_url or hdx_hapi_base_url()).rstrip("/")
        self._client = httpx.Client(timeout=timeout_sec, headers={"Accept": "application/json"})

    def close(self) -> None:
        self._client.close()

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any] | list[dict[str, Any]]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        r = request_get_with_retry(
            self._client,
            url,
            params=params,
            headers={"Accept": "application/json"},
        )
        return r.json()

    def get_inform_national_risk(self, iso3: str) -> dict[str, Any] | None:
        """Latest INFORM Risk Index row for one country, or None if not present."""
        app_id = hdx_app_identifier()
        if not app_id:
            raise RuntimeError(
                f"{HDX_APP_ID_ENV} is not set. Generate one at "
                "https://hapi.humdata.org/docs#/Utility/get_encoded_identifier_api_v1_encode_identifier_get "
                "and export it before calling this tool."
            )

        iso = iso3.strip().upper()
        if len(iso) != 3 or not iso.isalpha():
            raise ValueError("iso3 must be a 3-letter ISO 3166 alpha-3 code.")

        data = self._get_json(
            "api/v1/coordination-context/national-risk",
            {
                "location_code": iso,
                "output_format": "json",
                "limit": "1",
                "offset": "0",
                "app_identifier": app_id,
            },
        )
        rows = data.get("data") if isinstance(data, dict) else data
        if not rows or not isinstance(rows, list):
            return None
        first = rows[0]
        return first if isinstance(first, dict) else None
