"""Validation behavior for DonClient.get_by_id (no live HTTP)."""

import pytest

from who_sentinel.clients.don import DonClient, _validate_don_id


def test_validate_don_id_accepts_uuid():
    s = "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
    assert _validate_don_id(s) == s


def test_validate_don_id_accepts_uppercase_uuid():
    s = "9B1DEB4D-3B7D-4BAD-9BDD-2B0D7B3DCB6D"
    out = _validate_don_id(s)
    assert out.lower() == s.lower()


def test_validate_don_id_rejects_empty():
    with pytest.raises(ValueError):
        _validate_don_id("")
    with pytest.raises(ValueError):
        _validate_don_id("   ")


def test_validate_don_id_rejects_injection_attempts():
    bad_inputs = [
        "1 or 1 eq 1",
        "abc'; DROP TABLE x; --",
        "<script>",
        "../etc/passwd",
        "abc def",
    ]
    for bad in bad_inputs:
        with pytest.raises(ValueError):
            _validate_don_id(bad)


def test_get_by_id_validates_before_http():
    """Bad input must raise ValueError without ever making an HTTP request."""
    d = DonClient()
    try:
        with pytest.raises(ValueError):
            d.get_by_id("not-a-guid; or 1 eq 1")
    finally:
        d.close()
