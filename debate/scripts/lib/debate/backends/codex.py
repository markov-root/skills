"""CodexCliDebater — headless `codex exec` on a Codex/ChatGPT subscription ($0 marginal)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from debate.backends.base import AtCapacity, EmptyCompletion, _raise_cli_failure, _retry
from debate.config import get_settings


@dataclass
class CodexCliDebater:
    """Headless `codex exec` on a Codex/ChatGPT subscription — OpenAI's flagship (e.g. gpt-5.5) as
    one panel voice at $0 marginal cost (flat plan). Monovendor (OpenAI) on its own.

    Two differences from `claude -p`: `codex exec` has no system-prompt flag, so the system prompt
    is folded into the prompt (callers extract JSON tolerantly downstream, so no envelope needed);
    and `codex exec` is agentic by default, so it is pinned to a read-only, ephemeral sandbox — a
    debate voice only emits text and must never run a model-issued shell command or touch the tree.
    The final agent message is captured via `-o`; token usage from the `turn.completed` event."""

    id: str
    model: str | None = None
    backend: str = "codex_cli"
    timeout_s: float | None = None  # per-debater override; else settings.codex_cli_timeout_s
    reasoning_effort: str | None = None  # per-debater; else settings.codex_reasoning_effort
    max_retries: int | None = None
    workspace: str | None = None  # materials_mode 'disk' (ADR-0010): working root it may READ
    last_meta: dict = field(default_factory=dict)

    def generate(self, system: str, user: str, *, want_json: bool = False) -> str:
        timeout = self.timeout_s or get_settings().codex_cli_timeout_s
        attempts = (
            self.max_retries if self.max_retries is not None else get_settings().max_retries
        ) + 1
        prompt = f"{system}\n\n---\n\n{user}" if system else user

        def call() -> str:
            with tempfile.NamedTemporaryFile("r", suffix=".txt", delete=False) as f:
                out_path = f.name
            cmd = [
                "codex",
                "exec",
                "--skip-git-repo-check",  # the cwd isn't a git unit of work
                "--ephemeral",  # don't persist session files across a batch run
                "-s",
                "read-only",  # a debater emits text — never let it mutate anything
                "--color",
                "never",
                "--json",  # JSONL events on stdout (token usage)
                "-o",
                out_path,  # final agent message → file (the result text)
            ]
            if self.model:
                cmd += ["-m", self.model]
            if self.workspace:  # materials_mode 'disk': read the corpus files under this root
                cmd += ["-C", self.workspace]
            # Fairness (panels.yaml): every voice gets the SAME thinking budget. codex exec else
            # runs GPT at its low default (~500 reasoning tokens, vs 4k–16k for the OpenRouter
            # panelists at high), so GPT under-deliberates vs peers. Pin to the configured effort,
            # mirroring OpenRouterDebater's reasoning.effort.
            if effort := (self.reasoning_effort or get_settings().codex_reasoning_effort):
                cmd += ["-c", f"model_reasoning_effort={effort}"]
            try:
                proc = subprocess.run(
                    cmd, input=prompt, capture_output=True, text=True, timeout=timeout
                )
                if proc.returncode != 0:
                    # Mirror claude_code, plus distinguish codex "at capacity" (a transient 503 →
                    # retry with backoff) from a plan-limit (→ park, resumable). ADR-0016.
                    _raise_cli_failure(
                        self.id, proc.returncode, proc.stdout, proc.stderr, allow_capacity=True
                    )
                result = Path(out_path).read_text().strip()
            finally:
                Path(out_path).unlink(missing_ok=True)
            # Token usage from the turn.completed event. Best-effort: codex is a flat subscription
            # (not in metrics._BILLED_BACKENDS), so this is informational — a parse miss must not
            # fail an otherwise-good call. Common token schema across backends so metrics.json sums.
            usage: dict = {}
            for line in proc.stdout.splitlines():
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "turn.completed" and ev.get("usage"):
                    usage = ev["usage"]
            self.last_meta = {
                "model": self.model,
                "cost_usd": None,  # flat subscription — $0 marginal (notional only)
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "cached_tokens": usage.get("cached_input_tokens"),  # prompt-cache read
                "reasoning_tokens": usage.get("reasoning_output_tokens"),
            }
            if not result:
                # A clean exit with no final message = a degraded turn; raise so _retry re-calls.
                raise EmptyCompletion(f"{self.id}: codex exec produced no final message")
            return result

        return _retry(
            call,
            attempts=attempts,
            transient=(subprocess.TimeoutExpired, EmptyCompletion, AtCapacity),
            label=self.id,
        )
