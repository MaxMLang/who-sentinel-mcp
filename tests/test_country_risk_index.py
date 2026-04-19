"""country_risk_index passes INFORM Risk Index rows from HDX HAPI through unchanged."""

from typing import Any

from who_sentinel.cache import TTLCache
from who_sentinel.clients.gho import GhoClient
from who_sentinel.clients.hdx import HdxHapiClient
from who_sentinel.sentinel import fetch_inform_risk_index


class _FakeHdx:
    def __init__(self, row: dict[str, Any] | None, raises: Exception | None = None) -> None:
        self._row = row
        self._raises = raises
        self.calls: list[str] = []

    def get_inform_national_risk(self, iso3: str) -> dict[str, Any] | None:
        self.calls.append(iso3)
        if self._raises is not None:
            raise self._raises
        return self._row


def _gho() -> GhoClient:
    return GhoClient(cache=TTLCache(default_ttl_sec=60.0))


def test_inform_ok_payload(monkeypatch):
    g = _gho()
    monkeypatch.setattr(
        "who_sentinel.sentinel.resolve_country",
        lambda gh, c: {"ok": True, "iso3": "UGA", "name": "Uganda"},
    )
    hdx = _FakeHdx(
        {
            "overall_risk": 5.4,
            "hazard_exposure_risk": 6.1,
            "vulnerability_risk": 5.0,
            "coping_capacity_risk": 5.2,
            "risk_class": "High",
            "global_rank": 41,
            "meta_missing_indicators_pct": 3.7,
            "meta_avg_recentness_years": 1.2,
            "reference_period_start": "2025-01-01",
            "reference_period_end": "2025-12-31",
            "resource_hdx_id": "abc-123",
        }
    )

    out = fetch_inform_risk_index(g, hdx, "Uganda")
    assert out["status"] == "ok"
    assert out["country"]["iso3"] == "UGA"
    assert out["scores"]["overall_risk_0_10"] == 5.4
    assert out["scores"]["risk_class"] == "High"
    assert out["scores"]["global_rank"] == 41
    assert out["data_quality"]["missing_indicators_pct"] == 3.7
    assert out["reference_period"]["start"] == "2025-01-01"
    assert out["resource_hdx_id"] == "abc-123"
    assert hdx.calls == ["UGA"]
    g.close()


def test_inform_no_data(monkeypatch):
    g = _gho()
    monkeypatch.setattr(
        "who_sentinel.sentinel.resolve_country",
        lambda gh, c: {"ok": True, "iso3": "TUV", "name": "Tuvalu"},
    )
    out = fetch_inform_risk_index(g, _FakeHdx(None), "Tuvalu")
    assert out["status"] == "no_data"
    assert out["country"]["iso3"] == "TUV"
    g.close()


def test_inform_needs_config_when_app_id_missing(monkeypatch):
    g = _gho()
    monkeypatch.setattr(
        "who_sentinel.sentinel.resolve_country",
        lambda gh, c: {"ok": True, "iso3": "UGA", "name": "Uganda"},
    )
    hdx = _FakeHdx(None, raises=RuntimeError("WHO_SENTINEL_HDX_APP_ID is not set."))
    out = fetch_inform_risk_index(g, hdx, "Uganda")
    assert out["status"] == "needs_config"
    assert "WHO_SENTINEL_HDX_APP_ID" in out["error"]
    g.close()


def test_hdx_client_requires_app_id(monkeypatch):
    monkeypatch.delenv("WHO_SENTINEL_HDX_APP_ID", raising=False)
    c = HdxHapiClient()
    try:
        import pytest

        with pytest.raises(RuntimeError):
            c.get_inform_national_risk("UGA")
    finally:
        c.close()
