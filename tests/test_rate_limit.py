import importlib

import pytest


def test_rate_limit_exhaustion(monkeypatch):
    monkeypatch.setenv("WHO_SENTINEL_MAX_HTTP_PER_MINUTE", "1")
    import who_sentinel.rate_limit as rl

    importlib.reload(rl)
    rl.acquire_http_slot()
    with pytest.raises(rl.HttpRateLimitExceeded):
        rl.acquire_http_slot()


def test_rate_limit_zero_means_unlimited(monkeypatch):
    monkeypatch.setenv("WHO_SENTINEL_MAX_HTTP_PER_MINUTE", "0")
    import who_sentinel.rate_limit as rl

    importlib.reload(rl)
    for _ in range(5):
        rl.acquire_http_slot()
