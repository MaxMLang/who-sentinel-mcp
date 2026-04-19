from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ExtractResult:
    cases: int | None
    deaths: int | None
    cfr: float | None
    confidence: str
    evidence_snippets: list[str]
    cfr_from_explicit_text: bool = False


# Adjectives often stack between count and noun ("144 suspected and confirmed cases").
# Kept as a whitelist so unrelated digits ("100 of these were …") don't get parsed.
_CASE_ADJ = (
    r"(?:laboratory[-\s]?confirmed|suspected|confirmed|probable|reported|"
    r"new|additional|further|fatal|human|severe|symptomatic|presumptive|positive)"
)
_CASE_ADJ_GROUP = rf"(?:{_CASE_ADJ}(?:[\s,]+(?:and|or)\s+{_CASE_ADJ}|[\s,]+{_CASE_ADJ}){{0,3}}\s+)?"

_DEATH_ADJ = r"(?:reported|new|additional|further|confirmed|suspected|associated|human)"
_DEATH_ADJ_GROUP = rf"(?:{_DEATH_ADJ}(?:[\s,]+(?:and|or)\s+{_DEATH_ADJ}|[\s,]+{_DEATH_ADJ}){{0,3}}\s+)?"

_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_NUM_WORD_RE = "|".join(_NUM_WORDS)

_CASE_PATTERNS = [
    re.compile(
        rf"a\s+total\s+of\s+(?P<n>\d[\d,]*)\s+{_CASE_ADJ_GROUP}(?:human\s+)?cases?\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<n>\d[\d,]*)\s+{_CASE_ADJ_GROUP}(?:human\s+)?cases?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<n>\d[\d,]*)\s+patients?\s+have\s+been\s+laboratory[-\s]?confirmed",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<word>{_NUM_WORD_RE})\s+{_CASE_ADJ_GROUP}(?:human\s+)?cases?\b",
        re.IGNORECASE,
    ),
]

_DEATH_PATTERNS = [
    re.compile(
        rf"(?:including|of\s+which|with)\s+(?P<n>\d[\d,]*)\s+{_DEATH_ADJ_GROUP}deaths?\b",
        re.IGNORECASE,
    ),
    re.compile(rf"(?P<n>\d[\d,]*)\s+{_DEATH_ADJ_GROUP}deaths?\b", re.IGNORECASE),
    re.compile(
        r"(?P<n>\d[\d,]*)\s+(?:people|persons|individuals|patients)\s+(?:have\s+)?died\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?P<n>\d[\d,]*)\s+have\s+died\b", re.IGNORECASE),
    re.compile(r"(?P<n>\d[\d,]*)\s+fatalities\b", re.IGNORECASE),
    re.compile(
        rf"\b(?P<word>{_NUM_WORD_RE})\s+{_DEATH_ADJ_GROUP}(?:deaths?|fatalities)\b",
        re.IGNORECASE,
    ),
]

# Allow a short clause between "fatality rate" and the verb ("rate among
# hospitalized patients was 12.5%"); bounded so it can't slurp paragraphs.
_CFR_PATTERNS = [
    re.compile(
        r"case\s+fatality(?:\s+ratio|\s+rate)?(?:\s*\(CFR\))?[^%]{0,80}?"
        r"(?:of|is|was|at)\s*(?P<p>\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    ),
    re.compile(
        r"case\s+fatality(?:\s+ratio|\s+rate)?(?:\s*\(CFR\))?\s*(?P<p>\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    ),
    re.compile(
        r"CFR(?:\s*\([^)]*\))?\s*(?:of|is|was|at)?\s*(?P<p>\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    ),
    re.compile(r"(?P<p>\d+(?:\.\d+)?)\s*%\s+case\s+fatality", re.IGNORECASE),
]


def _match_int(m: re.Match[str]) -> int | None:
    """Pull an int out of a numeric ``(?P<n>)`` or spelled-out ``(?P<word>)`` capture."""
    g = m.groupdict()
    if g.get("n"):
        try:
            return int(g["n"].replace(",", ""))
        except ValueError:
            return None
    if g.get("word"):
        return _NUM_WORDS.get(g["word"].lower())
    return None


def extract_outbreak_metadata(text: str) -> ExtractResult:
    """Lightweight regex/heuristic extraction from DON narrative HTML/text."""

    raw = text or ""
    # Decode entities (&nbsp;, &#37;) after stripping tags so the regexes see plain digits.
    plain = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()
    snippets: list[str] = []

    cases: int | None = None
    deaths: int | None = None

    for pat in _CASE_PATTERNS:
        m = pat.search(plain)
        if not m:
            continue
        v = _match_int(m)
        if v is not None:
            cases = v
            snippets.append(m.group(0)[:240])
            break

    for pat in _DEATH_PATTERNS:
        m = pat.search(plain)
        if not m:
            continue
        v = _match_int(m)
        if v is not None:
            deaths = v
            snippets.append(m.group(0)[:240])
            break

    cfr: float | None = None
    cfr_explicit = False
    for pat in _CFR_PATTERNS:
        m = pat.search(plain)
        if not m:
            continue
        try:
            cfr = round(float(m.group("p")), 2)
        except (ValueError, IndexError):
            continue
        cfr_explicit = True
        snippets.append(m.group(0)[:240])
        break

    if cfr is None and cases and deaths and cases > 0:
        cfr = round(100.0 * deaths / cases, 2)

    conf = "medium" if cfr_explicit or (cases is not None and deaths is not None) else "low"

    return ExtractResult(
        cases=cases,
        deaths=deaths,
        cfr=cfr,
        confidence=conf,
        evidence_snippets=snippets[:6],
        cfr_from_explicit_text=cfr_explicit,
    )


def extract_result_to_dict(er: ExtractResult) -> dict[str, Any]:
    return {
        "cases": er.cases,
        "deaths": er.deaths,
        "case_fatality_ratio_percent": er.cfr,
        "confidence": er.confidence,
        "evidence_snippets": er.evidence_snippets,
        "cfr_source": "explicit_text" if er.cfr_from_explicit_text else "derived_or_none",
    }
