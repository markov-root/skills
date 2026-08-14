"""CLI resolution helpers (task-0024): map args -> debates root / project / cast / protocol / plan,
and snapshot a run. Pure wiring — no command bodies, no argparse subcommands. Imported by commands.
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

from debate._resources import copy_private_tree, resource_root
from debate.input_contracts import InputContractError, resolve_owned_path, validate_identifier


def _repo_root() -> Path:
    """Compatibility name for the immutable runtime-resource root."""
    return resource_root()


def _default_debate_home(
    *,
    platform: str | None = None,
    os_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the platform-appropriate per-user data directory using only the stdlib."""
    platform = sys.platform if platform is None else platform
    os_name = os.name if os_name is None else os_name
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if os_name == "nt":
        base = (
            Path(environ["LOCALAPPDATA"])
            if environ.get("LOCALAPPDATA")
            else home / "AppData" / "Local"
        )
        return base / "debate"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "debate"
    base = (
        Path(environ["XDG_DATA_HOME"])
        if environ.get("XDG_DATA_HOME")
        else home / ".local" / "share"
    )
    return base / "debate"


# Compatibility export for callers that imported the old constant. Resolution itself is dynamic so
# tests and embedded callers observe current environment overrides without re-importing the module.
_DEFAULT_DEBATE_HOME = _default_debate_home()


def _debates_root(args: argparse.Namespace) -> Path:
    """Where debate folders live: --out, else $DEBATE_HOME, else the platform user-data home."""
    out = getattr(args, "out", None) or os.environ.get("DEBATE_HOME")
    return Path(out).expanduser() if out else _default_debate_home()


def _debates_root_source(args: argparse.Namespace) -> str:
    """Name the precedence source that selected ``_debates_root`` for diagnostics."""
    if getattr(args, "out", None):
        return "--out"
    if os.environ.get("DEBATE_HOME"):
        return "DEBATE_HOME"
    return "platform default"


def _resolve_target(args: argparse.Namespace) -> str:
    """Map a bare project SLUG to its path under the debates root, so `run`/`cost` accept either an
    explicit path (`<home>/x` or `./x`) or just the slug (`x`) — agent-friendly now that the root is
    well-known. An explicit path or a legacy run-spec passes through unchanged."""
    from debate import project

    target = args.target
    if not project.is_project(target):
        # Only an identifier is a root-relative shorthand.  Strings containing path syntax are
        # explicit paths and never get joined to the debates root where `..` could escape it.
        try:
            validate_identifier(target, kind="project slug")
        except InputContractError:
            return target
        candidate = resolve_owned_path(_debates_root(args), target, kind="project slug")
        if project.is_project(candidate):
            return str(candidate)
    return target


# --------------------------------------------------------------------------- panels


def _protocol(args: argparse.Namespace, spec: dict) -> str:
    if getattr(args, "idea", False):
        return "idea"
    if getattr(args, "delphi", False):
        return "delphi"
    return spec.get("protocol", "delphi")


def _build_task(protocol: str, spec: dict, prompts_dir: Path):
    if protocol == "delphi":
        from debate.tasks.delphi import DelphiTask

        return DelphiTask(spec, prompts_dir=prompts_dir)
    if protocol == "idea":
        raise SystemExit(
            "protocol 'idea' (three-point estimation) is not wired yet — it is the next build step "
            "(docs/tasks/task-0002, IDEA variant). Use --delphi for now."
        )
    raise SystemExit(f"unknown protocol {protocol!r}")


def _resolve_cast(panel: str | None):
    if not panel:
        raise SystemExit("--panel is required (see `debate panels`).")
    from debate.panels import resolve_cast

    cast = resolve_cast(panel)
    for w in cast.get("warnings", []):
        print(f"  ⚠ {w}")
    return cast


def _planned_calls(n_proposers: int, has_redteam: bool) -> tuple[int, int]:
    rounds_per = 4 if has_redteam else 3  # propose, critique, revise, (respond)
    total = n_proposers * rounds_per + (1 if has_redteam else 0) + 1  # + redteam + aggregate
    return rounds_per, total


def _settings_snapshot() -> dict:
    """The engine settings that shape a debate — recorded per debate for audit/reproducibility."""
    from debate.config import get_settings

    s = get_settings()
    return {
        "reasoning_effort": s.openrouter_reasoning_effort,
        "web_search": s.openrouter_web_search,
        "max_output_tokens": s.max_output_tokens,
        "max_debate_rounds": s.max_debate_rounds,
        "token_budget": s.debate_token_budget,
        "request_timeout_s": s.request_timeout_s,
        "max_concurrency": s.max_concurrency,
    }


