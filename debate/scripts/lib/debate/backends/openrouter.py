"""OpenRouterDebater — a pinned model via OpenRouter (reproducible; for published editions)."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from debate.backends.base import _TRANSIENT, BackendProbe, EmptyCompletion, _client, _log, _retry
from debate.config import get_settings


@dataclass
class OpenRouterDebater:
    id: str
    model: str
    temperature: float = 0.0
    backend: str = "openrouter"
    web: bool = (
        False  # per-voice web search (materials_mode 'search', ADR-0010); else settings flag
    )
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    max_retries: int | None = None
    client: object | None = field(default=None, repr=False)
    # Per-call telemetry from the LAST generate() (tokens/cost/duration); read by the debate
    # loop after each call to build the run's metrics.json. The API already returns this; we
    # were discarding it. Empty until the first call.
    last_meta: dict = field(default_factory=dict)

    @classmethod
    def probe(cls) -> BackendProbe:
        """Verify the configured key with a bounded, no-model-call OpenRouter request."""
        api_key = get_settings().openrouter_api_key
        if not api_key:
            return BackendProbe(
                cls.backend,
                "api",
                False,
                False,
                "OPENROUTER_API_KEY is not set",
                "Set OPENROUTER_API_KEY in the process environment, then rerun `debate doctor`.",
            )

        request = Request(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=5) as response:
                status = response.getcode()
        except HTTPError as exc:
            if exc.code in (401, 403):
                return BackendProbe(
                    cls.backend,
                    "api",
                    True,
                    False,
                    f"OpenRouter rejected the configured credential (HTTP {exc.code})",
                    "Replace OPENROUTER_API_KEY, then rerun `debate doctor`.",
                )
            return BackendProbe(
                cls.backend,
                "api",
                True,
                None,
                f"OpenRouter credential could not be verified (HTTP {exc.code})",
                "Check OpenRouter availability, then rerun `debate doctor`.",
            )
        except (URLError, TimeoutError, OSError):
            return BackendProbe(
                cls.backend,
                "api",
                True,
                None,
                "OPENROUTER_API_KEY is configured but unverified (network unavailable)",
                "Allow bounded access to openrouter.ai, then rerun `debate doctor`.",
            )

        if status == 200:
            return BackendProbe(
                cls.backend,
                "api",
                True,
                True,
                "OpenRouter accepted the configured credential",
                "No action required; the probe made no model call.",
            )
        if status in (401, 403):
            return BackendProbe(
                cls.backend,
                "api",
                True,
                False,
                f"OpenRouter rejected the configured credential (HTTP {status})",
                "Replace OPENROUTER_API_KEY, then rerun `debate doctor`.",
            )
        return BackendProbe(
            cls.backend,
            "api",
            True,
            None,
            f"OpenRouter credential could not be verified (HTTP {status})",
            "Check OpenRouter availability, then rerun `debate doctor`.",
        )

    def generate(self, system: str, user: str, *, want_json: bool = False) -> str:
        s = None
        if (
            self.max_output_tokens is None
            or self.reasoning_effort is None
            or self.max_retries is None
        ):
            s = get_settings()
        kwargs: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.temperature,
            "max_tokens": (
                self.max_output_tokens
                if self.max_output_tokens is not None
                else s.max_output_tokens
            ),
        }
        if want_json:
            kwargs["response_format"] = {"type": "json_object"}
        # Fairness + grounding knobs, applied identically to every model (see Settings):
        #   reasoning.effort — same "thinking budget" for all (OpenRouter normalises it);
        #   web search — OFF unless explicitly enabled (grounding must stay on injected sources).
        extra_body: dict = {}
        effort = (
            self.reasoning_effort
            if self.reasoning_effort is not None
            else s.openrouter_reasoning_effort
        )
        if effort and effort != "none":
            extra_body["reasoning"] = {"effort": effort}
        elif effort == "none":
            extra_body["reasoning"] = {"enabled": False}
        if self.web or (s is not None and s.openrouter_web_search):
            extra_body["plugins"] = [{"id": "web"}]
        if extra_body:
            kwargs["extra_body"] = extra_body
        attempts = (self.max_retries if self.max_retries is not None else s.max_retries) + 1

        def call() -> str:
            client = self.client or _client()
            resp = client.chat.completions.create(**kwargs)
            u = getattr(resp, "usage", None)
            ptd = getattr(u, "prompt_tokens_details", None)
            ctd = getattr(u, "completion_tokens_details", None)
            finish = getattr(resp.choices[0], "finish_reason", None) if resp.choices else None
            if finish == "length":
                _log.warning(
                    "%s/%s hit max_tokens (%d) — output truncated; raise MAX_OUTPUT_TOKENS",
                    self.id,
                    self.model,
                    kwargs["max_tokens"],
                )
            # Common token schema across backends (see ClaudeCodeDebater) so metrics.json sums.
            self.last_meta = {
                "model": self.model,
                "provider": getattr(resp, "provider", None),  # which upstream served it
                "finish_reason": finish,
                "input_tokens": getattr(u, "prompt_tokens", None),
                "output_tokens": getattr(u, "completion_tokens", None),
                "total_tokens": getattr(u, "total_tokens", None),
                "cached_tokens": getattr(ptd, "cached_tokens", None),  # prompt-cache read
                "cache_write_tokens": getattr(ptd, "cache_write_tokens", None),
                "reasoning_tokens": getattr(ctd, "reasoning_tokens", None),
                # OpenRouter returns per-request spend by default (no `usage.include` needed).
                "cost_usd": getattr(u, "cost", None),
            }
            content = resp.choices[0].message.content if resp.choices else None
            if not (content or "").strip():
                # A clean 200 with no content = a degraded upstream (see EmptyCompletion). Raise so
                # _retry re-calls with backoff and OpenRouter re-routes; name the provider to debug.
                raise EmptyCompletion(
                    f"{self.id}/{self.model}: empty content from upstream "
                    f"{self.last_meta.get('provider')!r} (finish={finish})"
                )
            return content

        return _retry(
            call, attempts=attempts, transient=_TRANSIENT, label=f"{self.id}/{self.model}"
        )
