"""Canonical machine-readable contract for ``debate doctor --json``."""

from __future__ import annotations

import json

DOCTOR_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://debate.local/schemas/doctor.schema.json",
    "title": "Debate doctor report",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_id",
        "schema_version",
        "ok",
        "exit_code",
        "backends",
        "panels",
        "smallest_runnable_panel",
        "debates_home",
        "environment",
    ],
    "properties": {
        "schema_id": {"const": "debate.doctor"},
        "schema_version": {"const": "1.0.0"},
        "ok": {"type": "boolean"},
        "exit_code": {"enum": [0, 1]},
        "backends": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "backend",
                    "kind",
                    "available",
                    "authenticated",
                    "detail",
                    "remediation",
                ],
                "properties": {
                    "backend": {"type": "string", "minLength": 1},
                    "kind": {"enum": ["api", "cli"]},
                    "available": {"type": "boolean"},
                    "authenticated": {"type": ["boolean", "null"]},
                    "detail": {"type": "string", "minLength": 1},
                    "remediation": {"type": "string", "minLength": 1},
                },
            },
        },
        "panels": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name",
                    "status",
                    "runnable",
                    "voice_count",
                    "backends",
                    "missing",
                ],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "status": {"enum": ["RUNNABLE", "BLOCKED"]},
                    "runnable": {"type": "boolean"},
                    "voice_count": {"type": "integer", "minimum": 1},
                    "backends": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "missing": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["backend", "detail", "remediation"],
                            "properties": {
                                "backend": {"type": "string", "minLength": 1},
                                "detail": {"type": "string", "minLength": 1},
                                "remediation": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                },
            },
        },
        "smallest_runnable_panel": {"type": ["string", "null"]},
        "debates_home": {
            "type": "object",
            "additionalProperties": False,
            "required": ["path", "source", "exists", "writable", "detail", "override"],
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "source": {"enum": ["--out", "DEBATE_HOME", "platform default"]},
                "exists": {"type": "boolean"},
                "writable": {"type": "boolean"},
                "detail": {"type": "string", "minLength": 1},
                "override": {"type": "string", "minLength": 1},
            },
        },
        "environment": {
            "type": "object",
            "additionalProperties": False,
            "required": ["python", "uv", "offline_cache"],
            "properties": {
                "python": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["version", "supported", "requirement"],
                    "properties": {
                        "version": {"type": "string", "minLength": 1},
                        "supported": {"type": "boolean"},
                        "requirement": {"type": "string", "minLength": 1},
                    },
                },
                "uv": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["available", "path"],
                    "properties": {
                        "available": {"type": "boolean"},
                        "path": {"type": ["string", "null"]},
                    },
                },
                "offline_cache": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["warm", "detail"],
                    "properties": {
                        "warm": {"type": ["boolean", "null"]},
                        "detail": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    },
    "allOf": [
        {
            "if": {"properties": {"ok": {"const": True}}, "required": ["ok"]},
            "then": {
                "properties": {
                    "exit_code": {"const": 0},
                    "smallest_runnable_panel": {"type": "string", "minLength": 1},
                }
            },
            "else": {
                "properties": {
                    "exit_code": {"const": 1},
                    "smallest_runnable_panel": {"type": "null"},
                }
            },
        }
    ],
}


def render_doctor_schema() -> str:
    """Render the checked-in schema deterministically for drift tests and regeneration."""
    return json.dumps(DOCTOR_SCHEMA, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    print(render_doctor_schema(), end="")
