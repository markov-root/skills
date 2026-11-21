#!/usr/bin/env python3
"""Track open-code-review (`ocr`) consumption: time, tokens, and plan usage when observable.

Reads OCR's own session files (`~/.opencodereview/sessions/<repo>/<run>.jsonl`), so every run is
counted whether it came from the engineering skill, OCR's upstream skills, or a human. New runs are
appended once to a JSONL ledger (default `$XDG_STATE_HOME/software-engineering/ocr-usage.jsonl`).
OCR does not report plan percentages, so each new entry also records the Codex/ChatGPT weekly
usage reading from `usage-check --provider codex --json` when that reading is fresh, and `null`
with a reason otherwise. Standard library only; never contacts a model.

    ocr_usage.py            # sync the ledger, then print a per-day summary
    ocr_usage.py --json     # sync, then print the summary as JSON
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

FRESH_SECONDS = 900


def _state_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "software-engineering" / "ocr-usage.jsonl"


def _sessions_root() -> Path:
    return Path(os.environ.get("OCR_SESSIONS_DIR") or Path.home() / ".opencodereview" / "sessions")


def summarize_session(path: Path) -> dict[str, Any] | None:
    start: dict[str, Any] = {}
    end: dict[str, Any] = {}
    tokens = defaultdict(int)
    calls = comments = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return None
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        if "llmSource" in record:
            start = record
        if "duration_seconds" in record:
            end = record
        usage = record.get("usage")
        if isinstance(usage, dict):
            calls += 1
            for key, value in usage.items():
                if isinstance(value, int):
                    tokens[key] += value
        if isinstance(record.get("comments"), list):
            comments += len(record["comments"])
    if not end:
        return None  # still running or aborted before completion
    manifest = end.get("run_manifest") or {}
    return {
        "run_id": path.stem,
        "repository": path.parent.name,
        "started": start.get("timestamp"),
        "mode": start.get("reviewMode"),
        "range": start.get("diffCommit"),
        "model": start.get("model"),
        "source": start.get("llmSource"),
        "terminal_state": manifest.get("terminal_state"),
        "duration_seconds": round(float(end.get("duration_seconds") or 0), 1),
        "files_reviewed": len(end.get("files_reviewed") or ()),
        "comments": comments,
        "llm_calls": calls,
        "llm_failures": end.get("llm_failures"),
        "prompt_tokens": tokens["prompt_tokens"],
        "completion_tokens": tokens["completion_tokens"],
        "cache_read_tokens": tokens["cache_read_tokens"],
    }


def plan_reading() -> dict[str, Any]:
    if shutil.which("usage-check") is None:
        return {"weekly_used_pct": None, "reason": "usage-check unavailable"}
    completed = subprocess.run(
        ["usage-check", "--provider", "codex", "--json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    try:
        data = json.loads(completed.stdout)
    except ValueError:
        return {"weekly_used_pct": None, "reason": "usage-check returned no JSON"}
    age = data.get("age_seconds")
    if data.get("stale") or not isinstance(age, (int, float)) or age > FRESH_SECONDS:
        return {"weekly_used_pct": None, "reason": f"codex reading stale (age {age}s)"}
    weekly = (data.get("seven_day") or {}).get("used_pct")
    return {"weekly_used_pct": weekly, "reading_age_seconds": age}


def sync(ledger: Path, sessions: Path) -> list[dict[str, Any]]:
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            entries.append(entry)
            seen.add(entry.get("run_id", ""))
    new = []
    for path in sorted(sessions.glob("*/*.jsonl")):
        if path.stem in seen:
            continue
        summary = summarize_session(path)
        if summary is not None:
            new.append(summary)
    if new:
        plan = plan_reading()
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as handle:
            for summary in new:
                summary["plan_at_sync"] = plan
                handle.write(json.dumps(summary, sort_keys=True) + "\n")
        entries.extend(new)
    return entries


def daily(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    days: dict[str, dict[str, Any]] = {}
    for entry in entries:
        day = str(entry.get("started") or "")[:10] or "unknown"
        bucket = days.setdefault(
            day,
            {
                "day": day,
                "runs": 0,
                "seconds": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            },
        )
        bucket["runs"] += 1
        bucket["seconds"] += entry.get("duration_seconds") or 0
        bucket["prompt_tokens"] += entry.get("prompt_tokens") or 0
        bucket["completion_tokens"] += entry.get("completion_tokens") or 0
    return [days[key] for key in sorted(days)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ocr_usage", description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--ledger", type=Path, default=None)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    ledger = args.ledger or _state_path()
    entries = sync(ledger, _sessions_root())
    summary = daily(entries)
    if args.json:
        print(json.dumps({"ledger": str(ledger), "days": summary}, sort_keys=True))
        return 0
    print(f"ledger: {ledger}")
    for day in summary:
        print(
            f"{day['day']}  runs {day['runs']:3}  time {day['seconds'] / 60:6.1f} min  "
            f"tokens in {day['prompt_tokens']:>9,}  out {day['completion_tokens']:>7,}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
