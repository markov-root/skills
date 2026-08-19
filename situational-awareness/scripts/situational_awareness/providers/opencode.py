"""OpenCode provider backed by its durable SQLite session database.

OpenCode normalizes every upstream (including OpenRouter) into assistant-message
JSON containing provider/model plus input and cache read/write counters. Reads use
SQLite read-only mode and never touch auth or network state.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from situational_awareness.core import CacheSample, Raw
from situational_awareness.providers.base import Provider

DEFAULT_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
_SEPARATOR = "@session="


def _db_path() -> Path:
    return Path(os.environ.get("OPENCODE_DB", DEFAULT_DB))


def _encoded(db: Path, session_id: str) -> Path:
    return Path(f"{db}{_SEPARATOR}{session_id}")


def _decode(path: Path) -> tuple[Path, str]:
    text = str(path)
    if _SEPARATOR not in text:
        raise LookupError("OpenCode session id missing from database locator")
    db, session_id = text.rsplit(_SEPARATOR, 1)
    return Path(db), session_id


def _connect(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


class OpenCodeProvider(Provider):
    name = "opencode"

    def locate(self, session: str | None) -> Path | None:
        db = _db_path()
        if not db.is_file():
            return None
        try:
            with _connect(db) as con:
                if session and session != "current":
                    row = con.execute("SELECT id FROM session WHERE id = ?", (session,)).fetchone()
                else:
                    row = con.execute(
                        "SELECT id FROM session "
                        "WHERE time_archived IS NULL AND directory = ? "
                        "ORDER BY time_updated DESC LIMIT 1",
                        (os.getcwd(),),
                    ).fetchone()
                    if row is None:
                        row = con.execute(
                            "SELECT id FROM session WHERE time_archived IS NULL "
                            "ORDER BY time_updated DESC LIMIT 1"
                        ).fetchone()
        except (OSError, sqlite3.Error):
            return None
        return _encoded(db, row["id"]) if row else None

    def list_recent(self, max_age_s: int, limit: int) -> list[Path]:
        db = _db_path()
        if not db.is_file():
            return []
        cutoff_ms = int((time.time() - max_age_s) * 1000)
        try:
            with _connect(db) as con:
                rows = con.execute(
                    "SELECT id FROM session WHERE time_updated >= ? "
                    "ORDER BY time_updated DESC LIMIT ?",
                    (cutoff_ms, limit),
                ).fetchall()
        except (OSError, sqlite3.Error):
            return []
        return [_encoded(db, row["id"]) for row in rows]

    def read(self, path: Path) -> Raw:
        db, session_id = _decode(path)
        samples: list[CacheSample] = []
        provider_id = None
        model = None
        with _connect(db) as con:
            rows = con.execute(
                "SELECT time_created, data FROM message WHERE session_id = ? "
                "ORDER BY time_created, id",
                (session_id,),
            ).fetchall()
        for row in rows:
            try:
                data = json.loads(row["data"])
            except (TypeError, json.JSONDecodeError):
                continue
            if data.get("role") != "assistant":
                continue
            tokens = data.get("tokens")
            if not isinstance(tokens, dict):
                continue
            uncached = int(tokens.get("input", 0) or 0)
            cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
            read = int(cache.get("read", 0) or 0)
            write = int(cache.get("write", 0) or 0)
            total = uncached + read + write
            if total <= 0:  # skip in-flight placeholder messages
                continue
            provider_id = data.get("providerID") or provider_id
            model = data.get("modelID") or model
            samples.append(
                CacheSample(
                    input_tokens=total,
                    read_tokens=read,
                    write_tokens=write,
                    model=f"{provider_id}/{model}" if provider_id and model else model,
                    timestamp=str(row["time_created"]),
                )
            )
        if not samples:
            raise LookupError("no completed assistant usage records in OpenCode session")
        series = [sample.input_tokens for sample in samples]
        display_model = f"{provider_id}/{model}" if provider_id and model else model
        return Raw(
            used_tokens=series[-1],
            model=display_model,
            max_seen=max(series),
            transcript_path=str(path),
            series=series,
            cache_series=samples,
        )

    def resolve_session_id(self, session: str | None, path: Path) -> str:
        return _decode(path)[1]
