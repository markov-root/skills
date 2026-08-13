"""Backend kernel: the `Debater` seam + shared retry/quota classification + JSON extraction.

Each concrete backend (openrouter, claude_code, codex, fake) is its own module importing from here;
`build_debater` in the package `__init__` wires a spec to a backend (ADR-0004/0012/0016).
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import cache
from typing import Protocol

import openai
from openai import OpenAI

from debate.config import get_settings

_log = logging.getLogger("debate.backends")


class EmptyCompletion(RuntimeError):
    """A 200 with blank `content`. OpenRouter load-balances each model across heterogeneous
    upstream providers, and a degraded one intermittently returns an empty body (observed on
    deepseek-v4-pro mid-run: some upstreams returned '' while Novita/SiliconFlow/Fireworks/etc.
    answered the identical prompt fine). A blank completion is never useful here, so we raise —
    `_retry` then re-calls WITH BACKOFF, which lets OpenRouter re-route to a healthy provider
    (a plain no-backoff re-call kept hitting the same bad upstream during a sustained window)."""


class QuotaExceeded(RuntimeError):
    """A subscription/plan usage limit was hit on a CLI backend (`claude -p` / `codex exec`).
    Unlike a transient failure this is TERMINAL for the run but RESUMABLE: the engine parks with
    `STOP_LIMIT` and a re-run skips cached calls, so no completed work is re-charged (ADR-0016).
    Deliberately NOT in any `_TRANSIENT` tuple, so it propagates past `_retry` to the loop."""


class AtCapacity(RuntimeError):
    """A CLI backend is momentarily at capacity (codex "at capacity" / a 503), distinct from a
    plan-limit: transient, so it is retried with backoff — NOT parked (ADR-0016)."""


# Transient = worth retrying. Everything else (bad request, auth) is fatal and surfaces.
# APIResponseValidationError + a bare JSONDecodeError cover a truncated/garbled HTTP body (a
# reasoning model's stream cut mid-flight): the SDK fails to parse the envelope — a provider hiccup,
# not our bug. EmptyCompletion covers a clean 200 with no content (same cause, different symptom).
# One bad response shouldn't kill an hour-long debate (mirrors idea.py's parse retry).
_TRANSIENT = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APIResponseValidationError,
    json.JSONDecodeError,
    EmptyCompletion,
)

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

# Subscription-quota vs momentary-capacity, matched on the FULL combined stdout+stderr — the CLIs
# print a startup banner first, so scanning a truncated head would miss the marker (ADR-0016).
_QUOTA_RE = re.compile(
    r"usage limit|limit reached|quota (?:exceeded|reached)|plan limit|out of (?:credits|quota)",
    re.I,
)
_CAPACITY_RE = re.compile(r"at capacity|temporarily unavailable|overloaded|\b503\b", re.I)


def _raise_cli_failure(
    label: str, rc: int, stdout: str, stderr: str, *, allow_capacity: bool
) -> None:
    """Classify a non-zero CLI exit (ADR-0016): a plan-limit → `QuotaExceeded` (park, resumable);
    a momentary 'at capacity' → `AtCapacity` (transient retry, codex only); else a fatal
    `RuntimeError` (which task-0011 tolerates by dropping the voice). Scans the FULL combined
    output for the marker but surfaces only a truncated detail."""
    combined = f"{stdout}\n{stderr}"
    detail = (stderr.strip() or stdout.strip())[:400]
    if _QUOTA_RE.search(combined):
        raise QuotaExceeded(f"{label}: subscription usage limit hit (rc={rc}): {detail}")
    if allow_capacity and _CAPACITY_RE.search(combined):
        raise AtCapacity(f"{label}: backend at capacity (rc={rc}): {detail}")
    raise RuntimeError(f"{label} failed (rc={rc}): {detail}")


def extract_json(text: str) -> dict:
    """Parse a JSON object from a model response, tolerating ```json fences / prose."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if m := _FENCE.search(text):
        return json.loads(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"no JSON object found in response: {text[:300]!r}")


def _retry(fn: Callable[[], str], *, attempts: int, transient: tuple, label: str) -> str:
    for i in range(attempts):
        try:
            return fn()
        except transient as e:
            if i == attempts - 1:
                raise
            delay = 0.5 * 2**i + random.uniform(0, 0.5)
            _log.warning(
                "transient failure on %s (attempt %d/%d): %s; retrying in %.1fs",
                label,
                i + 1,
                attempts,
                type(e).__name__,
                delay,
            )
            time.sleep(delay)
    raise AssertionError("unreachable")


@cache
def _client() -> OpenAI:
    s = get_settings()
    return _client_for(
        s.openrouter_api_key,
        s.request_timeout_s,
        s.openrouter_app_title,
        s.openrouter_app_url,
    )


@cache
def _client_for(api_key: str, timeout_s: float, app_title: str, app_url: str) -> OpenAI:
    """Build a client from resolved non-secret policy plus the live referenced credential."""
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    headers = {"X-Title": app_title}
    if app_url:
        headers["HTTP-Referer"] = app_url
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=timeout_s,
        default_headers=headers,
    )


class Debater(Protocol):
    id: str
    backend: str

    def generate(self, system: str, user: str, *, want_json: bool = False) -> str: ...


def _vendor(backend: str, model: str | None) -> str:
    """The training-ecosystem owner of a voice — the unit that vendor-diversity is measured in
    (ADR-0011; ADR-0004). OpenRouter slugs are `<vendor>/<model>` (moonshotai, z-ai,
    deepseek, google, openai, anthropic, …); the CLI backends are pinned to a single vendor each."""
    if backend == "claude_code":
        return "anthropic"
    if backend == "codex_cli":
        return "openai"
    if backend == "openrouter" and model and "/" in model:
        return model.split("/", 1)[0]
    return backend  # fake / unknown — keep it honest rather than guess


def voice_descriptor(d: Debater) -> dict:
    """A compact, durable record of one debate voice: id + backend + pinned model + vendor.

    Written into result.json/metrics.json and promoted into the codebook so a generated option
    set is SELF-DESCRIBING — you can tell a monovendor Claude-Code run from a cross-vendor panel by
    reading the artifact, without chasing the run directory (ADR-0004 reproducibility). The
    `model` here is the *configured/pinned* id (reproducibility intent); the *actually served* model
    string is in each metrics.json call's `model` (e.g. claude reports a `[1m]` context suffix)."""
    backend = getattr(d, "backend", "?")
    model = getattr(d, "model", None)
    out = {"id": d.id, "backend": backend, "model": model, "vendor": _vendor(backend, model)}
    # task-0008: record the persona (the voice's expert lens) so a run is self-describing. Added
    # ONLY when set, so a persona-less run's provenance is byte-identical to before.
    persona = getattr(d, "persona", None)
    if persona:
        out["persona"] = persona
    return out


# The L0 trace schema version (ADR-0019/0020). Bump when the CallRecord SHAPE changes so a mixed
# dataset is sortable by capture era; L1–L4 layers (task-0031) stamp their own versions additively.
CALLRECORD_SCHEMA_VERSION = "callrecord/L0-1"


@dataclass
class CallRecord:
    """Normalized, provider-agnostic record of ONE model call (ADR-0019) — the L0 trace row.

    A SUPERSET schema with EXPLICIT NULLS: every field is ALWAYS present; data a given backend does
    not report is `None`, never a missing key. That makes cross-vendor comparison a query over a
    stable shape rather than a per-vendor special case (the capture-first principle, ADR-0020 —
    logits/version/candidate-slate are physically unrecoverable if not captured at the call). The
    engine emits one at the single `produce` chokepoint for EVERY call including cache hits, so
    nothing a run observed is silently lost (audit E-1). Higher layers — the blinding join, derived
    metrics, the label store, all-candidates + logits (L1–L4) — are task-0031 and strictly additive;
    L0 stamps `schema_version` and records what the call returned.

    `blinding_id` is null at L0 (the chokepoint has no blind map); a consumer joins on `debater_id`
    against the run's `blinding.json` (that join is the L1 step). `refused`/`request_id`/logits are
    reserved null until a backend or a higher layer fills them.
    """

    schema_version: str
    round_name: str  # storage key (unique per phase instance, e.g. "respond-2")
    stage: str  # semantic stage driving prompt/schema ("respond")
    debater_id: str
    backend: str | None
    provider: (
        str | None
    )  # upstream that actually served it (OpenRouter) — null for single-vendor CLIs
    model_id: str | None  # the CONFIGURED/pinned model (reproducibility intent)
    model_version: str | None  # the ACTUALLY-served model string (e.g. Claude's "[1m]" suffix)
    params: dict  # {temperature, reasoning_effort} — best-effort, explicit nulls
    tokens: dict  # {prompt, completion, reasoning, cached, cache_write} — explicit nulls
    cost_usd: float | None
    latency_ms: float | None
    finish_reason: str | None
    refused: bool | None
    attempt: int | None
    retries: int | None
    request_id: str | None
    blinding_id: str | None
    timestamp: float | None
    cached: bool

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_call(
        cls,
        debater: Debater,
        round_name: str,
        stage: str,
        *,
        latency_ms: float | None,
        attempt: int | None,
        cached: bool,
    ) -> CallRecord:
        """Build a full record from a debater's `last_meta` (set by the just-finished call)."""
        meta = getattr(debater, "last_meta", {}) or {}
        model_id = getattr(debater, "model", None)
        backend = getattr(debater, "backend", None)
        return cls(
            schema_version=CALLRECORD_SCHEMA_VERSION,
            round_name=round_name,
            stage=stage,
            debater_id=debater.id,
            backend=backend,
            provider=meta.get("provider") or _vendor(backend or "", model_id),
            model_id=model_id,
            model_version=meta.get("model"),
            params={
                "temperature": getattr(debater, "temperature", None),
                "reasoning_effort": getattr(debater, "reasoning_effort", None),
            },
            tokens={
                "prompt": meta.get("input_tokens"),
                "completion": meta.get("output_tokens"),
                "reasoning": meta.get("reasoning_tokens"),
                "cached": meta.get("cached_tokens"),
                "cache_write": meta.get("cache_write_tokens"),
            },
            cost_usd=meta.get("cost_usd"),
            latency_ms=latency_ms,
            finish_reason=meta.get("finish_reason"),
            refused=None,
            attempt=attempt,
            retries=(attempt - 1 if attempt is not None else None),
            request_id=meta.get("request_id"),
            blinding_id=None,
            timestamp=time.time(),
            cached=cached,
        )

    @classmethod
    def cached_stub(cls, debater: Debater, round_name: str, stage: str) -> CallRecord:
        """A cache hit whose original telemetry was never captured (a pre-L0 run resumed under L0):
        record what identity we still know, everything observed as an explicit null."""
        return cls(
            schema_version=CALLRECORD_SCHEMA_VERSION,
            round_name=round_name,
            stage=stage,
            debater_id=debater.id,
            backend=getattr(debater, "backend", None),
            provider=None,
            model_id=getattr(debater, "model", None),
            model_version=None,
            params={"temperature": None, "reasoning_effort": None},
            tokens={
                "prompt": None,
                "completion": None,
                "reasoning": None,
                "cached": None,
                "cache_write": None,
            },
            cost_usd=None,
            latency_ms=None,
            finish_reason=None,
            refused=None,
            attempt=None,
            retries=None,
            request_id=None,
            blinding_id=None,
            timestamp=None,
            cached=True,
        )
