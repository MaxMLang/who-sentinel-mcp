import json

from who_sentinel.constants import RESPONSE_DISCLAIMER_SHORT
from who_sentinel.server import _json_out


def test_json_out_includes_who_sentinel_meta_disclaimer():
    raw = _json_out({"x": 1})
    _, body = raw.split("\n\n", 1)
    payload = json.loads(body)
    assert payload["who_sentinel_meta"]["disclaimer"] == RESPONSE_DISCLAIMER_SHORT
    assert "CC BY 4.0" in payload["who_sentinel_meta"]["data_licensing"]
