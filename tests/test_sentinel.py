from who_sentinel.sentinel import _scale_to_score


def test_scale_to_score_higher_better():
    assert _scale_to_score(50.0, 0.0, 100.0, higher_is_better=True) == 50.0
    assert _scale_to_score(0.0, 0.0, 100.0, higher_is_better=True) == 0.0


def test_scale_to_score_lower_better_inverts():
    # high diarrhoea attributable fraction is bad -> lower score
    s = _scale_to_score(80.0, 0.0, 100.0, higher_is_better=False)
    assert s == 20.0
