from who_sentinel.cache import TTLCache
from who_sentinel.clients.gho import GhoClient
from who_sentinel.countries import filter_countries, resolve_country


def _sample_registry():
    return [
        {
            "RegionCode": "EMR",
            "RegionName": "Eastern Mediterranean",
            "CountryCode": "YEM",
            "CountryName": "Yemen",
            "Language": "EN",
        },
        {
            "RegionCode": "AFR",
            "RegionName": "Africa",
            "CountryCode": "UGA",
            "CountryName": "Uganda",
            "Language": "EN",
        },
        {
            "RegionCode": "AMR",
            "RegionName": "Americas",
            "CountryCode": "USA",
            "CountryName": "United States of America",
            "Language": "EN",
        },
    ]


def test_resolve_iso3(monkeypatch):
    g = GhoClient(cache=TTLCache(default_ttl_sec=60.0))
    monkeypatch.setattr(g, "get_region_countries_full", lambda: _sample_registry())
    r = resolve_country(g, "yem")
    assert r["ok"] is True
    assert r["iso3"] == "YEM"
    assert r["region_code"] == "EMR"
    g.close()


def test_resolve_alias_usa(monkeypatch):
    g = GhoClient(cache=TTLCache(default_ttl_sec=60.0))
    monkeypatch.setattr(g, "get_region_countries_full", lambda: _sample_registry())
    r = resolve_country(g, "USA")
    assert r["ok"] is True
    assert r["iso3"] == "USA"
    g.close()


def test_filter_countries():
    reg = _sample_registry()
    assert len(filter_countries(reg, None, 10)) == 3
    assert len(filter_countries(reg, "Yemen", 10)) == 1
