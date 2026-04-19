"""needs_indicator ambiguity guidance (merged list size / multiple curated groups)."""

from who_sentinel.cache import TTLCache
from who_sentinel.clients.don import DonClient
from who_sentinel.clients.gho import GhoClient
from who_sentinel.sentinel import run_surveillance_synthesis


def test_needs_indicator_adds_guidance_when_many_candidates(monkeypatch):
    g = GhoClient(cache=TTLCache(60.0))
    d = DonClient()
    monkeypatch.setattr(
        "who_sentinel.sentinel.resolve_country",
        lambda gh, c: {"ok": True, "iso3": "UGA", "name": "Uganda"},
    )
    monkeypatch.setattr("who_sentinel.sentinel.curated_hints_for_query", lambda q: [])
    monkeypatch.setattr(
        GhoClient,
        "search_indicators",
        lambda self, q, top=15: [{"IndicatorCode": f"C{i}", "IndicatorName": f"N{i}"} for i in range(15)],
    )
    out = run_surveillance_synthesis(g, d, "query", "Uganda", None)
    assert out["status"] == "needs_indicator"
    assert "indicator_selection_guidance" in out
    g.close()
    d.close()


def test_needs_indicator_omits_guidance_when_few_candidates(monkeypatch):
    g = GhoClient(cache=TTLCache(60.0))
    d = DonClient()
    monkeypatch.setattr(
        "who_sentinel.sentinel.resolve_country",
        lambda gh, c: {"ok": True, "iso3": "UGA", "name": "Uganda"},
    )
    monkeypatch.setattr("who_sentinel.sentinel.curated_hints_for_query", lambda q: [])
    monkeypatch.setattr(
        GhoClient,
        "search_indicators",
        lambda self, q, top=15: [{"IndicatorCode": f"C{i}", "IndicatorName": "x"} for i in range(5)],
    )
    out = run_surveillance_synthesis(g, d, "query", "Uganda", None)
    assert out["status"] == "needs_indicator"
    assert "indicator_selection_guidance" not in out
    g.close()
    d.close()
