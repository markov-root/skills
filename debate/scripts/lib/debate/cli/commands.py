"""CLI command bodies (task-0024). Each cmd_* takes parsed args and returns an int exit code; the
parser (in __init__) wires them. Resolution helpers live in cli.resolve.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from debate.cli.resolve import (
    _apply_materials_mode,
    _debate_key,
    _debates_root,
    _find_debates,
    _protocol,
    _repo_root,
    _resolve_cast,
    _resolve_run,
    _resolve_run_dir,
    _resolve_target,
)


def cmd_panels(args: argparse.Namespace) -> int:
    import yaml  # local import so --help works before `uv sync`

    from debate.input_contracts import InputContractError, load_panel_registry_input

    path = _repo_root() / "configs" / "panels.yaml"
    if not path.exists():
        print(f"no panel registry at {path}", file=sys.stderr)
        return 1
    try:
        panels = load_panel_registry_input(
            yaml.safe_load(path.read_text()) or {}, source=path
        ).to_runtime()
    except InputContractError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for name, p in panels.items():
        proposers = ", ".join(d.get("id", "?") for d in p.get("proposers", []))
        rt = " + red-team" if p.get("redteam") else ""
        desc = " ".join((p.get("description") or "").split())
        print(f"\n{name}\n  proposers: {proposers}{rt}\n  {desc}")
    return 0


# --------------------------------------------------------------------------- run / cost


def cmd_new(args: argparse.Namespace) -> int:
    """Scaffold a debate PROJECT directory (ADR-0008): item.md + debate.yaml + cast.yaml +
    materials/ + prompts/. Non-destructive — only writes what is absent."""
    from debate import project

    cast = _resolve_cast(args.panel)
    protocol = _protocol(args, {})
    root = _debates_root(args)
    from debate.input_contracts import InputContractError, resolve_owned_path, validate_identifier

    try:
        validate_identifier(args.slug, kind="project slug")
        folder = resolve_owned_path(root, args.slug, kind="project slug")
    except InputContractError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    project.scaffold_project(
        folder,
        slug=args.slug,
        protocol=protocol,
        cast=cast,
        lean=args.lean,
        question=args.question,
        item_src=Path(args.item) if args.item else None,
    )
    hint_out = f" --out {root}" if getattr(args, "out", None) else ""
    print(f"scaffolded debate project → {folder}")
    print("  edit items/v0.1.0.md, add sources in materials/, tune cast.yaml, then:")
    print(f"  debate cost {args.slug}{hint_out}   # dry-run, NO spend")
    print(f"  debate run  {args.slug}{hint_out}")
    return 0


_CONTRACT = """\
debate — data/API contract (ADR-0008/0009/0010/0024)

INPUTS: a debate PROJECT dir under the debates root (--out, $DEBATE_HOME, or the configured
compatibility default; never in the source checkout or docs/). Make one:
`debate new <slug> --panel <p> --item paper.md`:
  <project>/
    items/v0.1.0.md  versioned drafts of the debated item; `--item items/v0.2.0.md` picks one
    debate.yaml    schema_id/version, id, protocol, question, criteria, item, materials_mode;
                   optional rounds{} + aggregator; unknown keys fail before model/backend startup
    cast.yaml      schema_id/version, proposers[] + redteam + arbitrator;
                   each voice: id, backend, model?, call_policy?
                   backends: openrouter (billed), claude_code (free), codex_cli (free, GPT-5.5)
    materials/     versioned manifest.yaml (sources[]: url->path,sha256,summary);
                   see `debate materials`
    prompts/       the project's default round prompts (editable)

STRICTNESS: current authored YAML is schema version 1.0.0; unversioned alpha files migrate in
memory. Unknown nested fields, wrong versions, duplicate/unsafe IDs, unsupported backend policies,
and owner-root path escapes fail before run-directory/backend creation. Generated schemas:
assets/schemas/inputs/; use `debate contract` for the human-readable boundary.

TRIGGER (agent-friendly, all params/args):
  debate new  <slug> --panel <p> [--item f.md] [--question Q] [--out DIR]
  debate materials {fetch,prep,all} <project> [--backend codex_cli --model gpt-5.5]
  debate cost <project|spec> [--panel P]                 # resolved plan/reducer + cost, NO calls
  debate run  <project> [--panel P] [--item f.md] [--run-name R] [--materials-mode M] [--lean]
  debate show <slug>/runs/<R> [--out DIR] ; debate status [--out DIR]

