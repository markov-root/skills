"""ClaudeCodeDebater — headless `claude -p` on the Max plan; subscription-only (no console bill)."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

from debate.backends.base import _raise_cli_failure, _retry
from debate.config import get_settings


@dataclass
class ClaudeCodeDebater:
    """Headless `claude -p` on the Max plan. No per-token billing. Monovendor on its own."""

    id: str
    model: str | None = None
    backend: str = "claude_code"
    timeout_s: float | None = None  # per-debater override; else settings.claude_code_timeout_s
    max_retries: int | None = None
    workspace: str | None = (
        None  # materials_mode 'disk' (ADR-0010): dir the voice may READ files in
    )
    # Per-call telemetry from the LAST generate() — `claude -p --output-format json` already
    # returns duration_ms / total_cost_usd / usage; we extract it instead of dropping it.
    last_meta: dict = field(default_factory=dict)

    def generate(self, system: str, user: str, *, want_json: bool = False) -> str:
        timeout = self.timeout_s or get_settings().claude_code_timeout_s
        attempts = (
            self.max_retries if self.max_retries is not None else get_settings().max_retries
        ) + 1
        cmd = ["claude", "-p", "--output-format", "json", "--append-system-prompt", system]
        if self.model:
            cmd += ["--model", self.model]
        # materials_mode 'disk': let the voice open the corpus files (read-only) via --add-dir.
        cwd = self.workspace or None
        if self.workspace:
            cmd += ["--add-dir", self.workspace]
        # Never bill the Anthropic console: `claude -p` prefers a present API key over its OAuth
        # subscription, so an ambient ANTHROPIC_API_KEY (e.g. in .env) would silently meter-bill
        # — a ~$95 leak upstream (ADR-0016). Strip it from the child env so a run is
        # strictly subscription-only. No behaviour change when the key isn't set.
        child_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

        def call() -> str:
            proc = subprocess.run(
                cmd,
                input=user,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=child_env,
            )
            if proc.returncode != 0:
                # A quota hit exits non-zero with the "usage limit reached" text on STDOUT (not
                # stderr), so classification scans both: a plan-limit parks (resumable), anything
                # else is fatal for this voice (task-0011 then drops it if a quorum remains).
                _raise_cli_failure(
                    self.id, proc.returncode, proc.stdout, proc.stderr, allow_capacity=False
                )
            payload = json.loads(proc.stdout)
            usage = payload.get("usage") or {}
            # Common token schema across backends (see OpenRouterDebater) so metrics.json sums.
            self.last_meta = {
                "model": payload.get("modelUsage") and next(iter(payload["modelUsage"]), None),
                "duration_ms": payload.get("duration_ms"),
                "duration_api_ms": payload.get("duration_api_ms"),
                "cost_usd": payload.get("total_cost_usd"),
                "num_turns": payload.get("num_turns"),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "cached_tokens": usage.get("cache_read_input_tokens"),  # prompt-cache read
                "cache_write_tokens": usage.get("cache_creation_input_tokens"),
            }
            return payload.get("result", "")

        return _retry(
            call, attempts=attempts, transient=(subprocess.TimeoutExpired,), label=self.id
        )
