from who_sentinel.cache import TTLCache
from who_sentinel.clients.don import DonClient
from who_sentinel.clients.gho import GhoClient
from who_sentinel.sentinel import run_compare_gho_countries, run_surveillance_synthesis


def _series(code: str, iso: str, years: list[tuple[int, float]]):
    return [
        {
            "year": y,
            "numeric_value": v,
            "value": str(v),
            "spatial_dim": iso,
            "indicator_code": code,
            "gho_last_updated": "2025-01-01",
            "period_begin": None,
            "period_end": None,
        }
        for y, v in years
    ]


def test_compare_two_countries(monkeypatch):
    g = GhoClient(cache=TTLCache(60.0))
    d = DonClient()

    def fake_resolve(gh, c):
        if "A" in c:
            return {"ok": True, "iso3": "AAA", "name": "Aland"}
        return {"ok": True, "iso3": "BBB", "name": "Boland"}

    def fake_series(self, code, iso, max_points=30):
        if iso == "AAA":
            return _series(code, iso, [(2022, 10.0), (2021, 9.0)])
        return _series(code, iso, [(2022, 20.0), (2021, 8.0)])

    monkeypatch.setattr("who_sentinel.sentinel.resolve_country", fake_resolve)
    monkeypatch.setattr(GhoClient, "fetch_country_year_series", fake_series)

    def fake_meta(self, code):
        return {"IndicatorCode": code, "IndicatorName": "X"}

    monkeypatch.setattr(GhoClient, "get_indicator_meta", fake_meta)

    out = run_compare_gho_countries(g, "WHS4_100", "Aland", "Boland")
    assert out["status"] == "ok"
    assert out["delta_a_minus_b"] == -10.0
    assert out["ratio_a_over_b"] == 0.5
    g.close()
    d.close()


def test_surveillance_custom_prior_years(monkeypatch):
    g = GhoClient(cache=TTLCache(60.0))
    d = DonClient()

    monkeypatch.setattr(
        "who_sentinel.sentinel.resolve_country",
        lambda gh, c: {"ok": True, "iso3": "UGA", "name": "Uganda"},
    )

    def fake_series(self, code, iso, max_points=30):
        return _series(
            code, iso, [(2024, 100.0), (2023, 90.0), (2022, 80.0), (2021, 70.0)]
        )

    monkeypatch.setattr(GhoClient, "fetch_country_year_series", fake_series)
    monkeypatch.setattr(
        GhoClient,
        "get_indicator_meta",
        lambda self, code: {"IndicatorCode": code, "IndicatorName": "X"},
    )
    monkeypatch.setattr(d, "list_recent", lambda limit=25: [])

    out = run_surveillance_synthesis(
        g, d, "x", "Uganda", "WHS4_100", prior_years_for_baseline=2, baseline_latest_year=None
    )
    assert out["status"] == "ok"
    assert out["baseline"]["prior_year_count"] == 2
    g.close()
    d.close()
