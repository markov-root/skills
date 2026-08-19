"""Provider-agnostic core: the ladder, the action mapping, and the result shape.

Nothing here knows about Claude or codex. Providers hand us a `Raw` (how many
prompt tokens the last turn consumed, which model, and — if they know it — the
window). Core turns that into a `Reading` with an `action`.
"""

from __future__ import annotations

import itertools
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

# --- exit codes (mirrors usage-check's grammar: one action -> one code) --------
EXIT_CONTINUE = 0
EXIT_WRAP_UP = 11
EXIT_HANDOFF = 10
EXIT_NO_DATA = 3
EXIT_ERROR = 2

_ACTION_EXIT = {
    "continue": EXIT_CONTINUE,
    "wrap_up": EXIT_WRAP_UP,
    "handoff_now": EXIT_HANDOFF,
}


@dataclass
class CacheSample:
    """One provider-reported input/cache usage sample.

    `input_tokens` is the total prompt size for the request. `read_tokens` and
    `write_tokens` are subsets when the provider exposes them.
    """

    input_tokens: int
    read_tokens: int = 0
    write_tokens: int = 0
    model: str | None = None
    timestamp: str | None = None
    event: str | None = None

    @property
    def uncached_tokens(self) -> int:
        return max(0, self.input_tokens - self.read_tokens - self.write_tokens)


@dataclass
class Raw:
    """What a provider extracts from a session transcript."""

    used_tokens: int
    model: str | None = None
    window: int | None = None  # authoritative if the provider knows it (codex does)
    window_source: str | None = None  # e.g. "transcript"
    max_seen: int | None = None  # largest prompt-token count in this transcript
    transcript_path: str | None = None
    stale: bool = False
    # A compaction just reset occupancy and the first post-compaction turn isn't
    # recorded yet, so `used_tokens` is a lower-bound estimate, not a live count.
    pending_compaction: bool = False
    series: list[int] = field(default_factory=list)  # per-turn used_tokens, in order
    cache_series: list[CacheSample] = field(default_factory=list)


@dataclass
class Reading:
    provider: str
    session: str
    model: str | None
    window: int
    window_source: str
    used_tokens: int
    used_pct: float
    remaining_pct: float
    zone: str
    action: str
    message: str
    confidence: str
    stale: bool
    policy: str = "conservative"
    transcript_path: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return _ACTION_EXIT[self.action]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["transcript_path"] = display_path(self.transcript_path)
        d.pop("notes") if not self.notes else None
        return d


def display_path(value: str | None) -> str | None:
    """Render a diagnostic path without exposing the current user's home path.

    Paths under the home directory become home-relative. Other absolute paths
    retain only their basename, which keeps JSON useful without publishing host
    layout details. Internal filesystem access continues to use the original path.
    """
    if value is None:
        return None
    home = str(Path.home())
    if value == home:
        return "~"
    if value.startswith(home + os.sep):
        return "~" + value[len(home) :]
    if os.path.isabs(value):
        return f"<absolute>/{Path(value).name}"
    return value


# --- the ladder (v2, % of window REMAINING) -----------------------------------
# > 70   normal          continue
# 60-70  offload         continue   (prefer subagents for bulky reads)
# 50-60  wrap_up         wrap_up    (finish open work, draft handoff, no new threads)
# 40-50  wrap_up_strong  wrap_up    (stronger)
# 30-40  handoff         handoff_now
# < 30   critical        handoff_now (should essentially never happen)
_LADDER = [
    (70.0, "normal", "continue", "context {rem:.0f}% remaining — continue"),
    (
        60.0,
        "offload",
        "continue",
        "context {rem:.0f}% remaining — prefer subagents/offload for bulky reads",
    ),
    (
        50.0,
        "wrap_up",
        "wrap_up",
        (
            "context {rem:.0f}% remaining — finish open tasks, note deferred items, draft handoff; "
            "no new threads unless the user is explicit"
        ),
    ),
    (
        40.0,
        "wrap_up_strong",
        "wrap_up",
        "context {rem:.0f}% remaining — wrap up now, write the handoff, stop opening new threads",
    ),
    (
        30.0,
        "handoff",
        "handoff_now",
        "context {rem:.0f}% remaining — checkpoint and hand off to a fresh session now",
    ),
    (
        0.0,
        "critical",
        "handoff_now",
        "context {rem:.0f}% remaining — CRITICAL: stop, write the handoff, do not start new work",
    ),
]

# Harnesses that automatically summarize and immediately continue need a
# different workflow policy, not different context arithmetic. The same stable
# actions/exit codes remain; only their thresholds and messages change.
_CONTINUOUS_COMPACTION_LADDER = [
    (70.0, "normal", "continue", "context {rem:.0f}% remaining — continue"),
    (
        60.0,
        "offload",
        "continue",
        "context {rem:.0f}% remaining — prefer offloading bulky reads",
    ),
    (
        20.0,
        "checkpoint",
        "continue",
        (
            "context {rem:.0f}% remaining — keep task, decision, and test docs current before "
            "automatic compaction; continue the current outcome"
        ),
    ),
    (
        5.0,
        "compaction_near",
        "continue",
        (
            "context {rem:.0f}% remaining — automatic compaction is near; finish durable "
            "checkpointing, then continue"
        ),
    ),
    (
        0.0,
        "compaction_recovery",
        "continue",
        (
            "context {rem:.0f}% remaining — let the harness compact, then re-read applicable "
            "instructions and active task/checkpoint docs before continuing"
        ),
    ),
]


