import pytest

from who_sentinel.cache import TTLCache
from who_sentinel.clients.gho import GhoClient


@pytest.fixture
def gho_sample_json():
    return {
        "@odata.context": "x",
        "value": [
            {
                "IndicatorCode": "WHS4_100",
                "IndicatorName": "DTP3 coverage",
                "Language": "EN",
            }
        ],
    }


def test_search_indicators_uses_cache(httpx_mock, gho_sample_json):
    httpx_mock.add_response(json=gho_sample_json)
    cache = TTLCache(default_ttl_sec=3600.0)
    g = GhoClient(cache=cache)

    rows = g.search_indicators("DTP")
    assert rows[0]["IndicatorCode"] == "WHS4_100"

    # Second call should hit cache (no additional HTTP)
    rows2 = g.search_indicators("DTP")
    assert rows2 == rows
    assert len(httpx_mock.get_requests()) == 1

    g.close()
