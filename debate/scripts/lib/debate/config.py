"""Typed configuration, validated at startup (CONFIGURATION.md: validate at boot, not at use).

Read once, validated, then immutable. The OpenRouter key is allowed to be empty so that
offline paths (Claude Code backend, tests) work without it; a run that uses an OpenRouter
backend calls `require_api_key()` up front so it fails fast — before spending any calls —
rather than mid-debate.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError


def _development_env_path(package_dir: Path) -> Path | None:
    """Return the checkout-local env file, never an installed site-packages neighbor."""
    if (package_dir / "_data").is_dir():
        return None
    candidate = package_dir.parent / ".env"
    return candidate if candidate.is_file() else None


def _load_development_env(package_dir: Path) -> None:
    env_file = _development_env_path(package_dir)
    if env_file is None:
        return
    if os.name != "nt" and env_file.stat().st_mode & 0o077:
        raise RuntimeError(f"{env_file} must not be accessible by group or other users (use 0600)")
    # Exported variables win: dotenv never overrides the process environment.
    load_dotenv(env_file)


# Source-checkout convenience only. Installed packages use the caller's environment/configuration
# manager and never look for a potentially unrelated `.env` beside site-packages.
_load_development_env(Path(__file__).resolve().parent)


class Settings(BaseModel):
    openrouter_api_key: str = ""
    openrouter_app_url: str = ""
    openrouter_app_title: str = "Debate"
    # Scoring injects the full provider dossier (~500k chars for ss-7.3) and reasoning models
    # (kimi, glm) routinely think 3–5 min BEFORE emitting output, then generate a long JSON.
    # Generous so a slow-but-fine call isn't killed and re-charged on a timeout retry.
    request_timeout_s: float = 900.0
    # Claude Code (`claude -p`) is much slower than the API and scales with prompt size; heavy
    # rounds (revise/aggregate on big measures) can run several minutes. Generous by design.
    claude_code_timeout_s: float = 900.0
    # Codex CLI (`codex exec`) backend — headless GPT on a Codex/ChatGPT subscription ($0 marginal).
    # Same generous timeout rationale as claude_code (agentic CLI, slower than a raw API call).
    codex_cli_timeout_s: float = 900.0
    # Fairness: codex exec runs GPT at a low reasoning default (~500 tokens) unless told otherwise,
    # so pin it to the same effort band as the OpenRouter panelists (none|minimal|low|medium|high).
    codex_reasoning_effort: str = "high"
    max_retries: int = 4  # transient-failure retries per model call
    # Fairness across the cross-vendor panel: every OpenRouter debater gets the SAME reasoning
    # budget (OpenRouter normalises `reasoning.effort` across providers) and temperature, so no
    # model is silently given more "thinking time" than another. "none" disables reasoning.
    openrouter_reasoning_effort: str = "high"
    # Web access is OFF by design: the scorer/generator must ground ONLY in the injected,
    # SHA-pinned sources (the grounding gate rejects any quote not in them). Live web results are
    # non-reproducible and unpinnable — they'd break provenance and the false-zero discipline.
    openrouter_web_search: bool = False
    # Independent within-round calls (propose/critique/revise/respond) may run concurrently.
    max_concurrency: int = 4
    # Dynamic debate rounds (ADR-0011). `max_debate_rounds` CAPS total phases — floor (propose,
    # critique, revise) = 3; each adversarial pass (redteam + respond) = 2. Default 5 = exactly
    # today's full config (floor + one standard red-team pass), so behaviour is unchanged until
    # raised; raising it (e.g. 7, 9) admits escalation passes on the contested subset, which stop on
    # EXHAUSTED SEARCH not agreement. `debate_token_budget` (None = off) is a graceful ceiling: when
    # cumulative output tokens reach it, escalation stops with a resumable ongoing-incomplete marker
    # rather than dying mid-pass. The floor is never refused on budget — only escalation is gated.
    max_debate_rounds: int = 5
    debate_token_budget: int | None = None
    # Output token budget per call. This is an upper BOUND, not a target — a model stops at its
    # natural end (finish_reason=stop) and you only pay for tokens actually produced — so being
    # generous is essentially free and just prevents truncation. Reasoning models can also spend
    # tens of thousands of tokens thinking, which on some providers counts toward this cap, so the
    # visible JSON gets cut off if it's tight (16k then 32k both truncated kimi/glm/gpt on ss-7.3).
    max_output_tokens: int = 64000

    def require_api_key(self) -> None:
        if not self.openrouter_api_key:
            raise SystemExit(
                "OPENROUTER_API_KEY is not set — copy .env.example to .env and fill it in. "
                "(Only Claude Code / offline runs work without it.)"
            )


@cache
def get_settings() -> Settings:
    try:
        return Settings(
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            openrouter_app_url=os.environ.get("OPENROUTER_APP_URL", ""),
            openrouter_app_title=os.environ.get("OPENROUTER_APP_TITLE", "Debate"),
            request_timeout_s=float(os.environ.get("REQUEST_TIMEOUT_S", "900")),
            claude_code_timeout_s=float(os.environ.get("CLAUDE_CODE_TIMEOUT_S", "900")),
            codex_cli_timeout_s=float(os.environ.get("CODEX_CLI_TIMEOUT_S", "900")),
            codex_reasoning_effort=os.environ.get("CODEX_REASONING_EFFORT", "high"),
            max_retries=int(os.environ.get("MAX_RETRIES", "4")),
            openrouter_reasoning_effort=os.environ.get("OPENROUTER_REASONING_EFFORT", "high"),
            openrouter_web_search=os.environ.get("OPENROUTER_WEB_SEARCH", "").lower()
            in {"1", "true", "yes"},
            max_concurrency=int(os.environ.get("MAX_CONCURRENCY", "4")),
            max_output_tokens=int(os.environ.get("MAX_OUTPUT_TOKENS", "64000")),
            max_debate_rounds=int(os.environ.get("MAX_DEBATE_ROUNDS", "5")),
            debate_token_budget=(int(b) if (b := os.environ.get("DEBATE_TOKEN_BUDGET")) else None),
        )
    except (ValidationError, ValueError) as e:
        raise SystemExit(f"Invalid configuration:\n{e}") from e
