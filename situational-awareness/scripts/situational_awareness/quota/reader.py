"""Read provider-owned, on-disk quota snapshots. Dumb + defensive: never raise
on bad/missing data (return a status the caller maps to exit 3).

Claude Code files (written by ~/.claude/usage/statusline-capture.sh):
  latest.json    full statusline payload; we use `.rate_limits`
  history.jsonl  {ts,h5u,h5r,d7u,d7r} per line — burn-rate source
  marks.jsonl    {ts,label,h5u,h5r,d7u,d7r} — calibration marks

Codex embeds its current rate-limit windows in transcript `token_count` events.
They are normalized by their declared window length rather than by
primary/secondary position because account plans expose different combinations.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

DIR = Path(os.environ.get("SITUATIONAL_AWARENESS_USAGE_DIR", Path.home() / ".claude" / "usage"))
LATEST = DIR / "latest.json"
HISTORY = DIR / "history.jsonl"
MARKS = DIR / "marks.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def _age_from_timestamp(value: str | None, fallback: Path, now: float) -> int | None:
    if value:
        try:
            parsed = datetime.fromisoformat(value).timestamp()
            return max(0, int(now - parsed))
        except (TypeError, ValueError):
            pass
    try:
        return max(0, int(now - fallback.stat().st_mtime))
    except OSError:
        return None


def _normalize_codex_windows(rate_limits: dict) -> dict:
    normalized = {
        "five_hour": {"available": False},
        "seven_day": {"available": False},
    }
    for key in ("primary", "secondary"):
        window = rate_limits.get(key)
        if not isinstance(window, dict):
            continue
        minutes = window.get("window_minutes")
        used = window.get("used_percent")
        if minutes is None or used is None:
            continue
        try:
            minutes = float(minutes)
        except (TypeError, ValueError):
            continue
        if minutes <= 6 * 60:
            name = "five_hour"
        elif minutes >= 6 * 24 * 60:
            name = "seven_day"
        else:
            continue
        normalized[name] = {
            "available": True,
            "used_percentage": used,
            "resets_at": window.get("resets_at"),
            "window_minutes": minutes,
        }
    return normalized


def _load_codex_latest(
    session_path: Path | None, now: float
) -> tuple[dict | None, int | None, str]:
    if session_path is None:
        return None, None, "no_cache"
    latest_limits = None
    latest_timestamp = None
    try:
        with open(session_path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = rec.get("payload") or {}
                if payload.get("type") != "token_count":
                    continue
                rate_limits = payload.get("rate_limits")
                if isinstance(rate_limits, dict):
                    latest_limits = rate_limits
                    latest_timestamp = rec.get("timestamp")
    except OSError:
        return None, None, "no_cache"
    age = _age_from_timestamp(latest_timestamp, session_path, now)
    if latest_limits is None:
        return None, age, "no_rate_limits"
    normalized = _normalize_codex_windows(latest_limits)
    if not any(w.get("available") for w in normalized.values()):
        return None, age, "no_rate_limits"
    return normalized, age, "ok"


def load_latest(
    now: float | None = None,
    *,
    provider: str = "claude-code",
    session_path: Path | None = None,
) -> tuple[dict | None, int | None, str]:
    """Return (rate_limits | None, age_seconds | None, status).
    status ∈ 'ok' | 'no_cache' | 'no_rate_limits'.
    age is None when mtime is unknown (fix #2 — caller treats as stale)."""
    now = now if now is not None else time.time()
    if provider == "codex":
        return _load_codex_latest(session_path, now)
    if provider != "claude-code":
        return None, None, "no_rate_limits"
    try:
        with open(LATEST, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None, None, "no_cache"
    try:
        age = max(0, int(now - os.stat(LATEST).st_mtime))
    except OSError:
        age = None
    rl = data.get("rate_limits")
    if not isinstance(rl, dict):
        return None, age, "no_rate_limits"
    return rl, age, "ok"


def load_history() -> list[dict]:
    return _read_jsonl(HISTORY)


def load_marks() -> list[dict]:
    return _read_jsonl(MARKS)


def append_mark(record: dict, cap: int = 1000) -> None:
    """Append a calibration mark, then truncate to the last `cap` lines."""
    DIR.mkdir(parents=True, exist_ok=True)
    with open(MARKS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    rows = _read_jsonl(MARKS)
    if len(rows) > cap:
        with open(MARKS, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in rows[-cap:])
