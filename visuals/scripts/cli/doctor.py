#!/usr/bin/env python3
"""`visuals doctor` — read-only readiness verdict for the authored-render engine.

Per-item verdicts:
  browser            Chrome or Chromium presence and version (required)
  python3            the resolved interpreter and its version (required)
  uv                 the resolved uv and its version (required)
  image-generation   the generative delegate, capability-detected (optional,
                     honest degradation per ADR 0006)
  project config     visuals.toml resolved by walking up from the working
                     directory, when one exists (optional)

Exit 0 when the authored-render engine can run, 3 when a required component is
absent — never 0 on an unusable environment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BROWSER_CANDIDATES = (
    "/usr/bin/google-chrome",
    "/snap/bin/chromium",
    "/usr/bin/chromium-browser",
    "google-chrome",
    "chromium",
    "chromium-browser",
)

# Delegate detection constants live in the capability domain (cli/delegate.py)
# — the single source shared with the `visuals image` shim, so the two can
# never drift (audit F7 discipline). Re-exported here for the module's own
# check wrapper and for tests that monkeypatch them on doctor.
from delegate import (  # noqa: E402  (constants block, before code)
    DELEGATE_COMMAND_NAMES,
    DELEGATE_ENTRYPOINTS,
    DELEGATE_INSTALL_CANDIDATES,
)
import delegate as _delegate  # noqa: E402

CONFIG_NAME = "visuals.toml"
KNOWN_CONFIG_SCHEMA_VERSIONS = ("1",)

REQUIRED = ("browser", "python3", "uv")


def _version_of(cmd: str) -> str | None:
    try:
        proc = subprocess.run(
            [cmd, "--version"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = (proc.stdout or proc.stderr).strip().splitlines()
    return line[0].strip() if line else None


def check_browser() -> dict:
    for candidate in BROWSER_CANDIDATES:
        resolved = shutil.which(candidate) or (
            candidate
            if candidate.startswith("/") and Path(candidate).is_file()
            else None
        )
        if not resolved:
            continue
        version = _version_of(resolved)
        if version:
            return {
                "name": "browser",
                "status": "ok",
                "required": True,
                "detail": f"{version} ({resolved})",
            }
    return {
        "name": "browser",
        "status": "missing",
        "required": True,
        "detail": "no Chrome/Chromium found (tried: "
        + ", ".join(BROWSER_CANDIDATES)
        + ")",
    }


def check_python3() -> dict:
    resolved = shutil.which("python3")
    if not resolved:
        return {
            "name": "python3",
            "status": "missing",
            "required": True,
            "detail": "python3 not on PATH",
        }
    version = _version_of(resolved) or f"Python {sys.version.split()[0]}"
    return {
        "name": "python3",
        "status": "ok",
        "required": True,
        "detail": f"{version} ({resolved})",
    }


def check_uv() -> dict:
    resolved = shutil.which("uv")
    if not resolved:
        return {
            "name": "uv",
            "status": "missing",
            "required": True,
            "detail": "uv not on PATH (needed by uv-weight commands; install https://docs.astral.sh/uv/)",
        }
    version = _version_of(resolved)
    return {
        "name": "uv",
        "status": "ok",
        "required": True,
        "detail": f"{version or 'version unknown'} ({resolved})",
    }


def delegate_on_path() -> str | None:
    """Resolve the delegate as a PATH command, if the machine exposes one."""
    return _delegate.delegate_on_path(command_names=DELEGATE_COMMAND_NAMES)


def check_delegate() -> dict:
    """Thin wrapper over the capability-domain detection (cli/delegate.py);
    the module constants above stay the monkeypatchable seam for tests."""
    found = _delegate.resolve_delegate(
        candidates=DELEGATE_INSTALL_CANDIDATES,
        command_names=DELEGATE_COMMAND_NAMES,
    )
    if found:
        if found.kind == "entrypoint":
            return {
                "name": "image-generation",
                "status": "ok",
                "required": False,
                "detail": f"delegate available ({found.location})",
            }
        return {
            "name": "image-generation",
            "status": "ok",
            "required": False,
            "detail": f"delegate available on PATH ({found.location})",
        }
    # The unavailable message stays byte-identical to the pre-refactor report;
    # delegate.missing_detail is the image shim's richer variant (it names the
    # install command), while doctor reports absence without advice.
    return {
        "name": "image-generation",
        "status": "unavailable",
        "required": False,
        "detail": "delegate not installed (checked "
        + ", ".join(str(c) for c in DELEGATE_INSTALL_CANDIDATES)
        + "; no "
        + "/".join(DELEGATE_COMMAND_NAMES)
        + " on PATH)"
        + "; generative commands degrade honestly per ADR 0006",
    }


def find_project_config() -> Path | None:
    """Resolve visuals.toml by walking up from the working directory."""
    here = Path.cwd().resolve()
    for parent in (here, *here.parents):
        candidate = parent / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def check_project_config() -> dict:
    path = find_project_config()
    if path is None:
        return {
            "name": "project config",
            "status": "absent",
            "required": False,
            "detail": f"no {CONFIG_NAME} found walking up from {Path.cwd()}",
        }
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'^\s*schema_version\s*=\s*["\']?([\w.]+)', text, re.M)
    if not match:
        return {
            "name": "project config",
            "status": "invalid",
            "required": False,
            "detail": f"{path} has no schema_version",
        }
    version = match.group(1)
    if version not in KNOWN_CONFIG_SCHEMA_VERSIONS:
        return {
            "name": "project config",
            "status": "invalid",
            "required": False,
            "detail": f"{path} declares schema_version {version!r}; known: "
            + ", ".join(KNOWN_CONFIG_SCHEMA_VERSIONS),
        }
    return {
        "name": "project config",
        "status": "ok",
        "required": False,
        "detail": f"{path} (schema_version {version})",
    }


CHECKS = (
    check_browser,
    check_python3,
    check_uv,
    check_delegate,
    check_project_config,
)


def run_checks() -> list[dict]:
    return [check() for check in CHECKS]


def verdict(items: list[dict]) -> tuple[bool, list[str]]:
    """(ready, names of failed required items)."""
    missing = [i["name"] for i in items if i.get("required") and i["status"] != "ok"]
    return (not missing, missing)


def render_human(items: list[dict], ready: bool, missing: list[str]) -> str:
    lines = ["visuals doctor — environment readiness"]
    for item in items:
        flag = {
            "ok": "ok",
            "missing": "MISSING",
            "unavailable": "unavailable",
            "absent": "absent",
            "invalid": "INVALID",
        }[item["status"]]
        opt = "" if item["required"] else " (optional)"
        lines.append(f"  {item['name']:<18} {flag:<11}{opt}  {item['detail']}")
    if ready:
        lines.append("verdict: ready — the authored-render engine can run (exit 0)")
    else:
        lines.append(
            f"verdict: NOT READY — required absent: {', '.join(missing)} (exit 3)"
        )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """Handler entry point. `argv` is this command's own arguments, without the
    program name or the command name — the dispatcher declares no flags for us
    (that would be a second command catalog), so we parse our own here."""
    parser = argparse.ArgumentParser(prog="visuals doctor", add_help=False)
    parser.add_argument("--json", action="store_true", help="emit a JSON verdict")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2  # usage

    items = run_checks()
    ready, missing = verdict(items)
    if args.json:
        print(
            json.dumps(
                {
                    "command": "doctor",
                    "ready": ready,
                    "exit_code": 0 if ready else 3,
                    "missing_required": missing,
                    "items": items,
                },
                indent=2,
            )
        )
    else:
        print(render_human(items, ready, missing))
    return 0 if ready else 3
