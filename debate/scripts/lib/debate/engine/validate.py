"""Boundary validation of model outputs (ERROR_HANDLING.md: external responses are untrusted).

A model can return well-formed JSON that is the wrong *shape* — a missing clause list, a
bad verifiability enum, a score out of range. The audit trail is the product, so we refuse
to write an output that doesn't satisfy its task's JSON Schema. Fail fast, with the offending
output preserved for debugging.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


class OutputSchemaError(ValueError):
    """A model output failed its task's JSON Schema."""


def load_schema(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def validate_output(obj: dict, schema: dict, *, context: str, dump_to: Path | None = None) -> dict:
    """Validate `obj` against `schema`. On failure, optionally dump the output and raise.

    Returns `obj` unchanged on success so callers can write `out = validate_output(...)`.
    """
    errors = sorted(Draft202012Validator(schema).iter_errors(obj), key=lambda e: e.path)
    if not errors:
        return obj
    if dump_to is not None:
        dump_to.parent.mkdir(parents=True, exist_ok=True)
        dump_to.write_text(json.dumps(obj, indent=2))
    summary = "; ".join(
        f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors[:5]
    )
    where = f" (saved to {dump_to})" if dump_to else ""
    raise OutputSchemaError(f"{context}: output failed schema{where}: {summary}")
