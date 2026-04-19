"""Stdlib logging setup from environment."""

from __future__ import annotations

import logging
import os


def configure_logging() -> None:
    level_name = os.environ.get("WHO_SENTINEL_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
