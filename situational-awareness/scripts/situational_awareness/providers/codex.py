"""Codex provider.

Transcript: ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl. Token usage
arrives as `event_msg` records with payload.type == "token_count". Codex helpfully
embeds the AUTHORITATIVE window as `info.model_context_window`, so — unlike Claude
— we never have to guess. Context occupancy for the last turn is
`info.last_token_usage.input_tokens`.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from situational_awareness.core import CacheSample, Raw
from situational_awareness.providers.base import Provider

SESSIONS = Path.home() / ".codex" / "sessions"


class CodexProvider(Provider):
    name = "codex"

    def locate(self, session: str | None) -> Path | None:
        sid = session if session and session != "current" else os.environ.get("CODEX_THREAD_ID")
        if sid:
            hits = sorted(SESSIONS.glob(f"**/rollout-*{sid}*.jsonl"))
            return hits[-1] if hits else None
        hits = sorted(SESSIONS.glob("**/rollout-*.jsonl"))
        return hits[-1] if hits else None  # "current" -> most recent

    def list_recent(self, max_age_s: int, limit: int) -> list[Path]:
        now = time.time()
        hits: list[tuple[float, Path]] = []
        for p in SESSIONS.glob("**/rollout-*.jsonl"):
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if now - m <= max_age_s:
                hits.append((m, p))
        hits.sort(reverse=True)
        return [p for _, p in hits[:limit]]

    def read(self, path: Path) -> Raw:
        window = None
        model = None
        series: list[int] = []
        cache_series: list[CacheSample] = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                model = _find_model(rec) or model
                payload = rec.get("payload") or {}
                if payload.get("type") != "token_count":
                    continue
                info = payload.get("info") or {}
                last_usage = info.get("last_token_usage") or {}
                last = last_usage.get("input_tokens")
                if last is not None:
                    series.append(last)
                    cache_series.append(
                        CacheSample(
                            input_tokens=int(last),
                            read_tokens=int(last_usage.get("cached_input_tokens", 0) or 0),
                            write_tokens=int(last_usage.get("cache_write_input_tokens", 0) or 0),
                            model=model,
                            timestamp=rec.get("timestamp"),
                        )
                    )
                if info.get("model_context_window"):
                    window = info["model_context_window"]
        if not series:
            raise LookupError("no token_count events in transcript")
        return Raw(
            used_tokens=series[-1],
            model=model,
            window=window,
            window_source="transcript" if window else None,
            max_seen=max(series),
            transcript_path=str(path),
            series=series,
            cache_series=cache_series,
        )

    def resolve_session_id(self, session: str | None, path: Path) -> str:
        if session and session != "current":
            return session
        # rollout-<ISO-ts-with-dashes>-<uuid>.jsonl -> the trailing UUID
        m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", path.stem)
        return m.group(0) if m else path.stem


def _find_model(rec: dict) -> str | None:
    """Model id shows up in session_meta / turn_context; scan defensively."""
    for key in ("model", "model_slug"):
        if isinstance(rec.get(key), str):
            return rec[key]
    for container in ("payload", "turn_context", "info"):
        sub = rec.get(container)
        if isinstance(sub, dict) and isinstance(sub.get("model"), str):
            return sub["model"]
    return None
