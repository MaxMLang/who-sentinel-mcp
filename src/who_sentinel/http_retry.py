"""Retry policy for WHO public HTTP APIs (GET only)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from who_sentinel.metrics import record_http_get

RETRYABLE_STATUS = frozenset({408, 429, 502, 503, 504})
_BACKOFF_SEC = (0.5, 1.0, 2.0)
_MAX_ATTEMPTS = 3


def _retry_after_seconds(resp: httpx.Response, default: float) -> float:
    ra = resp.headers.get("Retry-After")
    if not ra:
        return default
    try:
        return max(0.0, float(ra))
    except ValueError:
        return default


def request_get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """GET with exponential backoff. One rate-limit slot per logical call (retries don't recharge)."""
    from who_sentinel.rate_limit import acquire_http_slot

    acquire_http_slot()
    for attempt in range(_MAX_ATTEMPTS):
        record_http_get()
        r = client.get(url, params=params, headers=headers)
        if r.status_code < 400:
            return r
        if r.status_code not in RETRYABLE_STATUS or attempt == _MAX_ATTEMPTS - 1:
            r.raise_for_status()
        backoff = _BACKOFF_SEC[min(attempt, len(_BACKOFF_SEC) - 1)]
        if r.status_code == 429:
            backoff = _retry_after_seconds(r, backoff)
        time.sleep(backoff)
    raise RuntimeError("request_get_with_retry: exhausted retries without response")  # unreachable