def _snapshot_debate(folder: Path, spec_path: str, protocol: str, cast: dict, lean: bool) -> None:
    """Make `folder` a self-contained record (ADR-0006). Only writes what is ABSENT, so a re-run
    uses the (possibly edited) snapshot rather than clobbering it — that is the reproducibility
    contract: the folder, not the original sources, is what the run executes."""
    import yaml

    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / "runspec.yaml").exists():
        shutil.copyfile(spec_path, folder / "runspec.yaml")
    if not (folder / "prompts").exists():
        copy_private_tree(_repo_root() / "prompts" / protocol, folder / "prompts")
    if not (folder / "panel.yaml").exists():
        record = {
            "protocol": protocol,
            "panel": cast.get("panel"),
            "lean": lean,
            "proposers": cast["debaters"],
            "redteam": (None if lean else cast.get("redteam")),
            "arbitrator": cast["arbitrator"],
            "settings": _settings_snapshot(),
            "created": datetime.date.today().isoformat(),
        }
        (folder / "panel.yaml").write_text(yaml.safe_dump(record, sort_keys=False))


def _apply_materials_mode(mode: str, cast: dict, spec: dict, workspace: str | None) -> str:
    """Validate the materials mode against the cast (fail fast, ADR-0010) and stamp the per-voice
    capability flags onto the cast specs: `disk` → each CLI voice reads files under `workspace`;
    `search` → each OpenRouter voice gets web search on. Records the mode on `spec` for the task."""
    from debate import project

    project.validate_materials_mode(mode, cast)
    voices = [*cast["debaters"], cast.get("redteam"), cast.get("arbitrator")]
    for v in voices:
        if not v:
            continue
        if mode == "disk" and workspace:
            v["workspace"] = workspace
        elif mode == "search" and v.get("backend") == "openrouter":
            v["web"] = True
    spec["materials_mode"] = mode
    return mode


def _preflight_resolved_backends(resolved) -> None:
    """Verify selected capabilities before any run directory or snapshot is created."""
    from debate import backends

    backends.require_backend_readiness(
        resolved.cast,
        include_redteam=resolved.engine_plan.has_adversary,
    )


def _resolve_run(args: argparse.Namespace):
    """Resolve ``debate run`` once, before creating its run directory.

    Two layouts share the engine (ADR-0008 extends ADR-0006):
    - a PROJECT dir (`item.md` + `debate.yaml`): run traces go to `<project>/runs/<run-name>/`;
      the project's `cast.yaml` is the default cast, overridable per-run with `--panel`;
    - a legacy flat run-spec YAML: one self-contained `<out>/<date>-<id>/` folder, run in place.
    """
    import yaml

    from debate import project
    from debate.application import resolve_execution_plan
    from debate.config import get_settings

    target = _resolve_target(args)
    if project.is_project(target):
        proj = Path(target)
        # --item swaps a different item file for THIS run (an edited draft, e.g. items/v0.2.0.md),
        # reusing the same materials/cast/prompts. A relative path resolves against the project.
        item_override = getattr(args, "item", None)
        if item_override and not Path(item_override).exists() and (proj / item_override).exists():
            item_override = str(proj / item_override)
        spec = project.load_project(proj, item_override=item_override)
        protocol = _protocol(args, spec)
        # --panel overrides the project's default cast.yaml for THIS run (multi-panel comparison,
        # ADR-0008); else the folder's canonical cast.yaml is authoritative.
        cast = _resolve_cast(args.panel) if args.panel else project.load_cast(proj)
        mode = getattr(args, "materials_mode", None) or spec.get("materials_mode", "context")
        _apply_materials_mode(mode, cast, spec, str(proj))
        run_name = args.run_name or args.panel or cast.get("panel") or "default"
        validate_identifier(run_name, kind="run name")
        run_dir = resolve_owned_path(proj / "runs", run_name, kind="run name")
        display = f"{proj.name}/{run_name}"
        resolved = resolve_execution_plan(
            run_id=display,
            spec=spec,
            protocol=protocol,
            cast=cast,
            prompts_dir=proj / "prompts",
            has_redteam=bool(cast.get("redteam") and not args.lean),
            settings=get_settings(),
        )
        _preflight_resolved_backends(resolved)
        run_dir.mkdir(parents=True, exist_ok=True)
        # A run is SELF-CONTAINED (ADR-0006/0008): snapshot the exact cast, item, and prompts used
        # into its own dir, so the record stays honest even if the project's inputs change later.
        snap = run_dir / "cast.yaml"
        if not snap.exists():
            snap.write_text(
                yaml.safe_dump(project._cast_doc(cast, protocol, args.lean), sort_keys=False)
            )
        item_snap = run_dir / "item.md"
        if not item_snap.exists():
            item_snap.write_text(Path(spec["item_path"]).read_text())
        prompts_dir = (
            run_dir / "prompts"
        )  # per-run prompt snapshot (the exact prompts this run used)
        if not prompts_dir.exists():
            copy_private_tree(proj / "prompts", prompts_dir)
        return proj, run_dir, resolved, display

    from debate.runspec import load_runspec

    source = load_runspec(target)  # read just for id/protocol; the SNAPSHOT is canonical
    protocol = _protocol(args, source)
    cast = _resolve_cast(args.panel)
    today = datetime.date.today().isoformat()
    folder_name = args.name or f"{today}-{source['id']}"
    if args.name:
        validate_identifier(folder_name, kind="legacy run name")
    folder = resolve_owned_path(_debates_root(args), folder_name, kind="legacy run name")
    resolved = resolve_execution_plan(
        run_id=folder.name,
        spec=source,
        protocol=protocol,
        cast=cast,
        prompts_dir=_repo_root() / "prompts" / protocol,
        has_redteam=bool(cast.get("redteam") and not args.lean),
        settings=get_settings(),
    )
    _preflight_resolved_backends(resolved)
    _snapshot_debate(folder, target, protocol, cast, args.lean)
    return folder, folder, resolved, folder.name


