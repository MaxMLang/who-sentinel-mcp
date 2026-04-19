from __future__ import annotations

import re
import uuid
from typing import Any

import httpx

from who_sentinel.constants import don_base_url, who_web_base_url
from who_sentinel.http_retry import request_get_with_retry


_DON_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")


def _validate_don_id(raw: str) -> str:
    """Validate a DON record Id (UUID/GUID). Raises ValueError on bad input."""
    s = (raw or "").strip()
    if not s:
        raise ValueError("don_id is required")
    try:
        return str(uuid.UUID(s))
    except (ValueError, AttributeError):
        if _DON_ID_RE.match(s):
            return s
        raise ValueError("don_id must be a UUID/GUID string") from None


def _combine_narrative(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("Summary", "Overview", "Response", "Assessment", "Advice", "Epidemiology"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return "\n\n".join(parts)


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _country_text_matches(raw_text: str, norm_blob: str, hint: str) -> bool:
    h = hint.strip()
    if not h:
        return True
    if len(h) == 3 and h.isalpha():
        return re.search(rf"\b{re.escape(h)}\b", raw_text, re.IGNORECASE) is not None
    return _norm(h) in norm_blob


class DonClient:
    """WHO Disease Outbreak News OData client."""

    def __init__(self, base_url: str | None = None, timeout_sec: float = 45.0) -> None:
        self.base_url = (base_url or don_base_url()).rstrip("/")
        self._client = httpx.Client(timeout=timeout_sec, headers={"Accept": "application/json"})

    def close(self) -> None:
        self._client.close()

    def _get_json(self, params: dict[str, Any]) -> dict[str, Any]:
        r = request_get_with_retry(
            self._client,
            self.base_url,
            params=params,
            headers={"Accept": "application/json"},
        )
        return r.json()

    def list_recent(self, limit: int = 25) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 100))
        data = self._get_json({"$orderby": "PublicationDate desc", "$top": str(lim)})
        return list(data.get("value") or [])

    def get_by_id(self, don_id: str) -> dict[str, Any] | None:
        safe_id = _validate_don_id(don_id)
        flt = f"Id eq {safe_id}"
        data = self._get_json({"$filter": flt, "$top": "1"})
        rows = data.get("value") or []
        return rows[0] if rows else None

    @staticmethod
    def truncate_text(text: str | None, max_chars: int = 500) -> str:
        if not text:
            return ""
        t = text.strip()
        if len(t) <= max_chars:
            return t
        return t[: max_chars - 1].rstrip() + "…"


def filter_outbreak_rows(
    rows: list[dict[str, Any]],
    disease_query: str | None,
    country_hints: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Client-side filter on title + narrative.
    Country: any hint may match (ISO3 uses word boundaries; names use normalized substring).
    """

    d_q = _norm(disease_query) if disease_query else ""
    hints = [h for h in (country_hints or []) if h and str(h).strip()]
    hints_norm = list(dict.fromkeys(hints))  # preserve order, dedupe

    out: list[dict[str, Any]] = []
    for row in rows:
        title = str(row.get("Title") or "")
        narrative = _combine_narrative(row)
        raw_text = f"{title}\n{narrative}"
        norm_blob = _norm(raw_text)

        if d_q and d_q not in norm_blob:
            continue

        if hints_norm:
            if not any(_country_text_matches(raw_text, norm_blob, h) for h in hints_norm):
                continue

        out.append(row)
    return out


def outbreak_narrative_text(row: dict[str, Any]) -> str:
    """Plain-ish text for extraction (strips HTML tags not applied here)."""
    return _combine_narrative(row)


def don_public_url(row: dict[str, Any]) -> str | None:
    """Canonical browse URL on who.int for a DON item."""
    base = who_web_base_url().rstrip("/")
    path = row.get("ItemDefaultUrl")
    if isinstance(path, str) and path.strip():
        p = path.strip()
        if not p.startswith("/"):
            p = "/" + p
        return f"{base}{p}"
    un = row.get("UrlName")
    if isinstance(un, str) and un.strip():
        return f"{base}/{un.strip().lstrip('/')}"
    return None


def outbreak_summary_row(row: dict[str, Any], overview_max: int = 500) -> dict[str, Any]:
    overview = str(row.get("Overview") or "")
    out = {
        "Id": row.get("Id"),
        "Title": row.get("Title"),
        "PublicationDate": row.get("PublicationDate"),
        "UrlName": row.get("UrlName"),
        "ItemDefaultUrl": row.get("ItemDefaultUrl"),
        "public_url": don_public_url(row),
        "Summary": DonClient.truncate_text(str(row.get("Summary") or ""), overview_max),
        "Overview_excerpt": DonClient.truncate_text(overview, overview_max),
    }
    return out
