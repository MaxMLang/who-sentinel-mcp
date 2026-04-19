from who_sentinel.cache import MISS, TTLCache


def test_ttl_cache_expires(monkeypatch):
    clock = [0.0]

    def monotonic() -> float:
        return clock[0]

    monkeypatch.setattr("who_sentinel.cache.time.monotonic", monotonic)

    c = TTLCache(default_ttl_sec=1.0)
    calls = {"n": 0}

    def factory() -> int:
        calls["n"] += 1
        return 42

    assert c.get_or_set("k", factory) == 42
    assert c.get_or_set("k", factory) == 42
    assert calls["n"] == 1

    clock[0] = 2.0  # past expiry (exp was 0 + 1)
    assert c.get("k") is None
    assert c.get_or_set("k", factory) == 42
    assert calls["n"] == 2


def test_cache_distinguishes_miss_from_cached_none():
    """MISS sentinel lets callers tell 'no entry' apart from a cached None."""
    c = TTLCache(default_ttl_sec=60.0)
    assert c.get("missing") is None
    assert c.get("missing", default=MISS) is MISS

    c.set("present", None)
    assert c.get("present") is None
    assert c.get("present", default=MISS) is None  # cached None, not MISS


def test_get_or_set_caches_none_via_factory():
    c = TTLCache(default_ttl_sec=60.0)
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return None

    assert c.get_or_set("k", factory) is None
    assert c.get_or_set("k", factory) is None
    assert calls["n"] == 1  # second call hits cached None, doesn't re-run factory
