"""Validate data against the standard's JSON Schemas (assets/schemas/<name>.schema.json)."""
from __future__ import annotations

import json
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from . import SCHEMA_DIR

NAMES = ("presentations", "talk", "script", "deck", "receipt", "approvals", "delivery",
         "annotations", "slides", "tokens", "library-item")


@cache
def validator(name: str) -> Draft202012Validator:
    if name not in NAMES:
        raise KeyError(f"unknown schema: {name}")
    schema = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def errors(name: str, data: Any) -> list[str]:
    """Human-readable validation errors, each prefixed with its JSON path; [] when valid."""
    out = []
    for err in sorted(validator(name).iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        out.append(f"{where}: {err.message}")
    return out
