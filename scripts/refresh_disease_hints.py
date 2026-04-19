"""Regenerate the auto_generated half of data/disease_hints.json from live GHO.

Run locally with ``uv run python scripts/refresh_disease_hints.py`` or weekly via
``.github/workflows/refresh-disease-hints.yml``. The script preserves the
editorial ``curated`` overlay and only rewrites ``auto_generated`` per topic.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from who_sentinel.cache import TTLCache
from who_sentinel.clients.gho import GhoClient

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPO_ROOT / "src" / "who_sentinel" / "data" / "disease_hints.json"

PER_QUERY_LIMIT = 25
PER_TOPIC_LIMIT = 30


def _auto_generated_for_topic(gho: GhoClient, topic: dict[str, Any]) -> list[dict[str, str]]:
    seen: set[str] = set()
    for c in topic.get("curated") or []:
        code = str(c.get("code") or "")
        if code:
            seen.add(code)

    out: list[dict[str, str]] = []
    for query in topic.get("search_queries") or []:
        if not isinstance(query, str) or not query.strip():
            continue
        rows = gho.search_indicators(query.strip(), top=PER_QUERY_LIMIT)
        for r in rows:
            code = str(r.get("IndicatorCode") or "")
            name = str(r.get("IndicatorName") or "")
            if not code or code in seen:
                continue
            seen.add(code)
            out.append({"code": code, "name": name})
            if len(out) >= PER_TOPIC_LIMIT:
                return out
    return out


def refresh(snapshot_path: Path = SNAPSHOT_PATH) -> tuple[bool, dict[str, Any]]:
    """Refresh the snapshot in place; return (changed, snapshot)."""
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    topics = data.get("topics") or []
    before = json.dumps([t.get("auto_generated") for t in topics], sort_keys=True)

    gho = GhoClient(cache=TTLCache(default_ttl_sec=3600.0))
    try:
        for topic in topics:
            topic["auto_generated"] = _auto_generated_for_topic(gho, topic)
    finally:
        gho.close()

    after = json.dumps([t.get("auto_generated") for t in topics], sort_keys=True)
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return (before != after, data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the snapshot would change (use as a dry run in CI).",
    )
    args = parser.parse_args()

    changed, _ = refresh()
    if args.check and changed:
        print("disease_hints.json would change", file=sys.stderr)
        return 1
    print(f"disease_hints.json {'updated' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
