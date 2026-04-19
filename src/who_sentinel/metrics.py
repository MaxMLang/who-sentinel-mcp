"""In-process counters (single MCP server process)."""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_http_gets = 0
_tool_calls: dict[str, int] = {}


def record_http_get() -> None:
    global _http_gets
    with _lock:
        _http_gets += 1


def record_tool(name: str) -> None:
    with _lock:
        _tool_calls[name] = _tool_calls.get(name, 0) + 1


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "http_get_total": _http_gets,
            "tool_calls_by_name": dict(sorted(_tool_calls.items())),
        }
