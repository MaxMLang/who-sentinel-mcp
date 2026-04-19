from who_sentinel.clients.don import don_public_url, filter_outbreak_rows


def _row(title: str, body: str) -> dict:
    return {"Title": title, "Overview": body, "Summary": ""}


def test_filter_disease_and_country_name():
    rows = [_row("Cholera in Yemen", "Cases reported in Yemen.")]
    out = filter_outbreak_rows(rows, "cholera", country_hints=["Yemen"])
    assert len(out) == 1


def test_filter_iso3_word_boundary():
    rows = [_row("Health update", "Coordination with UGA authorities on outbreak response.")]
    out = filter_outbreak_rows(rows, "outbreak", country_hints=["Uganda", "UGA"])
    assert len(out) == 1


def test_don_public_url_from_item_default():
    u = don_public_url({"ItemDefaultUrl": "/2026-DON597", "UrlName": "2026-DON597"})
    assert u == "https://www.who.int/2026-DON597"


def test_filter_iso3_avoids_substring_false_positive():
    rows = [_row("X", "The programme continued.")]
    out = filter_outbreak_rows(rows, "programme", country_hints=["UGA"])
    assert len(out) == 0
