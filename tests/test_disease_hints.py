from who_sentinel.disease_hints import curated_hints_for_query, merge_indicator_candidates


def test_curated_cholera():
    rows = curated_hints_for_query("cholera outbreak")
    codes = {r["IndicatorCode"] for r in rows}
    assert "CHOLERA_0000000001" in codes


def test_merge_dedupes_and_orders_curated_first():
    curated = [
        {"IndicatorCode": "A", "IndicatorName": "hint", "source": "curated_hint"},
    ]
    search = [{"IndicatorCode": "A", "IndicatorName": "dup"}, {"IndicatorCode": "B", "IndicatorName": "other"}]
    m = merge_indicator_candidates(curated, search, search_limit=10)
    assert m[0]["IndicatorCode"] == "A"
    assert m[0]["source"] == "curated_hint"
    assert len(m) == 2


def test_curated_cholera_includes_optional_caveat():
    rows = curated_hints_for_query("cholera")
    by_code = {r["IndicatorCode"]: r for r in rows}
    assert "caveat" in by_code["CHOLERA_0000000001"]
    assert "verify_with_indicator_name" in by_code["CHOLERA_0000000003"]


def test_curated_groups_matched_count():
    from who_sentinel.disease_hints import curated_groups_matched_count

    assert curated_groups_matched_count("cholera and malaria outbreak") >= 2


def test_tb_word_boundary_matches_only_real_token():
    """The 'tb' keyword must use word boundaries; 'stable' / 'tabular' must not match."""
    rows_stab = curated_hints_for_query("stable disease report")
    assert all(r["IndicatorCode"] != "MDG_0000000020" for r in rows_stab)

    rows_tab = curated_hints_for_query("tabular trends in cases")
    assert all(r["IndicatorCode"] != "MDG_0000000020" for r in rows_tab)

    rows_tb = curated_hints_for_query("TB outbreak among adults")
    codes = {r["IndicatorCode"] for r in rows_tb}
    assert "MDG_0000000020" in codes

    rows_full = curated_hints_for_query("tuberculosis incidence")
    codes_full = {r["IndicatorCode"] for r in rows_full}
    assert "MDG_0000000020" in codes_full
