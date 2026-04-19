"""Coverage for DON phrasings the basic regexes used to miss.

Inputs are sanitized synthetic strings; they only exercise wording shapes seen
in WHO Disease Outbreak News, not real article text.
"""

from who_sentinel.extract import extract_outbreak_metadata


def test_suspected_and_confirmed_cases_phrasing():
    text = "A total of 144 suspected and confirmed cases of food poisoning have been reported."
    r = extract_outbreak_metadata(text)
    assert r.cases == 144


def test_confirmed_and_probable_cases():
    text = "As of the reporting date, 87 confirmed and probable cases were notified."
    r = extract_outbreak_metadata(text)
    assert r.cases == 87


def test_spelled_out_one_human_case():
    text = "WHO was notified of one human case of avian influenza A(H5N1) infection."
    r = extract_outbreak_metadata(text)
    assert r.cases == 1


def test_spelled_out_two_fatalities():
    text = "Two fatalities have been reported among the confirmed cases."
    r = extract_outbreak_metadata(text)
    assert r.deaths == 2


def test_people_have_died_phrasing():
    text = "Since the start of the outbreak, 17 people have died."
    r = extract_outbreak_metadata(text)
    assert r.deaths == 17


def test_with_n_deaths_clause():
    text = "Authorities reported 230 cases with 18 deaths in the affected districts."
    r = extract_outbreak_metadata(text)
    assert r.cases == 230
    assert r.deaths == 18


def test_fatalities_numeric():
    text = "The cluster comprises 9 cases and 3 fatalities so far."
    r = extract_outbreak_metadata(text)
    assert r.cases == 9
    assert r.deaths == 3


def test_no_false_positive_on_age_or_year():
    """Standalone numbers near unrelated nouns must not become cases or deaths."""
    text = (
        "The patient is a 42-year-old male admitted in 2025. "
        "No epidemiologic counts were disclosed."
    )
    r = extract_outbreak_metadata(text)
    assert r.cases is None
    assert r.deaths is None


def test_case_fatality_rate_variant():
    text = "The case fatality rate among hospitalized patients was 12.5%."
    r = extract_outbreak_metadata(text)
    assert r.cfr == 12.5
    assert r.cfr_from_explicit_text is True
