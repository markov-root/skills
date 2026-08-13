"""Panel registry — define a debate council once, reference it by name (ADR-0005).

A panel = proposers + an optional red-team + an arbitrator, each a debater spec (the
`build_debater` shape). Referenced by the CLI (`--panel`), job files (`run-job`), and configs
(`panel: <name>`), so a vendor's flagship is bumped in ONE place (ADR-0004). `self_exclude:
by_vendor` drops the graded provider's own vendor at scoring time (no model grades its own lab;
ADR-0012; ADR-0004); no effect on generation, which has no provider.

This module only RESOLVES a panel name into a cast dict; `build_debater` (engine) instantiates it.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from debate._resources import resource_path
from debate.backends.base import _vendor
from debate.input_contracts import InputContractError, load_panel_registry_input

_PANELS = resource_path("configs", "panels.yaml")


@cache
def _load(path: str | None = None) -> dict:
    import yaml

    p = Path(path) if path else _PANELS
    if not p.exists():
        raise SystemExit(f"panel registry not found: {p}")
    data = yaml.safe_load(p.read_text())
    try:
        return load_panel_registry_input(data, source=p).to_runtime()
    except InputContractError as exc:
        raise SystemExit(str(exc)) from exc


def panel_names(path: str | None = None) -> list[str]:
    return sorted(_load(path))


def _spec_vendor(spec: dict) -> str:
    return _vendor(spec.get("backend", "openrouter"), spec.get("model"))


def resolve_cast(name: str, *, provider: str | None = None, path: str | None = None) -> dict:
    """Resolve a panel name to a cast: {debaters, arbitrator, redteam?, warnings, panel}.

    The specs are the build_debater shape. With `provider` set and the panel's
    `self_exclude: by_vendor`, drops any PROPOSER whose vendor == provider (the self-vendor-uplift
    guard, ADR-0012). The red-team/arbitrator are flagged (not silently dropped) if they share the
    provider's vendor: replacing the arbitrator needs a per-provider choice, so we surface it
    loudly rather than guess (a known limitation, tracked for scoring self-exclusion)."""
    panels = _load(path)
    if name not in panels:
        raise SystemExit(f"unknown panel {name!r}. Known: {sorted(panels)}")
    p = panels[name]
    proposers = [dict(d) for d in p["proposers"]]
    redteam = dict(p["redteam"]) if p.get("redteam") else None
    arbitrator = dict(p["arbitrator"])
    warnings: list[str] = []

    if provider and p.get("self_exclude") == "by_vendor":
        dropped = [d["id"] for d in proposers if _spec_vendor(d) == provider]
        proposers = [d for d in proposers if _spec_vendor(d) != provider]
        if dropped:
            warnings.append(f"self-exclude({provider}): dropped proposer(s) {dropped}")
        if not proposers:
            raise SystemExit(
                f"panel {name!r} self-excludes to ZERO proposers for provider {provider!r} — "
                "add a non-{provider} voice or use a different panel."
            )
        same = "shares the graded vendor; KEPT (set a per-provider alternate, scoring limitation)."
        if redteam and _spec_vendor(redteam) == provider:
            warnings.append(f"self-exclude({provider}): red-team {redteam['id']} {same}")
        if _spec_vendor(arbitrator) == provider:
            warnings.append(f"self-exclude({provider}): arbitrator {arbitrator['id']} {same}")

    # Expand each voice's optional persona (task-0008): a bare token names a
    # prompts/personas/<token>.md file; inline text passes through. Off by default (no `persona`).
    from debate.personas import resolve_persona

    for spec in [*proposers, arbitrator, *([redteam] if redteam else [])]:
        if spec.get("persona"):
            spec["persona"] = resolve_persona(spec["persona"])

    cast: dict = {
        "debaters": proposers,
        "arbitrator": arbitrator,
        "warnings": warnings,
        "panel": name,
    }
    if redteam:
        cast["redteam"] = redteam
    return cast
