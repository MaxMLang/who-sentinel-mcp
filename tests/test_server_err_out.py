"""_err_out should not leak Python tracebacks unless DEBUG logging is enabled."""

import json
import logging

from who_sentinel.server import _err_out


def _payload(text: str) -> dict:
    _, body = text.split("\n\n", 1)
    return json.loads(body)


def test_err_out_omits_traceback_at_default_log_level():
    log = logging.getLogger("who_sentinel")
    prev = log.level
    log.setLevel(logging.WARNING)
    try:
        try:
            raise RuntimeError("boom")
        except RuntimeError as e:
            out = _err_out(e)
        payload = _payload(out)
        assert payload["error"] == "boom"
        assert payload["error_type"] == "RuntimeError"
        assert "traceback" not in payload
    finally:
        log.setLevel(prev)


def test_err_out_includes_traceback_when_debug_enabled():
    log = logging.getLogger("who_sentinel")
    prev = log.level
    log.setLevel(logging.DEBUG)
    try:
        try:
            raise ValueError("xyz")
        except ValueError as e:
            out = _err_out(e)
        payload = _payload(out)
        assert payload["error_type"] == "ValueError"
        assert isinstance(payload.get("traceback"), str)
        assert "ValueError" in payload["traceback"]
    finally:
        log.setLevel(prev)
