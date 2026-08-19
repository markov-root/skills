"""Claude Code provider.

Transcript: ~/.claude/projects/<cwd-slug>/<session-uuid>.jsonl (one JSON obj per
line). Context occupancy for a turn is the sum of the three input buckets on that
turn's assistant record:
    input_tokens + cache_read_input_tokens + cache_creation_input_tokens

Two things make the tail of a transcript unreliable on its own:

  * Compaction. Claude Code writes a `{"type":"system","subtype":"compact_boundary"}`
    record (followed by a `isCompactSummary` user message) and RESETS occupancy.
    The pre-compaction turns are still in the file, so until the first
    post-compaction turn is recorded, the newest *usage* record is the big
    pre-compaction number — reporting it claims the window is far fuller than it
    is (the false "55% / wrap_up right after /compact" bug). We detect the marker
    and never report a pre-compaction number as if it were live.

  * Write-lag. The in-flight turn isn't written until it completes, so a
    self-check sees the previous turn (one turn stale).

Both are sidestepped for the CURRENT session by Claude Code's own statusline
capture (~/.claude/usage/latest.json): its `context_window` block is the exact,
post-compaction-correct number `/context` and the `ctx:%` statusline show, and it
states the window authoritatively. We use it when it describes THIS transcript,
and fall back to the (compaction-aware) transcript reader for every other
session / subagent.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from situational_awareness.core import CacheSample, Raw
from situational_awareness.providers.base import Provider

PROJECTS = Path.home() / ".claude" / "projects"

# The statusline re-renders on every turn/tool call. If the capture is older than
# this it is probably not describing the live session any more — fall back to the
# transcript rather than trust a stale number.
STATUSLINE_MAX_AGE_S = 1800


def _statusline_path() -> Path:
    """Claude Code's statusline capture — the authoritative live context number.
    Resolved at call time and overridable via env so tests stay hermetic (never
    read the developer's real session)."""
    return Path(
        os.environ.get(
            "SITUATIONAL_AWARENESS_STATUSLINE",
            str(Path.home() / ".claude" / "usage" / "latest.json"),
        )
    )


def _ctx_tokens(usage: dict) -> int:
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )


def _content_chars(content) -> int:
    """Rough size of a message's text content (str or list-of-blocks)."""
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(b.get("text", "")) for b in content if isinstance(b, dict))
    return 0


def _read_statusline(path: Path) -> tuple[int, int, str | None, float] | None:
    """If Claude Code's live statusline capture describes THIS transcript, return
    its authoritative (used_tokens, window, model, capture_mtime). Else None.

    Matched by `transcript_path`, so it only ever applies to the one live session
    (a subagent or another session has a different path and falls through)."""
    cache = _statusline_path()
    try:
        st = cache.stat()
    except OSError:
        return None
    if time.time() - st.st_mtime > STATUSLINE_MAX_AGE_S:
        return None
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("transcript_path") != str(path):
        return None
    cw = data.get("context_window")
    if not isinstance(cw, dict):
        return None
    win = cw.get("context_window_size")
    used = cw.get("total_input_tokens")
    if not win or used is None:
        return None
    model = (data.get("model") or {}).get("id") if isinstance(data.get("model"), dict) else None
    return int(used), int(win), model, st.st_mtime


