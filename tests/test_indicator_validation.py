"""surveillance_synthesis refuses indicators whose name shares no keywords with the disease query."""

from typing import Any

from who_sentinel.cache import TTLCache
from who_sentinel.clients.don import DonClient
from who_sentinel.clients.gho import GhoClient
from who_sentinel.sentinel import (
    _validate_indicator_for_disease,
    run_surveillance_synthesis,
)


def test_validation_ok_when_disease_keyword_in_indicator_name():
    v = _validate_indicator_for_disease(
        {"IndicatorCode": "X", "IndicatorName": "Number of reported cases of cholera"},
        "cholera outbreak",
    )
    assert v["confidence"] == "ok"
    assert "cholera" in v["matched_disease_tokens"]


def test_validation_warning_when_no_overlap():
    v = _validate_indicator_for_disease(
        {"IndicatorCode": "WHS4_100", "IndicatorName": "DTP3 immunization coverage"},
        "cholera outbreak",
    )
    assert v["confidence"] == "warning"
    assert v["matched_disease_tokens"] == []


def test_validation_unknown_when_query_has_no_real_tokens():
    v = _validate_indicator_for_disease(
        {"IndicatorCode": "X", "IndicatorName": "Anything"},
        "x",
    )
    assert v["confidence"] == "unknown"


def test_synthesis_refuses_low_confidence_pick(monkeypatch):
    g = GhoClient(cache=TTLCache(60.0))
    d = DonClient()
    monkeypatch.setattr(
        "who_sentinel.sentinel.resolve_country",
        lambda gh, c: {"ok": True, "iso3": "UGA", "name": "Uganda"},
    )
    monkeypatch.setattr(
        GhoClient,
        "get_indicator_meta",
        lambda self, code: {"IndicatorCode": code, "IndicatorName": "DTP3 immunization coverage"},
    )
    monkeypatch.setattr("who_sentinel.sentinel.curated_hints_for_query", lambda q: [])
    monkeypatch.setattr(GhoClient, "search_indicators", lambda self, q, top=15: [])

    called: list[Any] = []
    monkeypatch.setattr(
        GhoClient,
        "fetch_country_year_series",
        lambda self, code, iso, max_points=30: called.append(code) or [],
    )

    out = run_surveillance_synthesis(g, d, "cholera", "Uganda", "WHS4_100")
    assert out["status"] == "indicator_validation_warning"
    assert out["code_provenance"] == "user_supplied"
    assert out["code_validation"]["confidence"] == "warning"
    assert called == [], "Should not have fetched a series for a refused indicator."
    g.close()
    d.close()


def test_synthesis_proceeds_when_confirm_indicator_true(monkeypatch):
    g = GhoClient(cache=TTLCache(60.0))
    d = DonClient()
    monkeypatch.setattr(
        "who_sentinel.sentinel.resolve_country",
        lambda gh, c: {"ok": True, "iso3": "UGA", "name": "Uganda"},
    )
    monkeypatch.setattr(
        GhoClient,
        "get_indicator_meta",
        lambda self, code: {"IndicatorCode": code, "IndicatorName": "DTP3 immunization coverage"},
    )
    monkeypatch.setattr(
        GhoClient,
        "fetch_country_year_series",
        lambda self, code, iso, max_points=30: [
            {"year": 2024, "numeric_value": 90.0},
            {"year": 2023, "numeric_value": 85.0},
            {"year": 2022, "numeric_value": 82.0},
        ],
    )
    monkeypatch.setattr(d, "list_recent", lambda limit=25: [])

    out = run_surveillance_synthesis(
        g, d, "cholera", "Uganda", "WHS4_100", confirm_indicator=True
    )
    assert out["status"] == "ok"
    assert out["code_provenance"] == "user_supplied"
    assert out["code_validation"]["confidence"] == "warning"
    g.close()
    d.close()
