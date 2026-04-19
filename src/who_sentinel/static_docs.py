"""Short MCP resource bodies (WHO data use, not clinical advice)."""

TRUST_AND_USE = """\
# Trust, intended use, and licensing

## Intended use

WHO-Sentinel helps **explore** WHO Global Health Observatory (GHO) indicators and Disease Outbreak News (DON) narratives for **research, teaching, and desk analysis**. Use it to look up codes, compare countries, and read outbreak summaries with clear attribution.

## Misuse to avoid

- **Not** for individual patient care, triage, or treatment decisions.  
- **Not** a substitute for official outbreak response, surveillance systems, or qualified public-health judgment.  
- **Not** real-time assurance: GHO and DON have **publication lag** and may omit subnational or provisional detail.

## Data and licensing

WHO GHO and related public content are typically **CC BY 4.0** where stated; see the [WHO GHO licensing page](https://www.who.int/data/gho/publications/licensing) and the attribution line prefixed on tool outputs.

## Your responsibility

**Verify** each `IndicatorCode` against GHO metadata (`search_gho_indicators`, `list_gho_indicator_dimensions`) before drawing conclusions. Curated disease hints and regex extraction are **assistive**, not authoritative.
"""

GHO_BASICS = """\
# WHO GHO in WHO-Sentinel

- GHO exposes **per-indicator OData entity sets** at `https://ghoapi.azureedge.net/api/{IndicatorCode}`.
- Country/year rows typically use `SpatialDim` (ISO3 for countries) and `TimeDim` (year when `TimeDimType` is YEAR).
- Use **search_gho_indicators** to find codes, **list_gho_indicator_dimensions** to see dimensions (e.g. COUNTRY, YEAR).
- Series points may include **gho_last_updated** and **period_end** for recency; absence does not imply real-time data.

Data: WHO (CC BY 4.0) — see tool attribution prefix in responses.
"""

LIMITATIONS = """\
# Limitations

- **Not** a clinical or public-health decision system; research / exploration only.
- GHO coverage varies by indicator and country; **missing years** are common.
- `surveillance_synthesis` validates that the chosen `IndicatorCode` shares keywords with the disease query (`code_validation`) and reports `code_provenance`. It refuses by default on no overlap; pass `confirm_indicator=true` to override.
- DON matching is **text-based**. Country hints are expanded with pycountry and a small alias overlay, but narratives may still use subnational place names.
- `country_risk_index` returns the **published INFORM Risk Index** (UN OCHA / EC JRC) via HDX HAPI; we don't compute composites of our own. Requires `WHO_SENTINEL_HDX_APP_ID`.
- Respect WHO and HDX services: cache-friendly access; avoid tight polling loops.

Data: WHO (CC BY 4.0); INFORM Risk Index (CC BY 4.0).
"""
