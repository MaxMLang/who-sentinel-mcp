from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, TypeVar

from who_sentinel.constants import GHO_REGISTRY_TTL_SEC

T = TypeVar("T")


class _Miss:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover
        return "<cache.MISS>"


MISS: Any = _Miss()
"""Sentinel returned by ``TTLCache.get`` when a key is absent (lets callers
distinguish a real miss from a cached ``None``)."""


def effective_cache_ttl_sec() -> float:
    """Resolved WHO_SENTINEL_CACHE_TTL (GHO series / indicator cache)."""
    return _ttl_from_env()


def _ttl_from_env() -> float:
    raw = os.environ.get("WHO_SENTINEL_CACHE_TTL")
    if raw is None:
        return 86400.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 86400.0


def country_registry_ttl_sec() -> float:
    raw = os.environ.get("WHO_SENTINEL_COUNTRY_REGISTRY_TTL")
    if raw is None:
        return float(GHO_REGISTRY_TTL_SEC)
    try:
        return max(60.0, float(raw))
    except ValueError:
        return float(GHO_REGISTRY_TTL_SEC)


class TTLCache:
    """Simple in-process TTL cache (single MCP server process)."""

    def __init__(self, default_ttl_sec: float | None = None) -> None:
        self._default_ttl = float(default_ttl_sec if default_ttl_sec is not None else _ttl_from_env())
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, default: Any = None) -> Any:
        """Return the cached value, or ``default`` if absent/expired. Pass ``default=MISS``
        to tell a cached ``None`` apart from a real miss."""
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return default
            exp, val = entry
            if exp <= now:
                del self._data[key]
                return default
            return val

    def set(self, key: str, value: Any, ttl_sec: float | None = None) -> None:
        ttl = float(ttl_sec if ttl_sec is not None else self._default_ttl)
        exp = time.monotonic() + ttl
        with self._lock:
            self._data[key] = (exp, value)

    def get_or_set(self, key: str, factory: Callable[[], T], ttl_sec: float | None = None) -> T:
        cached = self.get(key, default=MISS)
        if cached is not MISS:
            return cached  # type: ignore[no-any-return]
        val = factory()
        self.set(key, val, ttl_sec=ttl_sec)
        return val