def _is_run_dir(p: Path) -> bool:
    """A STARTED run dir — has trace artifacts even if `result.json` is not written yet (a crash/
    quota park). This is what `resume` looks for, unlike `_find_debates` which needs a result."""
    return p.is_dir() and (
        (p / "round_status.json").exists() or (p / "result.json").exists() or any(p.glob("round-*"))
    )


def _resolve_run_dir(args: argparse.Namespace) -> Path | None:
    """Locate a (possibly half-finished) run dir for `debate resume` from a target that is an
    explicit path, a project run key (`slug/runs/name`, or `slug` for its sole run), or a legacy
    flat `name` — all under the debates root. Returns None (caller errors) if nothing resolves; on
    an ambiguous bare slug (several runs) prints the choices and returns None."""
    root = _debates_root(args)
    t = str(args.target).rstrip("/")
    candidates = [Path(t).expanduser()]
    if _safe_root_handle(t):
        candidates.append(resolve_owned_path(root, t, kind="run handle"))
    for cand in candidates:
        if _is_run_dir(cand):
            return cand
    try:
        validate_identifier(t, kind="project slug")
        proj = resolve_owned_path(root, t, kind="project slug")
    except InputContractError:
        return None
    runs_dir = proj / "runs"
    if runs_dir.is_dir():
        runs = sorted(d for d in runs_dir.iterdir() if _is_run_dir(d))
        if len(runs) == 1:
            return runs[0]
        if len(runs) > 1:
            names = ", ".join(f"{t}/runs/{d.name}" for d in runs)
            print(f"{t!r} has several runs — pick one: {names}")
    return None


def _safe_root_handle(value: str) -> bool:
    """Whether a slash-delimited CLI handle is safely root-relative."""
    path = Path(value)
    if path.is_absolute() or not path.parts:
        return False
    for part in path.parts:
        if part == "runs":
            continue
        try:
            validate_identifier(part, kind="run handle component")
        except InputContractError:
            return False
    return True


def _find_debates(root: Path) -> list[Path]:
    """Every completed run under `root`, both layouts: legacy flat `<name>/result.json` (ADR-0006)
    and project runs `<slug>/runs/<run-name>/result.json` (ADR-0008)."""
    if not root.exists():
        return []
    flat = {p.parent for p in root.glob("*/result.json")}
    projects = {p.parent for p in root.glob("*/runs/*/result.json")}
    return sorted(flat | projects)


def _debate_key(root: Path, d: Path) -> str:
    """Display/lookup handle: relative to root, so a project run reads `slug/run-name`."""
    try:
        return str(d.relative_to(root))
    except ValueError:
        return d.name


def _preflight_execution(
    spec: dict,
    cast: dict,
    *,
    protocol: str,
    prompts_dir: Path,
    has_redteam: bool,
) -> None:
    """Validate the complete task/plan/reducer contract before creating a run directory."""
    from debate.aggregators import select_aggregator
    from debate.config import get_settings
    from debate.engine.plan import load_plan, validate_referee_names

    task = _build_task(protocol, spec, prompts_dir)
    plan_cast = cast if has_redteam else {**cast, "redteam": None, "adversaries": []}
    plan = load_plan(spec, plan_cast, get_settings())
    if referee_registry := getattr(task, "available_referees", None):
        validate_referee_names(plan, referee_registry())
    select_aggregator(spec.get("aggregator") or task.default_aggregator, task)
