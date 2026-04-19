from who_sentinel.extract import extract_outbreak_metadata


def test_explicit_cfr_percent():
    text = "The case fatality ratio (CFR) was 2.5% among confirmed cases."
    r = extract_outbreak_metadata(text)
    assert r.cfr == 2.5
    assert r.cfr_from_explicit_text is True
