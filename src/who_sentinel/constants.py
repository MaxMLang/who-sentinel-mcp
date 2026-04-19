"""Attribution, disclaimer strings, and base URLs (WHO data use)."""

from __future__ import annotations

import os

ATTRIBUTION_PREFIX = (
    "Source: World Health Organization Data (CC BY 4.0). "
    "https://www.who.int/data/gho/publications/licensing\n\n"
)

SERVER_INSTRUCTIONS = (
    "WHO-Sentinel provides research data from WHO GHO and Disease Outbreak News APIs. "
    "Use it for exploration, teaching, and desk research—not for outbreak response, individual care, "
    "or any decision that requires a qualified public health or medical professional. "
    "Always verify IndicatorCode semantics against GHO metadata before interpreting numbers; "
    "outputs include WHO attribution (CC BY 4.0). "
    "This server is not a clinical diagnostic tool."
)

# Embedded in every JSON tool payload (who_sentinel_meta.disclaimer)
RESPONSE_DISCLAIMER_SHORT = (
    "Research use only; not for clinical diagnosis or emergency response. "
    "Verify indicator definitions and sources."
)

GHO_BASE = "https://ghoapi.azureedge.net/api"
DON_BASE = "https://www.who.int/api/news/diseaseoutbreaknews"
WHO_WEB_BASE = "https://www.who.int"
HDX_HAPI_BASE = "https://hapi.humdata.org"

# OData max $top observed on GHO
GHO_MAX_TOP = 1000

# Default cache TTL for GHO-heavy reads (seconds)
DEFAULT_CACHE_TTL_SEC = 86400  # 24h

# Full RegionCountry + /api catalog (rarely change)
GHO_REGISTRY_TTL_SEC = 604800  # 7d


def gho_base_url() -> str:
    """Effective GHO OData base URL (env-overridable for testing/mirrors)."""
    return os.environ.get("WHO_SENTINEL_GHO_BASE", GHO_BASE)


def don_base_url() -> str:
    """Effective DON OData base URL (env-overridable for testing/mirrors)."""
    return os.environ.get("WHO_SENTINEL_DON_BASE", DON_BASE)


def who_web_base_url() -> str:
    """Effective www.who.int browse base URL (env-overridable)."""
    return os.environ.get("WHO_SENTINEL_WHO_WEB_BASE", WHO_WEB_BASE)


def hdx_hapi_base_url() -> str:
    """Effective HDX HAPI base URL (env-overridable for testing/mirrors)."""
    return os.environ.get("WHO_SENTINEL_HDX_HAPI_BASE", HDX_HAPI_BASE)
