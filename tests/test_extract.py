from who_sentinel.extract import extract_outbreak_metadata


def test_extract_cases_deaths():
    text = (
        "As of 10 April 2026, 51 laboratory-confirmed cases have been reported, "
        "including 11 deaths."
    )
    r = extract_outbreak_metadata(text)
    assert r.cases == 51
    assert r.deaths == 11
    assert r.cfr is not None and abs(r.cfr - (11 / 51 * 100)) < 0.1