class ClaudeCodeProvider(Provider):
    name = "claude-code"

    def locate(self, session: str | None) -> Path | None:
        sid = (
            session
            if session and session != "current"
            else os.environ.get("CLAUDE_CODE_SESSION_ID")
        )
        if not sid:
            return None
        # main-session transcript, or a subagent's (agent-<id>.jsonl)
        for pattern in (f"*/{sid}.jsonl", f"*/agent-{sid}*.jsonl", f"*/{sid}*.jsonl"):
            hits = sorted(PROJECTS.glob(pattern))
            if hits:
                return hits[-1]
        return None

    def list_recent(self, max_age_s: int, limit: int) -> list[Path]:
        now = time.time()
        hits: list[tuple[float, Path]] = []
        for p in PROJECTS.glob("*/*.jsonl"):  # includes subagent agent-*.jsonl
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if now - m <= max_age_s:
                hits.append((m, p))
        hits.sort(reverse=True)
        return [p for _, p in hits[:limit]]

    # --- transcript parsing (compaction-aware) -------------------------------
    def _parse_transcript(
        self, path: Path
    ) -> tuple[str | None, list[int], list[CacheSample], bool, int]:
        """Return (model, usage_series, pending_compaction, summary_est_tokens).

        `usage_series` is per-turn occupancy in file order, EXCLUDING sidechain
        (subagent) turns — those have their own window and must not count toward
        the main thread. `pending_compaction` is True when the newest structural
        event is a `compact_boundary` with no usage turn after it yet (occupancy
        has just reset but the first post-compaction turn isn't recorded)."""
        model: str | None = None
        series: list[int] = []
        cache_series: list[CacheSample] = []
        last_usage_idx = -1
        last_boundary_idx = -1
        summary_chars = 0
        compaction_since_usage = False
        with open(path, encoding="utf-8") as fh:
            for idx, line in enumerate(fh):
                # Cheap pre-filter: only the three record kinds we care about.
                if not (
                    '"compact_boundary"' in line
                    or '"isCompactSummary"' in line
                    or '"usage"' in line
                ):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") == "system" and rec.get("subtype") == "compact_boundary":
                    last_boundary_idx = idx
                    compaction_since_usage = True
                    continue
                msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
                if msg.get("isCompactSummary") or rec.get("isCompactSummary"):
                    summary_chars = _content_chars(msg.get("content"))
                if rec.get("isSidechain"):
                    continue
                usage = msg.get("usage")
                if isinstance(usage, dict):
                    total = _ctx_tokens(usage)
                    series.append(total)
                    last_usage_idx = idx
                    if msg.get("model"):
                        model = msg["model"]
                    cache_series.append(
                        CacheSample(
                            input_tokens=total,
                            read_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
                            write_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
                            model=msg.get("model") or model,
                            timestamp=rec.get("timestamp"),
                            event="compaction" if compaction_since_usage else None,
                        )
                    )
                    compaction_since_usage = False
        pending = last_boundary_idx > last_usage_idx
        # Estimate post-compaction occupancy from the summary size (a lower bound —
        # the real number also includes the system prompt + tool schemas). Only
        # used when there's no live statusline number for this session.
        summary_est = round(summary_chars / 4) if summary_chars else 0
        return model, series, cache_series, pending, summary_est

    def read(self, path: Path) -> Raw:
        model, series, cache_series, pending, summary_est = self._parse_transcript(path)

        live = _read_statusline(path)
        live_used, live_win, live_model = (
            (live[0], live[1], live[2]) if live else (None, None, None)
        )
        transcript_last = series[-1] if series else None
        pre_peak = max(series) if series else 0

        if pending:
            # A compaction is the newest event. The transcript's last usage record
            # is the PRE-compaction number — never report it. If the live statusline
            # has since re-rendered to a value clearly below the pre-compaction peak,
            # it captured the reset and is authoritative; otherwise fall back to the
            # summary-size estimate and flag the state.
            if live_used is not None and live_used < pre_peak * 0.75:
                return Raw(
                    used_tokens=live_used,
                    model=live_model or model,
                    window=int(live_win),
                    window_source="statusline",
                    max_seen=max(live_used, pre_peak),
                    transcript_path=str(path),
                    series=series or [live_used],
                    cache_series=cache_series,
                )
            return Raw(
                used_tokens=summary_est,
                model=model,
                window=None,  # resolved by config.py
                max_seen=pre_peak or summary_est,
                transcript_path=str(path),
                series=series,
                cache_series=cache_series,
                pending_compaction=True,
            )

        if live_used is not None:
            # Statusline is authoritative (it counts pending tool results the next
            # prompt will carry). Take the max so we never UNDER-report occupancy if
            # one clock lags the other — under-reporting is the dangerous direction.
            used = max(live_used, transcript_last or 0)
            return Raw(
                used_tokens=used,
                model=live_model or model,
                window=int(live_win),
                window_source="statusline",
                max_seen=max([used, *series]),
                transcript_path=str(path),
                series=series or [used],
                cache_series=cache_series,
            )

        # No live capture for this session (a subagent / another session / no
        # statusline installed) — transcript only.
        if transcript_last is None:
            raise LookupError("no usage records in transcript")
        return Raw(
            used_tokens=transcript_last,
            model=model,
            window=None,  # resolved by config.py
            max_seen=pre_peak,
            transcript_path=str(path),
            series=series,
            cache_series=cache_series,
        )
