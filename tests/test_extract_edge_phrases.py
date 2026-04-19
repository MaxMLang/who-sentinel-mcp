"""Sanitized synthetic DON-like strings for extract_outbreak_metadata edge behavior."""

from who_sentinel.extract import extract_outbreak_metadata


def test_confidence_low_when_no_numbers():
    r = extract_outbreak_metadata("No epidemiologic numbers in this stub narrative.")
    assert r.cases is None and r.deaths is None
    assert r.confidence == "low"


def test_cfr_explicit_sets_medium_and_explicit_source():
    text = "The case fatality ratio (CFR) was 3.2% among confirmed cases in this setting."
    r = extract_outbreak_metadata(text)
    assert r.cfr == 3.2
    assert r.cfr_from_explicit_text is True
    assert r.confidence == "medium"


def test_derived_cfr_sets_derived_or_none_in_dict():
    from who_sentinel.extract import extract_result_to_dict

    text = (
        "A total of 100 laboratory-confirmed cases have been reported, including 25 deaths."
    )
    r = extract_outbreak_metadata(text)
    d = extract_result_to_dict(r)
    assert r.cases == 100 and r.deaths == 25
    assert d["cfr_source"] == "derived_or_none"
    assert d["confidence"] == "medium"