OUTPUTS land in:  <project>/runs/<run-name>/    (default run-name = panel; --run-name forks a run)
    result.json       THE result (schema below)   metrics.json     tokens/cost/wall per round
    round-*/<voice>.json(+.raw.txt) per-call trace  round_status.json stop reason + dynamic rounds
    gate.json         verify_final issues          item.md,cast.yaml,prompts/ = this run's snapshot
    run.log           structured log

result.json (Delphi) fields:
    options: [ {id, statement, rationale, confidence in [0,1], ...} ]   # the generated set
    summary: str            disagreements: [str]   # cruxes the panel could not dissolve
    panel: {proposers:[{id,backend,model,vendor}], redteam, arbitrator, vendors[], monovendor}
    blinding: {voice_id: label}  gate: {ok, issues[]}  dynamic_rounds: {stop_reason, complete, ...}

RESUME: re-run the same project + run-name; completed calls are skipped (no re-charge). A DIFFERENT
item or panel needs a fresh --run-name (cache is keyed by run dir, not by content)."""


def cmd_contract(args: argparse.Namespace) -> int:
    """Print the input/output/result contract so an agent can drive the tool from `-h` alone."""
    print(_CONTRACT)
    return 0


def cmd_materials(args: argparse.Namespace) -> int:
    """Fetch + prep the research corpus for a project (ADR-0009). `fetch` downloads + pins the
    manifest's sources; `prep` writes a cached abstract per source; `all` does both."""
    from debate import materials

    proj = Path(args.target)
    if not (proj / "materials" / "manifest.yaml").exists():
        print(
            f"no materials/manifest.yaml under {proj} (scaffold with `debate new`)", file=sys.stderr
        )
        return 1
    if args.action in ("fetch", "all"):
        print(f"fetching corpus for {proj} …")
        for r in materials.fetch_sources(proj):
            extra = (
                f"{r.get('chars', 0):>7} chars" if r["status"] != "error" else r.get("error", "")
            )
            print(f"  [{r['status']:7}] {r['title'][:60]:60} {extra}")
    if args.action in ("prep", "all"):
        print(f"prepping abstracts (backend={args.backend}) …")
        for r in materials.prep_summaries(proj, backend=args.backend, model=args.model):
            extra = (
                f"{r.get('chars', 0):>5} chars"
                if r["status"] not in ("error",)
                else r.get("error", "")
            )
            print(f"  [{r['status']:10}] {str(r['title'])[:56]:56} {extra}")
    return 0


