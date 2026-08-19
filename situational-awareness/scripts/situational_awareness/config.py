"""Window resolution — the one genuinely hard part (see docs/DISCOVERY.md §Window,
docs/adrs/0003-window-resolution-strategy.md).

Two independent facts must be established, and they are NOT the same:
  * MODEL-aware:   which model produced this session? (windows differ wildly —
                   200K / 256K / 272K / 400K / 1M / 2M depending on model+beta)
  * SESSION-aware: how many tokens has *this* session's last turn consumed?

`used_tokens` is always read from the specific session's transcript (session-aware).
The WINDOW is a property of the model, resolved most-authoritative-first:

  1. provider-authoritative — codex embeds `model_context_window` in its transcript.
  2. explicit user config   — ~/.config/situational-awareness/config.toml (per-model or per-provider).
  3. statusline auto-detect — Claude's [1m] marker, BUT only when we are inspecting
                              the *current* session (the statusline describes the
                              live agent's model, not some other session's).
  4. per-model default table.
  5. floor guard            — never under-report below the largest turn ever seen in
                              this very session (a >200K turn *proves* a big window).
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

from situational_awareness.core import Raw

# Per-MODEL context windows. Windows are a property of the model, not the provider,
# so this table is keyed by model id. codex/gemini transcripts often state the
# window authoritatively (see providers) — these are fallbacks for when they don't.
# Verified on this machine: Claude runs the [1m] beta by default (a past turn hit
# 842,373 tokens, impossible under 200K).
DEFAULT_WINDOWS: dict[str, int] = {
    # Anthropic (bare id can be 200K standard OR 1M with the [1m] beta — ambiguous;
    # resolved by statusline/config/floor for the current session).
    "claude-opus-4-8": 1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-haiku-4-5": 200_000,
    # OpenAI / codex (authoritative window normally comes from the transcript).
    "gpt-5.5": 272_000,
    "gpt-5.4-mini": 272_000,
    "gpt-5.4": 272_000,
    # Google (for the future gemini provider).
    "gemini-2.5-pro": 1_048_576,
    "gemini-2.5-flash": 1_048_576,
}

# Family fallbacks when the exact model id is unknown/unlisted.
FAMILY_DEFAULTS: dict[str, int] = {
    "claude-code": 1_000_000,  # this machine's [1m] default
    "codex": 272_000,
    "gemini-cli": 1_048_576,
    "opencode": 200_000,
}
GENERIC_DEFAULT = 200_000
_TIERS = (200_000, 256_000, 272_000, 400_000, 1_000_000, 2_000_000)

CONFIG_PATH = Path(
    os.environ.get(
        "SITUATIONAL_AWARENESS_CONFIG",
        Path.home() / ".config" / "situational-awareness" / "config.toml",
    )
)

CONTEXT_POLICIES = ("conservative", "continuous-compaction")
DEFAULT_CONTEXT_POLICIES = {
    "claude-code": "conservative",
    "codex": "continuous-compaction",
    "opencode": "conservative",
}


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, "rb") as fh:
            return tomllib.load(fh)
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        return {}


def _config_window(cfg: dict, provider: str, model: str | None) -> int | None:
    if model:
        w = cfg.get("models", {}).get(model, {}).get("window")
        if w:
            return int(w)
    w = cfg.get("providers", {}).get(provider, {}).get("window")
    return int(w) if w else None


def resolve_context_policy(provider: str, override: str | None = None) -> str:
    """Resolve the workflow policy separately from raw context occupancy.

    The conservative ladder preserves the original explicit handoff policy.
    Continuous-compaction keeps working through a harness-managed summary while
    still checkpointing early and retaining low-headroom stop guards.
    """
    cfg = _load_config()
    value = (
        override
        or os.environ.get("SITUATIONAL_AWARENESS_CONTEXT_POLICY")
        or cfg.get("providers", {}).get(provider, {}).get("context_policy")
        or DEFAULT_CONTEXT_POLICIES.get(provider, "conservative")
    )
    if value not in CONTEXT_POLICIES:
        raise ValueError(
            f"unknown context policy {value!r}; expected one of {', '.join(CONTEXT_POLICIES)}"
        )
    if provider == "opencode" and os.environ.get("OPENCODE_DISABLE_AUTOCOMPACT"):
        return "conservative"
    return value


def _statusline_window(model: str | None) -> int | None:
    """Best-effort: the model display captured by usage-check's statusline wrapper.
    A '[1m]' marker (or a 1000000 context field) means the 1M beta is active."""
    latest = Path.home() / ".claude" / "usage" / "latest.json"
    try:
        with open(latest) as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    hay = json.dumps(data).lower()
    if "[1m]" in hay or "1000000" in hay:
        return 1_000_000
    return None


def _next_tier(n: int) -> int:
    for t in _TIERS:
        if n <= t:
            return t
    return n


def resolve_window(provider: str, raw: Raw, is_current: bool = False) -> tuple[int, str]:
    """Return (window_tokens, source). `is_current` gates statusline detection —
    the statusline only describes the live agent's model, so it must NOT be trusted
    when inspecting a different session (e.g. a subagent on another model)."""
    if raw.window:
        return raw.window, raw.window_source or "transcript"

    cfg = _load_config()
    w = _config_window(cfg, provider, raw.model)
    if w:
        return _apply_floor(w, raw, "config")

    if provider == "claude-code" and is_current:
        w = _statusline_window(raw.model)
        if w:
            return _apply_floor(w, raw, "statusline")

    if raw.model and raw.model in DEFAULT_WINDOWS:
        return _apply_floor(DEFAULT_WINDOWS[raw.model], raw, "default")

    fallback = FAMILY_DEFAULTS.get(provider, GENERIC_DEFAULT)
    return _apply_floor(fallback, raw, "default-fallback")


def _apply_floor(window: int, raw: Raw, source: str) -> tuple[int, str]:
    """Never claim more headroom than the session has already disproven."""
    if raw.max_seen and raw.max_seen > window:
        return _next_tier(raw.max_seen), "floor"
    return window, source
