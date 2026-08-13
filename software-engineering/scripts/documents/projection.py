"""Cheap top-level retrieval projections for governed Markdown records."""

from __future__ import annotations

import re

MAX_SUMMARY_CHARACTERS = 150
_SUMMARY_BREAK = re.compile(r"[.!?]\s+\S")


def summary_is_valid(value: object) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and 1 <= len(value) <= MAX_SUMMARY_CHARACTERS
        and value[-1:] in ".!?"
        and "\n" not in value
        and _SUMMARY_BREAK.search(value[:-1]) is None
    )


def allocation_summary(label: str, title: str) -> str:
    prefix = f"{label} record: "
    normalized = title.strip().rstrip(".!?")
    available = MAX_SUMMARY_CHARACTERS - len(prefix) - 1
    return f"{prefix}{normalized[:available].rstrip()}."
