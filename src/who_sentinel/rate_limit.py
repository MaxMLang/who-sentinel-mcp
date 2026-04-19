"""Token-bucket limiter for outbound HTTP (WHO public APIs)."""

from __future__ import annotations

import os
import threading
import time


class HttpRateLimitExceeded(RuntimeError):
    """Raised when the per-minute HTTP budget is exhausted."""


def _max_per_minute() -> float:
    raw = os.environ.get("WHO_SENTINEL_MAX_HTTP_PER_MINUTE", "120")
    try:
        v = float(raw)
        return max(0.0, v)
    except ValueError:
        return 120.0


def http_budget_per_minute() -> float:
    """Effective outbound GET budget per minute (0 = unlimited)."""
    return _max_per_minute()


class _Bucket:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: float | None = None
        self._last = time.monotonic()

    def acquire(self) -> None:
        cap = _max_per_minute()
        if cap <= 0:
            return
        refill_per_sec = cap / 60.0
        now = time.monotonic()
        with self._lock:
            if self._tokens is None:
                self._tokens = cap
            elapsed = now - self._last
            self._last = now
            self._tokens = min(cap, float(self._tokens) + elapsed * refill_per_sec)
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
        raise HttpRateLimitExceeded(
            f"WHO-Sentinel outbound HTTP budget exceeded (~{int(cap)} GETs/minute). "
            "Wait briefly or raise WHO_SENTINEL_MAX_HTTP_PER_MINUTE if appropriate."
        )


_bucket = _Bucket()


def acquire_http_slot() -> None:
    """Consume one token for a logical outbound HTTP request (retries reuse the same slot)."""
    _bucket.acquire()
