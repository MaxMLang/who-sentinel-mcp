import httpx

from who_sentinel.http_retry import request_get_with_retry


def test_retry_on_503_then_success():
    n = {"c": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["c"] += 1
        if n["c"] < 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    r = request_get_with_retry(client, "https://example.invalid/x")
    assert r.json() == {"ok": True}
    assert n["c"] == 2
    client.close()
