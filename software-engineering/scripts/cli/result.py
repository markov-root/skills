"""Versioned public envelope construction."""

from __future__ import annotations

from typing import Any

from ..commands.contracts import CommandResult

SCHEMA_VERSION = 1


def envelope(command: str, result: CommandResult) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "status": result.status,
        "project_root": str(result.root) if result.root else None,
        **result.data,
    }
