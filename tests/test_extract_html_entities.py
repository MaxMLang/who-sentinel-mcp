"""extract_outbreak_metadata should decode HTML entities before regex matching."""

from who_sentinel.extract import extract_outbreak_metadata


def test_html_entities_are_decoded_before_extraction():
    text = (
        "A&nbsp;total of 1,234&nbsp;laboratory-confirmed cases have been reported,"
        " including 56&nbsp;deaths."
    )
    r = extract_outbreak_metadata(text)
    assert r.cases == 1234
    assert r.deaths == 56


def test_numeric_entity_for_percent_in_cfr():
    text = "The CFR was 4.1&#37; in this setting."
    r = extract_outbreak_metadata(text)
    assert r.cfr == 4.1
    assert r.cfr_from_explicit_text is True
