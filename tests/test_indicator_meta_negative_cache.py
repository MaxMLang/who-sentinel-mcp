"""Regression test for negative caching of unknown indicator codes."""

import re

import pytest

from who_sentinel.cache import TTLCache
from who_sentinel.clients.gho import GhoClient


@pytest.mark.integration
def test_get_indicator_meta_negative_cache_prevents_refetch(httpx_mock):
    """A second call for an unknown indicator must hit the cache (no extra HTTP)."""
    httpx_mock.add_response(
        url=re.compile(r"https://ghoapi\.azureedge\.net/api/Indicator.*"),
        json={"@odata.context": "x", "value": []},
    )

    g = GhoClient(cache=TTLCache(default_ttl_sec=3600.0))
    try:
        assert g.get_indicator_meta("NO_SUCH_CODE") is None
        assert g.get_indicator_meta("NO_SUCH_CODE") is None
        assert len(httpx_mock.get_requests()) == 1
    finally:
        g.close()