def classify(remaining_pct: float, policy: str = "conservative") -> tuple[str, str, str]:
    """Return (zone, action, message-template) for a given % remaining."""
    ladder = _CONTINUOUS_COMPACTION_LADDER if policy == "continuous-compaction" else _LADDER
    for floor, zone, action, tmpl in ladder:
        if remaining_pct >= floor:
            return zone, action, tmpl
    return ladder[-1][1], ladder[-1][2], ladder[-1][3]


# --- forecast (task 0006) & fit check (task 0010) ----------------------------
# Zone boundaries as fraction of window USED: wrap_up begins at 40% used
# (60% remaining), handoff at 60% used (40% remaining). Kept in sync with _LADDER.
_WRAP_USED_FRAC = 0.40
_HANDOFF_USED_FRAC = 0.60


def forecast(
    used: int,
    window: int,
    series: list[int],
    lookback: int = 6,
    policy: str = "conservative",
) -> dict:
    """Estimate turns until the wrap_up / handoff thresholds, from recent growth.
    Uses only positive per-turn deltas (a negative step = compaction, skipped)."""
    deltas = [b - a for a, b in itertools.pairwise(series) if b > a]
    recent = deltas[-lookback:]
    rate = (sum(recent) / len(recent)) if recent else 0.0
    out = {
        "tokens_per_turn": round(rate),
        "turns_until_wrap_up": None,
        "turns_until_handoff": None,
    }
    if rate <= 0:
        return out
    import math

    if policy == "continuous-compaction":
        checkpoint_used = 0.40 * window
        headroom = checkpoint_used - used
        out["turns_until_checkpoint"] = max(0, math.floor(headroom / rate)) if headroom > 0 else 0
        return out

    for key, frac in (
        ("turns_until_wrap_up", _WRAP_USED_FRAC),
        ("turns_until_handoff", _HANDOFF_USED_FRAC),
    ):
        headroom = frac * window - used
        out[key] = max(0, math.floor(headroom / rate)) if headroom > 0 else 0
    return out


def fits(estimate: int, used: int, window: int, policy: str = "conservative") -> dict:
    """Would `estimate` more tokens fit? Report vs the window and vs the 'safe'
    handoff boundary (staying above 40% remaining)."""
    to_window = window - used
    safe_used_frac = 1.0 if policy == "continuous-compaction" else _HANDOFF_USED_FRAC
    to_handoff = int(safe_used_frac * window) - used
    remaining_after = to_window - estimate
    if estimate <= to_handoff:
        advice = "fits with safe headroom — go ahead"
    elif estimate <= to_window:
        advice = "fits, but would push you into the handoff zone — offload or split"
    else:
        advice = "does NOT fit — offload to subagents/codex, or split into batches"
    return {
        "estimate": estimate,
        "remaining_before": to_window,
        "remaining_after": remaining_after,
        "fits": estimate <= to_window,
        "fits_safely": estimate <= to_handoff,
        "advice": advice,
    }


def build_reading(
    provider: str,
    session: str,
    raw: Raw,
    window: int,
    window_source: str,
    policy: str = "conservative",
) -> Reading:
    window = max(window, 1)
    used_pct = round(raw.used_tokens / window * 100, 1)
    remaining_pct = round(100 - used_pct, 1)
    zone, action, tmpl = classify(remaining_pct, policy)

    notes: list[str] = []
    confidence = "high"

    # A compaction just reset occupancy but the first post-compaction turn isn't
    # recorded yet: `used_tokens` is only a lower-bound estimate (the compact
    # summary size). Never let a stale pre-compaction number trip wrap_up/handoff —
    # occupancy is genuinely low right now. Report high headroom, low confidence.
    if raw.pending_compaction:
        zone, action = "post_compaction", "continue"
        confidence = "low"
        message = (
            f"compaction just occurred — occupancy reset (~{used_pct:.0f}% used, "
            "lower-bound estimate); first post-compaction turn not yet recorded. "
            "Treat as high headroom; the real number appears next turn."
        )
        notes.append(
            "estimate is a lower bound (compact-summary size only); refreshes after the next turn"
        )
        return Reading(
            provider=provider,
            session=session,
            model=raw.model,
            window=window,
            window_source=window_source,
            used_tokens=raw.used_tokens,
            used_pct=used_pct,
            remaining_pct=remaining_pct,
            zone=zone,
            action=action,
            message=message,
            confidence=confidence,
            stale=raw.stale,
            policy=policy,
            transcript_path=raw.transcript_path,
            notes=notes,
        )

    if window_source in ("default", "default-fallback"):
        confidence = "medium"
        notes.append(f"window {window:,} assumed from {window_source}; set it in config to be sure")
    if window_source == "floor":
        notes.append(f"window raised to {window:,} — a past turn exceeded the assumed window")
    if raw.stale:
        confidence = "low"
        notes.append("last turn looks stale; number may lag the live session")
    if policy == "continuous-compaction" and remaining_pct < 60:
        notes.append(
            "after automatic compaction, re-read applicable instructions and active "
            "task/checkpoint docs before continuing"
        )

    return Reading(
        provider=provider,
        session=session,
        model=raw.model,
        window=window,
        window_source=window_source,
        used_tokens=raw.used_tokens,
        used_pct=used_pct,
        remaining_pct=remaining_pct,
        zone=zone,
        action=action,
        message=tmpl.format(rem=remaining_pct),
        confidence=confidence,
        stale=raw.stale,
        policy=policy,
        transcript_path=raw.transcript_path,
        notes=notes,
    )
