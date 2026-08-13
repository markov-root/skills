"""Application assembly for the one immutable run-plan boundary (task 0040).

Authored project files, environment settings, and legacy engine values meet here exactly once.
The returned :class:`ResolvedExecution` reconstructs every execution input from its immutable
``ResolvedRunPlan``; CLI commands do not independently rebuild task, cast, phase, or policy state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from debate.aggregators import select_aggregator
from debate.engine.plan import PhaseSpec, Plan, load_plan, validate_referee_names
from debate.runtime import ResolvedRunPlan, resolve_run_plan, resolved_artifact
from debate.tasks.delphi import DelphiTask


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _known(value: Any) -> dict[str, Any]:
    return {"state": "known", "value": value, "detail": None}


def _unknown(detail: str) -> dict[str, Any]:
    return {"state": "unknown", "value": None, "detail": detail}


def _settings_values(settings: Any) -> dict[str, Any]:
    return {
        "request_timeout_s": settings.request_timeout_s,
        "claude_code_timeout_s": settings.claude_code_timeout_s,
        "codex_cli_timeout_s": settings.codex_cli_timeout_s,
        "codex_reasoning_effort": settings.codex_reasoning_effort,
        "max_retries": settings.max_retries,
        "openrouter_reasoning_effort": settings.openrouter_reasoning_effort,
        "openrouter_web_search": settings.openrouter_web_search,
        "max_concurrency": settings.max_concurrency,
        "max_output_tokens": settings.max_output_tokens,
    }


def _expanded_voice(voice: dict[str, Any], settings: Any) -> dict[str, Any]:
    resolved = dict(voice)
    backend = resolved.get("backend", "openrouter")
    resolved.setdefault("backend", backend)
    resolved.setdefault("max_retries", settings.max_retries)
    if backend == "openrouter":
        resolved.setdefault("temperature", 0.0)
        resolved.setdefault("reasoning_effort", settings.openrouter_reasoning_effort)
        resolved.setdefault("web", settings.openrouter_web_search)
        resolved.setdefault("max_output_tokens", settings.max_output_tokens)
        resolved.setdefault("timeout", settings.request_timeout_s)
        resolved.setdefault("app_title", settings.openrouter_app_title)
        resolved.setdefault("app_url", settings.openrouter_app_url)
    elif backend == "claude_code":
        resolved.setdefault("timeout", settings.claude_code_timeout_s)
    elif backend == "codex_cli":
        resolved.setdefault("timeout", settings.codex_cli_timeout_s)
        resolved.setdefault("reasoning_effort", settings.codex_reasoning_effort)
    return resolved


def _capabilities(voice: dict[str, Any], *, materials_mode: str) -> dict[str, Any]:
    backend = voice.get("backend", "openrouter")
    filesystem = ["read_materials"] if materials_mode == "disk" else []
    network = [] if backend == "fake" else ["provider_call"]
    if voice.get("web"):
        network.append("web_search")
    return {
        "information": ["task", "evidence", "prior_rounds"],
        "tools": ["filesystem_read"] if filesystem else [],
        "filesystem": filesystem,
        "network": network,
        "effects": ["model_output"],
        "max_cost_usd": None,
        "max_tokens": voice.get("max_output_tokens"),
    }


def _compatibility(voice: dict[str, Any], capabilities: dict[str, Any]) -> dict[str, Any]:
    backend = voice.get("backend", "openrouter")
    model = voice.get("model")
    return {
        "adapter_version": _known("legacy-adapter/1"),
        "protocol_version": _known("debate-engine-plan/1"),
        "harness_version": _unknown("legacy adapters do not disclose a harness version"),
        "entitlement_class": _known(
            "metered" if backend == "openrouter" else "subscription"
        ),
        "selected_model": _known(model) if model else _unknown("adapter default model"),
        "selected_provider": (
            _unknown("OpenRouter selects the serving provider at call time")
            if backend == "openrouter"
            else _known(
                "anthropic"
                if backend == "claude_code"
                else "openai"
                if backend == "codex_cli"
                else backend
            )
        ),
        "resolved_capabilities": _known(capabilities),
    }


def _role_bindings(cast: dict[str, Any], settings: Any, materials_mode: str) -> list[dict]:
    roles: list[tuple[str, dict[str, Any]]] = [
        *(('proposers', voice) for voice in cast["debaters"]),
        *((('adversaries', cast["redteam"]),) if cast.get("redteam") else ()),
        ('aggregators', cast["arbitrator"]),
    ]
    bindings = []
    for pool, authored in roles:
        voice = _expanded_voice(authored, settings)
        caps = _capabilities(voice, materials_mode=materials_mode)
        bindings.append(
            {
                "role_id": voice["id"],
                "role_pool": pool,
                "voice": voice,
                "compatibility": _compatibility(voice, caps),
                "effective_capabilities": caps,
            }
        )
    return bindings


def _parent_capabilities(bindings: list[dict]) -> dict[str, Any]:
    dimensions = ("information", "tools", "filesystem", "network", "effects")
    token_limits = [role["effective_capabilities"]["max_tokens"] for role in bindings]
    return {
        **{
            key: sorted(
                {item for role in bindings for item in role["effective_capabilities"][key]}
            )
            for key in dimensions
        },
        "max_cost_usd": None,
        "max_tokens": None if any(limit is None for limit in token_limits) else max(token_limits),
    }


def _build_task(
    protocol: str,
    spec: dict[str, Any],
    *,
    prompts_dir: Path | None = None,
    resolved_prompts: dict[str, str] | None = None,
):
    if protocol != "delphi":
        raise ValueError(f"protocol {protocol!r} is not executable")
    return DelphiTask(spec, prompts_dir=prompts_dir, resolved_prompts=resolved_prompts)


@dataclass(frozen=True)
class ResolvedExecution:
    """Executable legacy adapters reconstructed only from an immutable plan."""

    plan: ResolvedRunPlan
    task: Any
    engine_plan: Plan
    cast: dict[str, Any]

    @property
    def aggregator_id(self) -> str:
        return str(self.plan.aggregator["id"])

    @property
    def max_concurrency(self) -> int:
        return int(self.plan.policies["call"]["max_concurrency"])


def execution_from_plan(plan: ResolvedRunPlan) -> ResolvedExecution:
    """Rehydrate execution from the recorded plan, never from project files."""

    document = plan.to_dict()
    prompt_map = {item["name"]: item["content"] for item in document["prompts"]}
    spec = document["task"]["payload"]
    protocol = document["task"]["family"]
    task = _build_task(protocol, spec, resolved_prompts=prompt_map)
    call_policy = document["policies"]["call"]
    phases = [PhaseSpec(**item) for item in document["phases"]]
    engine_plan = Plan(
        phases=phases,
        min=document["budgets"]["min_phases"],
        max=document["budgets"]["max_phases"],
        token_budget=document["budgets"]["token_budget"],
        referees=call_policy["referees"],
    )
    by_pool: dict[str, list[dict[str, Any]]] = {}
    for role in document["role_bindings"]:
        by_pool.setdefault(role["role_pool"], []).append(role["voice"])
    cast = {
        "debaters": by_pool.get("proposers", []),
        "redteam": (by_pool.get("adversaries") or [None])[0],
        "arbitrator": (by_pool.get("aggregators") or [None])[0],
        "panel": document["profile"]["id"],
    }
    if cast["arbitrator"] is None:
        raise ValueError("resolved plan has no aggregator role binding")
    return ResolvedExecution(plan=plan, task=task, engine_plan=engine_plan, cast=cast)


def resolve_execution_plan(
    *,
    run_id: str,
    spec: dict[str, Any],
    protocol: str,
    cast: dict[str, Any],
    prompts_dir: Path,
    has_redteam: bool,
    settings: Any,
) -> ResolvedExecution:
    """Resolve authored inputs and defaults once, returning that same executable value."""

    plan_cast = cast if has_redteam else {**cast, "redteam": None, "adversaries": []}
    engine_plan = load_plan(spec, plan_cast, settings)
    task = _build_task(protocol, dict(spec), prompts_dir=prompts_dir)
    if referee_registry := getattr(task, "available_referees", None):
        validate_referee_names(engine_plan, referee_registry())
    aggregator_id = select_aggregator(
        spec.get("aggregator") or task.default_aggregator, task
    ).id

    execution_cast = {
        **cast,
        "redteam": cast.get("redteam") if engine_plan.has_adversary else None,
    }
    bindings = _role_bindings(
        execution_cast, settings, str(spec.get("materials_mode", "context"))
    )
    stages = list(dict.fromkeys(phase.stage for phase in engine_plan.phases))
    prompts = [resolved_artifact(stage, task.system_prompt(stage)) for stage in stages]
    schemas = [resolved_artifact(stage, task.output_schema(stage)) for stage in stages]
    task_payload = {key: value for key, value in spec.items() if key != "item_path"}
    call_policy = {
        **_settings_values(settings),
        "referees": engine_plan.referees,
    }
    policies = {
        "call": call_policy,
        "failure": {
            "voice_failure": "drop_if_quorum_remains",
            "quota_failure": "park_and_resume",
            "failed_state": "failed",
            "indeterminate_state": "unknown",
        },
        "evidence": {
            "materials_mode": task_payload.get("materials_mode", "context"),
            "corpus_version": task_payload.get("corpus_version"),
            "grounding_required": task_payload.get("materials_mode") != "search",
        },
        "cache": {"reuse": "legacy_stage_artifact", "raw_before_parse": True},
    }
    source_hashes = [
        {"source": "resolved-task", "sha256": _digest(task_payload)},
        {"source": "resolved-cast", "sha256": _digest([r["voice"] for r in bindings])},
        *(
            {"source": f"prompt:{item['name']}", "sha256": item["sha256"]}
            for item in prompts
        ),
        *(
            {"source": f"schema:{item['name']}", "sha256": item["sha256"]}
            for item in schemas
        ),
    ]
    runtime_plan = resolve_run_plan(
        run_id=run_id,
        task={
            "contract_id": "debate.task-family-input",
            "contract_version": "1.0.0",
            "family": protocol,
            "family_version": "legacy/1",
            "payload": task_payload,
        },
        profile={
            "id": cast.get("panel") or "project-cast",
            "version": "unknown",
            "resolution_state": "unknown",
        },
        phases=[phase.as_dict() for phase in engine_plan.phases],
        prompts=prompts,
        schemas=schemas,
        role_bindings=bindings,
        policies=policies,
        budgets={
            "min_phases": engine_plan.min,
            "max_phases": engine_plan.max,
            "max_attempts": None,
            "max_cost_usd": None,
            "max_tokens": settings.max_output_tokens,
            "token_budget": engine_plan.token_budget,
        },
        seeds={
            "blinding": int.from_bytes(hashlib.sha256(run_id.encode()).digest()[:8], "big"),
            "sampling": 0,
        },
        aggregator={"id": aggregator_id, "version": "legacy/1", "config": {}},
        parent_capabilities=_parent_capabilities(bindings),
        source_hashes=source_hashes,
        operation_versions=[
            {"operation": "application-resolver", "version": "1.0.0"},
            {"operation": "engine-plan-loader", "version": "legacy/1"},
            {"operation": f"{protocol}-task", "version": "legacy/1"},
        ],
        secrets=[
            {
                "name": "OPENROUTER_API_KEY",
                "present": bool(getattr(settings, "openrouter_api_key", "")),
                "reference": "env:OPENROUTER_API_KEY",
                "source": "environment",
            }
        ],
        pricing=[
            {
                "role_id": role["role_id"],
                "basis": _known("subscription")
                if role["voice"]["backend"] != "openrouter"
                else _unknown("live OpenRouter pricing is not pinned by the legacy adapter"),
                "input_unit_price": _unknown("no offline price registry"),
                "output_unit_price": _unknown("no offline price registry"),
            }
            for role in bindings
        ],
        provenance_rules={
            "/": {
                "source": "application-resolver",
                "reference": "task-0040",
                "resolution": "derived",
            },
            "/task": {
                "source": "authored-input",
                "reference": "validated project or run specification",
                "resolution": "validated",
            },
            "/role_bindings": {
                "source": "authored-input",
                "reference": "validated cast or panel",
                "resolution": "expanded",
            },
            "/policies/call": {
                "source": "settings",
                "reference": "validated startup settings",
                "resolution": "defaulted-or-overridden",
            },
        },
    )
    return execution_from_plan(runtime_plan)
