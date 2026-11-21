"""Per-leaf feedback: record which `present` leaf ran, content-free (portfolio ADR 0006 D4; task 0021).

The public launcher `scripts/present` is a `skill-feedback` adapter. It records one invocation per
call with the static feature `cli`, and it exposes neither its invocation id nor a feature resolver
to the child. Until it does, `present` records a second, content-free invocation pair through the
documented `skill-feedback start` / `finish` commands:

- feature: the resolved leaf name (`talk.list`, `deck.build`, `usage`, `help`), never arguments;
- outcome: from the exit class, which is also carried as the tag `exit-class:<name>`;
- tags `present-leaf` and `nested`, so a consumer can tell these from the adapter's own pair.

It is a strict no-op, and never changes the exit code, when `skill-feedback` is absent, when
`SKILL_FEEDBACK_DISABLE=1` or `SKILL_FEEDBACK_DISABLE_SKILLS` names this skill, or when automatic
collection is not enabled (`skill-feedback collection` is not `manifest_opt_in` with a retention
policy). Only commands are used; skill-feedback's files are never read (ADR 0006 D1).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from . import SKILL_ROOT

SKILL = "presentation"
ADAPTER_MARKER = "# skill-feedback-managed-wrapper:"
TIMEOUT_S = 10
_TRUE = {"1", "true", "yes", "on"}

OUTCOME = {
    "OK": "success",
    "ERROR": "failure",
    "USAGE": "failure",
    "NOT_IMPLEMENTED": "failure",
}


def _binary() -> str | None:
    return shutil.which("skill-feedback")


def env_disabled() -> str | None:
    """The environment opt-out in force, if any (mirrors `skill-feedback run`)."""
    if os.environ.get("SKILL_FEEDBACK_DISABLE", "").strip().lower() in _TRUE:
        return "SKILL_FEEDBACK_DISABLE"
    names = {
        n.strip()
        for n in os.environ.get("SKILL_FEEDBACK_DISABLE_SKILLS", "").split(",")
    }
    if SKILL in names:
        return "SKILL_FEEDBACK_DISABLE_SKILLS"
    return None


def _collection(binary: str) -> dict[str, Any] | None:
    """`skill-feedback collection --json` (read-only without --off/--manifest-opt-in)."""
    try:
        out = subprocess.run(
            [binary, "collection", "--json"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
        if out.returncode != 0:
            return None
        value = json.loads(out.stdout)
        return value if isinstance(value, dict) else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def collection_state() -> dict[str, Any]:
    """Read-only: is per-leaf (and adapter) collection active, and if not, why."""
    binary = _binary()
    state: dict[str, Any] = {
        "skill_feedback": binary,
        "env_opt_out": env_disabled(),
        "automatic_collection": None,
        "retention": None,
        "active": False,
    }
    if binary is None:
        state["state"] = "unavailable"
        return state
    config = _collection(binary)
    if config is None:
        state["state"] = "unknown"
        return state
    retention = config.get("retention") or {}
    state["automatic_collection"] = config.get("automatic_collection")
    state["retention"] = retention.get("mode") if isinstance(retention, dict) else None
    enabled = (
        bool(config.get("configured"))
        and state["automatic_collection"] == "manifest_opt_in"
        and state["retention"] not in (None, "unset")
    )
    if state["env_opt_out"]:
        state["state"] = "disabled_by_env"
    elif not enabled:
        state["state"] = "off"
    else:
        state["state"], state["active"] = "on", True
    return state


def adapter_state(launcher: Path | None = None) -> dict[str, Any]:
    """Read-only: is the public launcher a skill-feedback managed adapter, and what does it wrap."""
    path = launcher or SKILL_ROOT / "scripts" / "present"
    info: dict[str, Any] = {
        "path": str(path),
        "managed": False,
        "feature": None,
        "target": None,
        "target_exists": False,
    }
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[:5]
    except OSError:
        return info
    info["managed"] = any(line.startswith(ADAPTER_MARKER) for line in lines)
    for line in lines:
        if line.startswith("# metadata:"):
            try:
                meta = json.loads(line.split(":", 1)[1])
            except ValueError:
                break
            info["feature"], info["target"] = meta.get("feature"), meta.get("target")
            if isinstance(info["target"], str):
                info["target_exists"] = (path.parent / info["target"]).is_file()
    return info


def record_leaf(leaf: str, exit_class: str, duration_ms: int) -> bool:
    """Append a content-free start/finish pair naming `leaf`. Fail-open: never raises."""
    try:
        if env_disabled() is not None:
            return False
        binary = _binary()
        if binary is None or not collection_state()["active"]:
            return False
        invocation = f"use-present-{uuid.uuid4().hex}"
        common = [
            "--actor",
            "automation",
            "--source",
            "deterministic",
            "--by",
            "present",
            "--tag",
            "present-leaf",
            "--tag",
            "nested",
            "--tag",
            f"exit-class:{exit_class.lower()}",
        ]
        start = subprocess.run(
            [
                binary,
                "start",
                SKILL,
                "--invocation-id",
                invocation,
                "--feature",
                leaf,
                *common,
            ],
            capture_output=True,
            timeout=TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
        if start.returncode != 0:
            return False
        finish = subprocess.run(
            [
                binary,
                "finish",
                SKILL,
                invocation,
                "--outcome",
                OUTCOME.get(exit_class, "unknown"),
                "--duration-ms",
                str(max(0, duration_ms)),
                *common,
            ],
            capture_output=True,
            timeout=TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
        return finish.returncode == 0
    except Exception:  # telemetry must never change the command's result
        return False
