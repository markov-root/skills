"""Honest date normalization for the queryable projection (Task 0025).

Harvested dates are evidence of varying trust, not facts. This module turns whatever date strings an
adapter surfaced into a provenance-tagged ``[{value, via, confidence}]`` list and drops values that
are implausible or match a known parser sentinel — recording *why* as a diagnostic rather than
silently presenting a guess as a publication date.

Pure functions of their inputs plus the current UTC year (for the plausibility ceiling); the ceiling
is read once per call so behavior is deterministic within a run.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timezone

PLAUSIBLE_MIN_YEAR = 1990

_ISO_DATE = re.compile(r"(?P<year>\d{4})(?:-(?P<month>\d{2})(?:-(?P<day>\d{2}))?)?")


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def _confidence_for(via: str) -> str:
    """A document-information date is stronger evidence than a heuristic HTML guess."""

    lowered = via.lower()
    if "docinfo" in lowered or "pdf" in lowered or "pymupdf" in lowered:
        return "medium"
    return "low"


def _is_sentinel(year: int, month: int | None, day: int | None) -> bool:
    """January 1 of the current year with no finer evidence is the classic htmldate fallback."""

    return month == 1 and day == 1 and year == _current_year()


def normalize_dates(
    metadata: Mapping[str, str],
    via: str,
) -> tuple[list[dict[str, object]], list[str]]:
    """Return (accepted dates, rejection diagnostics) for the date candidates in ``metadata``."""

    raw = metadata.get("date")
    if not raw:
        return [], []
    max_year = _current_year() + 1
    accepted: list[dict[str, object]] = []
    diagnostics: list[str] = []
    value = raw.strip()
    match = _ISO_DATE.match(value)
    if match is None:
        return [], [f"rejected date {value!r} (via {via}): unparseable"]
    year = int(match.group("year"))
    month = int(match.group("month")) if match.group("month") else None
    day = int(match.group("day")) if match.group("day") else None
    if year < PLAUSIBLE_MIN_YEAR or year > max_year:
        diagnostics.append(
            f"rejected date {value!r} (via {via}): year {year} outside "
            f"[{PLAUSIBLE_MIN_YEAR}, {max_year}]"
        )
    elif _is_sentinel(year, month, day):
        diagnostics.append(
            f"rejected date {value!r} (via {via}): current-year Jan-1 sentinel "
            "(likely a parser fallback, not a real publication date)"
        )
    else:
        accepted.append(
            {"value": value, "via": via, "confidence": _confidence_for(via)}
        )
    return accepted, diagnostics
