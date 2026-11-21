"""Start a deck worker process with a chosen brand (tasks 0008, 0016). Imports nothing from the
deck package itself, so the CLI process never binds a brand."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parents[2]  # .../scripts/cli


class WorkerError(Exception):
    def __init__(self, message: str, detail: str = "", data: dict | None = None):
        super().__init__(message)
        self.detail = detail
        self.data = data or {}


def worker(
    args: list[str], *, tokens: Path | None, repo: Path | None, timeout: int = 1800
) -> dict:
    env = {
        **os.environ,
        "PYTHONPATH": str(CLI_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    env.pop("PRESENT_TOKENS", None)
    if tokens is not None:
        env["PRESENT_TOKENS"] = str(tokens)
    if repo is not None:
        env["PRESENT_REPO"] = str(repo)
    proc = subprocess.run(
        [sys.executable, "-m", "present_cli.deck.worker", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        data = json.loads(last)
    except json.JSONDecodeError:
        raise WorkerError(
            f"deck worker failed (exit {proc.returncode})",
            (proc.stderr or proc.stdout)[-1500:],
        )
    if proc.returncode != 0 or "error" in data:
        raise WorkerError(
            data.get("error", f"deck worker exit {proc.returncode}"),
            proc.stderr[-1500:],
            data,
        )
    return data
