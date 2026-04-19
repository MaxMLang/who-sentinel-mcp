"""Integration-style tests using mocked HTTP (no live WHO calls)."""

import re

import pytest

from who_sentinel.cache import TTLCache
from who_sentinel.clients.gho import GhoClient


@pytest.mark.integration
def test_indicator_dimension_request_shape(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r"https://ghoapi\.azureedge\.net/api/IndicatorDimension.*"),
        json={
            "@odata.context": "x",
            "value": [
                {
                    "IndicatorCode": "WHS4_100",
                    "Language": "EN",
                    "Dimension": "COUNTRY",
                    "DimensionName": "Country",
                }
            ],
        },
    )
    g = GhoClient(cache=TTLCache(default_ttl_sec=60.0))
    rows = g.list_indicator_dimensions("WHS4_100", language="EN", top=10)
    assert rows[0]["Dimension"] == "COUNTRY"
    g.close()
