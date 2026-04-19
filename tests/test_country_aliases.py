"""pycountry-backed alias resolution and DON narrative text-hint expansion."""

from who_sentinel.country_aliases import country_text_hints, iso3_for_alias


def test_iso3_canonical_name():
    assert iso3_for_alias("Uganda") == "UGA"
    assert iso3_for_alias("United States of America") == "USA"


def test_iso3_alpha2_and_alpha3():
    assert iso3_for_alias("UG") == "UGA"
    assert iso3_for_alias("UGA") == "UGA"


def test_iso3_overlay_for_short_forms():
    assert iso3_for_alias("DRC") == "COD"
    assert iso3_for_alias("dr congo") == "COD"
    assert iso3_for_alias("the gambia") == "GMB"
    assert iso3_for_alias("Burma") == "MMR"


def test_iso3_handles_diacritics_and_apostrophe():
    assert iso3_for_alias("Côte d'Ivoire") == "CIV"
    assert iso3_for_alias("Cote dIvoire") == "CIV"


def test_iso3_returns_none_for_garbage():
    assert iso3_for_alias("") is None
    assert iso3_for_alias("   ") is None
    assert iso3_for_alias("not a real country zzzz") is None


def test_text_hints_include_overlay_and_iso3():
    hints = country_text_hints("COD", "Democratic Republic of the Congo")
    assert "DRC" in hints
    assert "COD" in hints
    assert "Democratic Republic of the Congo" in hints


def test_text_hints_for_unknown_iso3_still_returns_iso3():
    hints = country_text_hints("ZZZ", "Atlantis")
    assert hints[0] == "Atlantis"
    assert "ZZZ" in hints