def cmd_cost(args: argparse.Namespace) -> int:
    try:
        target, resolved = _resolve_preview(args)
    except ValueError as exc:
        print(f"invalid debate configuration: {exc}", file=sys.stderr)
        return 1
    spec = resolved.plan.task["payload"]
    protocol = resolved.plan.task["family"]
    cast = resolved.cast
    plan = resolved.engine_plan
    aggregator = resolved.aggregator_id
    counts = _plan_call_counts(plan, len(cast["debaters"]))
    uses_rt = plan.has_adversary
    print("DRY RUN — no model calls made.")
    print(f"  question : {spec['id']}  (protocol={protocol})")
    print(
        f"  panel    : {args.panel or cast.get('panel') or 'cast.yaml'} — "
        f"{len(cast['debaters'])} proposer(s){' + red-team' if uses_rt else ''} + arbitrator"
    )
    print(f"  plan     : {' → '.join(counts['stages'])}")
    print(f"  aggregate: {aggregator}")
    print(f"  rounds   : {counts['fanout']} fan-out phase(s) per proposer")
    if counts["max_total"] == counts["total"]:
        print(f"  planned  : {counts['total']} successful model calls (exact)")
    else:
        print(
            f"  planned  : {counts['total']}–{counts['max_total']} successful model calls "
            "(base–safe upper bound)"
        )
        reasons = []
        if counts["dynamic_passes_max"]:
            reasons.append(
                f"up to {counts['dynamic_passes_max']} escalation pass(es), cap={plan.max}"
            )
        if counts["scrutiny_passes_max"]:
            reasons.append("optional peer scrutiny when an adversary proposes a new option")
        print(f"  variable : {'; '.join(reasons)}")
    backends = {
        s.get("backend", "openrouter")
        for s in [*cast["debaters"], cast["arbitrator"], *([cast["redteam"]] if uses_rt else [])]
    }
    print(f"  backends : {sorted(backends)}")

    # A real per-token estimate (task-0003). We have no static price table — actual $ is reported
    # by the provider after the fact (metrics.py), and OpenRouter per-model prices drift — so the
    # honest dry-run figure is the TOKEN volume (the per-token basis an agent multiplies by the
    # current rate), split by whether the voice is metered (OpenRouter) or subscription-backed
    # (claude_code/codex_cli). Input ≈ (prompt+item)/4 chars/token; output bounded by the ceiling.
    est = _estimate_tokens(
        target,
        dict(spec),
        cast,
        counts,
        max_output_tokens=int(resolved.plan.policies["call"]["max_output_tokens"]),
    )
    if est:
        token_range = (
            f"~{est['input']:,} in + ≤{est['output']:,} out"
            if est["max_calls"] == est["calls"]
            else (
                f"base ~{est['input']:,} in + ≤{est['output']:,} out; "
                f"bounded high ~{est['max_input']:,} in + ≤{est['max_output']:,} out"
            )
        )
        billed_range = (
            f"~{est['billed_input']:,} in + ≤{est['billed_output']:,} out"
            if est["max_calls"] == est["calls"]
            else (
                f"base ~{est['billed_input']:,} in + ≤{est['billed_output']:,} out; "
                f"high ~{est['max_billed_input']:,} in + ≤{est['max_billed_output']:,} out"
            )
        )
        free_range = (
            str(est["free_calls"])
            if est["max_free_calls"] == est["free_calls"]
            else f"{est['free_calls']}–{est['max_free_calls']}"
        )
        print(
            f"  tokens   : {token_range} (OpenRouter billed {billed_range}; "
            f"{free_range} call(s) subscription-backed)"
        )
    if "openrouter" in backends:
        from debate.config import get_settings

        get_settings().require_api_key()  # fail fast if the key is missing
        print(
            "  note     : OpenRouter is billed per token — multiply the billed tokens above by the "
            "model's current $/Mtok; claude_code + codex_cli are $0 marginal on the subscription."
        )
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Print the exact immutable value that execution would consume; never create a run."""
    try:
        _target, resolved = _resolve_preview(args)
    except ValueError as exc:
        print(f"invalid debate configuration: {exc}", file=sys.stderr)
        return 1
    document = resolved.plan.to_dict()
    if args.json:
        print(json.dumps(document, indent=2, sort_keys=True))
    else:
        print(f"run_id         : {resolved.plan.run_id}")
        print(f"protocol_hash  : {resolved.plan.protocol_hash}")
        print(f"execution_hash : {resolved.plan.execution_hash}")
        print(f"phases         : {' → '.join(p['stage'] for p in resolved.plan.phases)}")
        print(f"aggregator     : {resolved.aggregator_id}")
    return 0


def _resolve_preview(args: argparse.Namespace):
    """Resolve the common cost/plan authored-input adapter exactly once."""
    from debate import project
    from debate.application import resolve_execution_plan
    from debate.config import get_settings

    target = _resolve_target(args)
    if project.is_project(target):
        project_dir = Path(target)
        item_override = getattr(args, "item", None)
        if (
            item_override
            and not Path(item_override).exists()
            and (project_dir / item_override).exists()
        ):
            item_override = str(project_dir / item_override)
        spec = project.load_project(target, item_override=item_override)
        protocol = _protocol(args, spec)
        cast = _resolve_cast(args.panel) if args.panel else project.load_cast(target)
        mode = getattr(args, "materials_mode", None) or spec.get("materials_mode", "context")
        _apply_materials_mode(mode, cast, spec, str(project_dir))
        prompts_dir = project_dir / "prompts"
        run_name = (
            getattr(args, "run_name", None) or args.panel or cast.get("panel") or "default"
        )
        run_id = f"{project_dir.name}/{run_name}"
    else:
        from debate.runspec import load_runspec

        spec = load_runspec(target)
        protocol = _protocol(args, spec)
        cast = _resolve_cast(args.panel)
        prompts_dir = _repo_root() / "prompts" / protocol
        run_id = getattr(args, "name", None) or f"{datetime.date.today().isoformat()}-{spec['id']}"
    resolved = resolve_execution_plan(
        run_id=run_id,
        spec=spec,
        protocol=protocol,
        cast=cast,
        prompts_dir=prompts_dir,
        has_redteam=bool(cast.get("redteam") and not args.lean),
        settings=get_settings(),
    )
    return target, resolved


def _estimate_tokens(
    target: str,
    spec: dict,
    cast: dict,
    counts: dict,
    *,
    max_output_tokens: int | None = None,
) -> dict | None:
    """Dry-run token estimate from real input sizes: prompt files + the debated item, at ~4 chars
    per token, with output bounded by the configured ceiling. Split into billed (OpenRouter) vs
    subscription-backed voices so the OpenRouter figure is the one an agent prices. Uses the
    resolved plan's per-role call counts (`counts` from `_plan_call_counts`) so a custom `rounds:`
    block is priced honestly. Best-effort — on any read error returns None (the estimate is
    advisory)."""
    try:
        base = Path(target)
        prompt_dir = base / "prompts"
        prompt_files = sorted(prompt_dir.glob("*.md")) if prompt_dir.is_dir() else []
        avg_prompt = (
            sum(len(p.read_text(encoding="utf-8")) for p in prompt_files) / len(prompt_files)
            if prompt_files
            else 1200.0
        )
        item_path = spec.get("item_path")
        item_chars = (
            len(Path(item_path).read_text(encoding="utf-8"))
            if item_path and Path(item_path).exists()
            else 0
        )
        in_per_call = int((avg_prompt + item_chars) / 4)
        if max_output_tokens is None:
            from debate.config import get_settings

            max_output_tokens = get_settings().max_output_tokens
        out_per_call = int(max_output_tokens)

        def _calls(voice: dict, n: int) -> tuple[int, bool]:
            return n, voice.get("backend", "openrouter") == "openrouter"

        def _call_totals(fanout: int, adversary: int) -> tuple[int, int]:
            legs = [_calls(d, fanout) for d in cast["debaters"]]
            legs.append(_calls(cast["arbitrator"], counts["aggregate"]))
            if adversary and cast.get("redteam"):
                legs.append(_calls(cast["redteam"], adversary))
            return (
                sum(n for n, _ in legs),
                sum(n for n, billed in legs if billed),
            )

        total_calls, billed_calls = _call_totals(counts["fanout"], counts["adversary"])
        max_calls, max_billed_calls = _call_totals(counts["max_fanout"], counts["max_adversary"])
        return {
            "calls": total_calls,
            "max_calls": max_calls,
            "input": in_per_call * total_calls,
            "output": out_per_call * total_calls,
            "max_input": in_per_call * max_calls,
            "max_output": out_per_call * max_calls,
            "billed_input": in_per_call * billed_calls,
            "billed_output": out_per_call * billed_calls,
            "max_billed_input": in_per_call * max_billed_calls,
            "max_billed_output": out_per_call * max_billed_calls,
            "free_calls": total_calls - billed_calls,
            "max_free_calls": max_calls - max_billed_calls,
        }
    except Exception:
        return None


def _plan_for(spec: dict, cast: dict, has_rt: bool):
    """Build the debate `Plan` from debate.yaml's optional `rounds:` block (task-0017 / audit F-1),
    else the default plan. Under --lean (or a cast with no red-team) the adversary pool is emptied,
    so the plan carries no adversarial/escalation phase — and a custom `rounds:` block that DOES
    need an adversary then fails fast at load rather than driving a REDTEAM phase into a None voice.
    """
    from debate.config import get_settings
    from debate.engine.plan import load_plan

    plan_cast = cast if has_rt else {**cast, "redteam": None, "adversaries": []}
    return load_plan(spec, plan_cast, get_settings())


def _plan_call_counts(plan, n_proposers: int) -> dict:
    """Derive bounded successful-call counts from the resolved plan.

    The base is the static plan. The safe upper bound adds every escalation pass allowed by `max`
    plus one conditional proposer-scrutiny fan-out for every adversary pass. Retries remain outside
    the plan and are therefore not included.
    """
    from debate.engine import plan as P

    fanout_stages = {P.PROPOSE, P.CRITIQUE, P.REVISE, P.RESPOND}
    fanout = sum(1 for ph in plan.phases if not ph.dynamic and ph.stage in fanout_stages)
    adversary = sum(
        1 for ph in plan.phases if not ph.dynamic and ph.stage in {P.REDTEAM, P.ESCALATE}
    )
    aggregate = sum(1 for ph in plan.phases if ph.stage == P.AGGREGATE)
    # Escalation only actually runs if the phase cap leaves room beyond the static (non-dynamic,
    # non-aggregate) phases — loop.py gates the escalation loop on `phase < max_rounds`. So at the
    # default max=5 the dynamic phases are present but dead; don't advertise headroom that isn't
    # there.
    static_phases = sum(1 for ph in plan.phases if not ph.dynamic and ph.stage != P.AGGREGATE)
    escalation_active = any(ph.dynamic for ph in plan.phases) and static_phases < plan.max
    dynamic_passes_max = max(0, (plan.max - static_phases) // 2) if escalation_active else 0
    # Every adversary pass may conditionally mint a new option, which triggers one extra blinded
    # proposer fan-out for symmetric scrutiny. It is not a declared plan phase, so expose it as
    # bounded variability rather than calling the base count exact.
    scrutiny_passes_max = adversary + dynamic_passes_max
    max_fanout = fanout + dynamic_passes_max + scrutiny_passes_max
    max_adversary = adversary + dynamic_passes_max
    total = fanout * n_proposers + adversary + aggregate
    max_total = max_fanout * n_proposers + max_adversary + aggregate
    return {
        "fanout": fanout,  # calls per proposer
        "adversary": adversary,  # single red-team/escalate calls
        "aggregate": aggregate,  # single arbitrator calls (=1)
        "escalation_active": escalation_active,  # escalation can fire and add more, up to the cap
        "dynamic_passes_max": dynamic_passes_max,
        "scrutiny_passes_max": scrutiny_passes_max,
        "max_fanout": max_fanout,
        "max_adversary": max_adversary,
        "total": total,
        "max_total": max_total,
        "stages": [ph.stage for ph in plan.phases],
    }


def _validate_execution_contract(task, plan, aggregator: str | None) -> str:
    """Validate the task-dependent half of configuration before constructing a backend or spending.

    The plan loader owns structural checks. Referee names and aggregator compatibility become known
    only after the task is selected, so `cost` and `run` share this final boundary and cannot drift.
    Returns the resolved aggregator id for display/provenance.
    """
    from debate.aggregators import select_aggregator
    from debate.engine.plan import validate_referee_names

    if aggregator is not None and not isinstance(aggregator, str):
        raise ValueError(f"`aggregator` must be a string, got {aggregator!r}")
    referee_registry = getattr(task, "available_referees", None)
    if referee_registry is not None:
        validate_referee_names(plan, referee_registry())
    return select_aggregator(aggregator or task.default_aggregator, task).id


def cmd_run(args: argparse.Namespace) -> int:
    from debate.runtime import ResolutionError, write_resolved_run_plan

    try:
        _folder, run_dir, resolved, display = _resolve_run(args)
    except ValueError as exc:
        print(f"invalid debate configuration: {exc}", file=sys.stderr)
        return 1

    # Materials boundary (task-0027; ADR-0015): verify the pinned corpus BEFORE spending any calls —
    # a drifted `content_sha256` fails fast rather than silently arguing over stale text. Skipped in
    # `search` mode (nothing is pinned there) and when the project has no materials.
    spec = resolved.plan.task["payload"]
    if _folder is not None and spec.get("materials_mode") != "search":
        from debate.materials_contract import MaterialsError, verify_corpus

        try:
            verify_corpus(_folder)
        except MaterialsError as e:
            print(f"materials contract violation: {e}", file=sys.stderr)
            return 1

    try:
        write_resolved_run_plan(resolved.plan, run_dir)
    except ResolutionError as exc:
        print(f"immutable run-plan conflict: {exc}", file=sys.stderr)
        return 1
    return _execute_resolved(
        args,
        run_dir=run_dir,
        display=display,
        resolved=resolved,
        fresh=not (run_dir / "result.json").exists(),
    )


def _execute_resolved(args, *, run_dir: Path, display: str, resolved, fresh: bool) -> int:
    """Execute only values carried by ``resolved``; project files are out of scope below here."""
    from debate.backends import QuotaExceeded, build_debater
    from debate.config import get_settings
    from debate.engine.loop import run_debate

    spec = resolved.plan.task["payload"]
    protocol = resolved.plan.task["family"]
    cast = resolved.cast
    plan = resolved.engine_plan
    uses_rt = plan.has_adversary
    voice_specs = [
        *cast["debaters"],
        cast["arbitrator"],
        *([cast["redteam"]] if uses_rt else []),
    ]
    if any(s.get("backend", "openrouter") == "openrouter" for s in voice_specs):
        get_settings().require_api_key()
    debaters = [build_debater(s) for s in cast["debaters"]]
    arbitrator = build_debater(cast["arbitrator"])
    redteam = build_debater(cast["redteam"]) if uses_rt else None
    print(f"{'starting' if fresh else 'resuming'} debate → {run_dir}")
    try:
        result = run_debate(
            resolved.task,
            debaters,
            arbitrator,
            debate_name=run_dir.name,
            redteam=redteam,
            run_dir=str(run_dir),
            plan=plan,
            aggregator=resolved.aggregator_id,
            max_concurrency=resolved.max_concurrency,
        )
    except QuotaExceeded as exc:
        print(f"\nPAUSED on usage limit: {exc}")
        print(f"  resume: re-run the same command once quota resets — cached calls under {run_dir}")
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    opts = result.get("options", [])
    print(f"\n{spec['id']} [{protocol}] → {display}")
    print(f"  {len(opts)} option(s); gate ok={result.get('gate', {}).get('ok')}")
    for option in opts:
        print(f"   - {option.get('id')}: {str(option.get('statement', ''))[:100]}")
    if result.get("disagreements"):
        print(f"  unresolved: {result['disagreements']}")
    print(f"  traces: {run_dir}")
    return 0


# --------------------------------------------------------------------------- eval (task-0026)


def cmd_eval(args: argparse.Namespace) -> int:
    """Score per-profile predictions against a ground-truth dataset → the comparison table +
    contamination (novel-vs-published) split. Predictions are supplied (`{profile: {id: pred}}`),
    so this runs with NO models — the live sweep that produces them across profiles is separate
    (task-0026, agent+human). `dataset` = a JSON file or 'builtin' for the demo arithmetic set."""
    from debate.eval import harness
    from debate.eval.datasets import builtin_arithmetic, load_dataset

    dataset = builtin_arithmetic() if args.dataset == "builtin" else load_dataset(args.dataset)
    preds = json.loads(Path(args.predictions).read_text())
    table = harness.compare(dataset, preds)
    split = harness.contamination_split(dataset, preds)
    if args.json:
        print(json.dumps({"compare": table, "contamination": split}, indent=2))
        return 0
    print(f"{dataset.name}: {table['n_items']} items, {len(preds)} profile(s)")
    for name, m in table["profiles"].items():
        head = {k: v for k, v in m.items() if k not in ("binary_rates", "coverage_risk")}
        print(f"  {name:16} {head}")
    print(f"contamination: {split['n_published']} published / {split['n_novel']} novel")
    return 0


# --------------------------------------------------------------------------- status / show


def cmd_status(args: argparse.Namespace) -> int:
    root = _debates_root(args)
    debates = _find_debates(root)
    if not debates:
        print(f"no completed debates under {root}/")
        return 0
    print(f"debates under {root}/:")
    for d in debates:
        result = json.loads((d / "result.json").read_text())
        dyn = result.get("dynamic_rounds", {})
        n_opts = len(result.get("options", []))
        print(
            f"  {_debate_key(root, d):48} {n_opts:>3} opt  stop={dyn.get('stop_reason', '?')}  "
            f"gate={result.get('gate', {}).get('ok')}"
        )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    if not args.target:
        print("usage: debate show <debate> [--out DIR]", file=sys.stderr)
        return 2
    root = _debates_root(args)
    t = args.target.rstrip("/")
    matches = [d for d in _find_debates(root) if _debate_key(root, d) == t or d.name == t]
    if not matches:
        print(f"no debate {args.target!r} under {root}/ (try `debate status`)", file=sys.stderr)
        return 1
    d = matches[0]
    result = json.loads((d / "result.json").read_text())
    print(f"=== {_debate_key(root, d)} ===  ({d})")
    panel = result.get("panel", {})
    print(
        f"panel: {[p['id'] for p in panel.get('proposers', [])]} "
        f"(vendors={panel.get('vendors')}, monovendor={panel.get('monovendor')})"
    )
    if dropped := panel.get("dropped"):
        # A degraded run is visibly degraded (task-0011): name the voices dropped mid-run.
        print(f"  DROPPED voices (failed mid-run): {dropped}")
    print(
        f"gate: {result.get('gate', {}).get('ok')}  stop: "
        f"{result.get('dynamic_rounds', {}).get('stop_reason')}"
    )
    for o in result.get("options", []):
        print(f"  - {o.get('id')}: {str(o.get('statement', ''))[:110]}")
    if result.get("disagreements"):
        print(f"  unresolved: {result['disagreements']}")
    metrics_f = d / "metrics.json"
    if metrics_f.exists():
        s = json.loads(metrics_f.read_text()).get("summary", {})
        print(
            f"calls: {s.get('n_calls')} live ({s.get('n_cached')} cached); "
            f"${s.get('cost_usd', 0):.4f} real (+${s.get('notional_cost_usd', 0):.4f} notional)"
        )
    files = sorted(p.name for p in d.iterdir())
    print(f"files: {files}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Continue a paused/crashed/half-finished debate from a single run handle (task-0003). Unlike
    re-typing the full `debate run …`, resume needs only the run: it locates the run dir (even one
    with no `result.json` yet), recovers the project + run-name from the path, and re-drives the
    same pipeline — completed calls are read from the run dir's cache, so nothing is re-charged
    (ADR-0005/0016). A different item/panel still needs a fresh `debate run --run-name`."""
    if not getattr(args, "target", None):
        print("usage: debate resume <slug | slug/runs/name | run-dir> [--out DIR]", file=sys.stderr)
        return 2
    run_dir = _resolve_run_dir(args)
    if run_dir is None:
        print(
            f"no resumable run for {args.target!r} (try `debate status`, or pass slug/runs/name)",
            file=sys.stderr,
        )
        return 1

    from debate.application import execution_from_plan
    from debate.runtime import PLAN_FILENAME, ResolutionError, load_resolved_run_plan

    if (run_dir / PLAN_FILENAME).exists():
        try:
            resolved = execution_from_plan(load_resolved_run_plan(run_dir))
        except (ResolutionError, ValueError) as exc:
            print(f"invalid immutable run plan: {exc}", file=sys.stderr)
            return 1
        try:
            display = str(run_dir.relative_to(_debates_root(args)))
        except ValueError:
            display = run_dir.name
        print(f"resuming {display} from immutable plan → {run_dir}")
        return _execute_resolved(
            args, run_dir=run_dir, display=display, resolved=resolved, fresh=False
        )

    if run_dir.parent.name == "runs":  # project layout: <proj>/runs/<run-name>/
        project_dir = run_dir.parent.parent
        # Honour the run's OWN snapshot for the one flag that changes the call graph: a run
        # recorded without a red-team resumes lean, so we never drive a REDTEAM phase it lacked.
        lean = _snapshot_is_lean(run_dir)
        ns = argparse.Namespace(
            target=str(project_dir),
            run_name=run_dir.name,
            panel=None,  # the project's own cast.yaml is authoritative on resume
            item=None,
            lean=lean,
            materials_mode=None,
            json=getattr(args, "json", False),
            out=getattr(args, "out", None),
            delphi=False,
            idea=False,
            name=None,
        )
        print(f"resuming {project_dir.name}/{run_dir.name} from cache → {run_dir}")
        return cmd_run(ns)

    # Legacy flat folder (ADR-0006): re-drive its own snapshot in place.
    import yaml

    panel_f = run_dir / "panel.yaml"
    spec_f = run_dir / "runspec.yaml"
    if not (panel_f.exists() and spec_f.exists()):
        print(
            f"{run_dir} is not a self-contained run (no panel.yaml/runspec.yaml)", file=sys.stderr
        )
        return 1
    panel = (yaml.safe_load(panel_f.read_text()) or {}).get("panel")
    ns = argparse.Namespace(
        target=str(spec_f),
        name=run_dir.name,
        run_name=None,
        panel=panel,
        item=None,
        lean=(yaml.safe_load(panel_f.read_text()) or {}).get("lean", False),
        materials_mode=None,
        json=getattr(args, "json", False),
        out=str(run_dir.parent),
        delphi=False,
        idea=False,
    )
    print(f"resuming {run_dir.name} from cache → {run_dir}")
    return cmd_run(ns)


def _snapshot_is_lean(run_dir: Path) -> bool:
    """A project run's snapshot cast.yaml records whether it ran with a red-team; resume respects it
    so the resumed call graph matches the original (no red-team snapshot ⇒ resume lean)."""
    import yaml

    snap = run_dir / "cast.yaml"
    if not snap.exists():
        return False
    doc = yaml.safe_load(snap.read_text()) or {}
    return doc.get("redteam") in (None, {}, [])


# --------------------------------------------------------------------------- parser
