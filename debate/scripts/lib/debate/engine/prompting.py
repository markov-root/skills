"""Shared prompt-assembly helpers — used by the engine loop and by task aggregate steps."""

from __future__ import annotations

import json


def blocks(*parts: str) -> str:
    """Join non-empty sections with blank lines."""
    return "\n\n".join(p for p in parts if p)


def json_block(label: str, obj: dict) -> str:
    return f"{label}:\n```json\n{json.dumps(obj, indent=2)}\n```"
