"""Agent-facing CLI adapter.

The stable surface is a debate project plus named runs under the external Debate home. The parser
wires shell arguments to command handlers; domain and persistence policy belong below this package.
`debate -h` teaches the current commands and `debate contract` describes their data boundary.
"""

from __future__ import annotations

import argparse
import os
import sys

from debate.cli.commands import (
    cmd_contract,
    cmd_cost,
    cmd_doctor,
    cmd_eval,
    cmd_materials,
    cmd_new,
    cmd_panels,
    cmd_plan,
    cmd_resume,
    cmd_run,
    cmd_show,
    cmd_status,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="debate",
        description="Cross-vendor multi-model expert debate (Delphi / IDEA).",
        epilog=(
            "examples:\n"
            "  debate doctor\n"
            "  debate panels\n"
            "  debate new steelman-x --panel <doctor-result> --item paper.md\n"
            "  debate cost steelman-x                    # dry-run, NO spend\n"
            "  debate run steelman-x                     # writes runs/<panel>/\n"
            "  debate run steelman-x --panel panel-or --run-name or\n"
            "  debate status\n"
            "  debate show steelman-x/runs/<panel>\n\n"
            "protocols: --delphi (propose/merge a SET of options; available now) · "
            "--idea (three-point numeric estimation; next build step)\n"
            "a debate is a PROJECT dir (ADR-0008): item.md + debate.yaml + cast.yaml + materials/ "
            "+ prompts/, with per-run traces under runs/<name>/. `debate new` scaffolds one; edit\n"
            "files and re-run to reproduce. A legacy run-spec YAML (ADR-0006) still works too.\n"
            "panels: defined in configs/panels.yaml — run `debate panels` to list."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="report backend/panel readiness; makes NO model calls")
    d.add_argument("--json", action="store_true", help="emit debate.doctor schema version 1.0.0")
    d.add_argument("--out", help="debates root to diagnose (overrides DEBATE_HOME for this check)")
    d.set_defaults(func=cmd_doctor)

    sub.add_parser("panels", help="list configured debate panels").set_defaults(func=cmd_panels)
    sub.add_parser(
        "contract", help="print the inputs/outputs/result.json contract (agent onboarding)"
    ).set_defaults(func=cmd_contract)

    def _add_protocol(sp):
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--delphi", action="store_true", help="set-merge protocol (default)")
        g.add_argument("--idea", action="store_true", help="three-point estimation (not wired yet)")

    n = sub.add_parser("new", help="scaffold a debate PROJECT directory (ADR-0008)")
    n.add_argument("slug", help="project name; becomes <out>/<slug>/")
    n.add_argument("--panel", help="named panel from configs/panels.yaml to seed cast.yaml")
    n.add_argument("--item", help="path to a .md to seed item.md (the debated item)")
    n.add_argument("--question", help="the debate question (default: a steelman prompt)")
    n.add_argument("--out", help="debates root (default $DEBATE_HOME or configured debate home)")
    n.add_argument("--lean", action="store_true", help="scaffold without a red-team voice")
    _add_protocol(n)
    n.set_defaults(func=cmd_new)

    m = sub.add_parser("materials", help="fetch + prep a project's research corpus (ADR-0009)")
    m.add_argument(
        "action", choices=["fetch", "prep", "all"], help="fetch sources / prep abstracts / both"
    )
    m.add_argument("target", help="a debate project dir")
    m.add_argument(
        "--backend", default="claude_code", help="prep model backend (default claude_code, free)"
    )
    m.add_argument("--model", help="prep model id (optional; backend default otherwise)")
    m.set_defaults(func=cmd_materials)

    r = sub.add_parser("run", help="run a debate: a PROJECT dir (ADR-0008) or a run-spec YAML")
    r.add_argument("target", help="a debate project dir (item.md+debate.yaml) OR a run-spec YAML")
    r.add_argument("--panel", help="named panel; overrides a project's cast.yaml for this run")
    r.add_argument(
        "--item",
        help="item file for THIS run (edited draft); reuses the project's materials/cast/prompts, "
        "snapshotted to runs/<name>/item.md. Pair with a fresh --run-name.",
    )
    r.add_argument(
        "--run-name", dest="run_name", help="project run folder runs/<name>/ (default: panel)"
    )
    r.add_argument(
        "--materials-mode",
        dest="materials_mode",
        choices=["context", "disk", "search"],
        help="override debate.yaml: context (map) | disk (CLI voices read files) | search (web)",
    )
    r.add_argument("--name", help="legacy flat folder name (default <date>-<id>); reuse to resume")
    r.add_argument("--out", help="debates root (default $DEBATE_HOME or configured debate home)")
    r.add_argument("--lean", action="store_true", help="skip the red-team/respond pass")
    r.add_argument("--json", action="store_true", help="emit the full result as JSON")
    _add_protocol(r)
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("cost", help="dry-run: planned calls + panel, makes NO model calls")
    c.add_argument("target", help="a debate project dir, a bare slug, OR a run-spec YAML")
    c.add_argument("--panel", help="named panel; overrides a project's cast.yaml for the estimate")
    c.add_argument("--out", help="debates root (default $DEBATE_HOME or configured debate home)")
    c.add_argument("--lean", action="store_true", help="cost without the red-team/respond pass")
    _add_protocol(c)
    c.set_defaults(func=cmd_cost)

    pl = sub.add_parser("plan", help="print the exact immutable execution plan; makes NO calls")
    pl.add_argument("target", help="a debate project dir, a bare slug, OR a run-spec YAML")
    pl.add_argument("--panel", help="named panel; overrides a project's cast.yaml")
    pl.add_argument("--item", help="item file for this planned run")
    pl.add_argument("--run-name", dest="run_name", help="planned project run folder name")
    pl.add_argument(
        "--materials-mode",
        dest="materials_mode",
        choices=["context", "disk", "search"],
        help="override evidence access mode for this planned run",
    )
    pl.add_argument("--name", help="planned legacy flat folder name")
    pl.add_argument("--out", help="debates root (default $DEBATE_HOME or configured debate home)")
    pl.add_argument("--lean", action="store_true", help="plan without red-team/respond")
    pl.add_argument("--json", action="store_true", help="emit the full ResolvedRunPlan JSON")
    _add_protocol(pl)
    pl.set_defaults(func=cmd_plan)

    st = sub.add_parser("status", help="list debates on disk + their stop-reason")
    st.add_argument("--out", help="debates root (default $DEBATE_HOME or configured debate home)")
    st.set_defaults(func=cmd_status)

    s = sub.add_parser("show", help="print a debate's options, aggregate, and metrics")
    s.add_argument("target", nargs="?", help="debate folder name (see `debate status`)")
    s.add_argument("--out", help="debates root (default $DEBATE_HOME or configured debate home)")
    s.set_defaults(func=cmd_show)

    rs = sub.add_parser("resume", help="continue a paused/crashed run from its cache")
    rs.add_argument(
        "target",
        nargs="?",
        help="run handle: <slug> (its sole run), <slug>/runs/<name>, or a run dir path",
    )
    rs.add_argument("--out", help="debates root (default $DEBATE_HOME or configured debate home)")
    rs.add_argument("--json", action="store_true", help="emit the full result as JSON")
    rs.set_defaults(func=cmd_resume)

    ev = sub.add_parser(
        "eval", help="protocol-validation harness: score per-profile predictions vs ground truth"
    )
    ev.add_argument("dataset", help="ground-truth dataset JSON (or 'builtin' for the demo set)")
    ev.add_argument(
        "predictions",
        help="JSON of {profile: {item_id: prediction}} — e.g. from debate runs across profiles",
    )
    ev.add_argument("--json", action="store_true", help="emit the comparison table as JSON")
    ev.set_defaults(func=cmd_eval)

    return p


def main(argv: list[str] | None = None) -> None:
    previous_umask = os.umask(0o077)
    try:
        args = build_parser().parse_args(argv)
        try:
            code = args.func(args)
        except SystemExit as exc:
            # Internal loaders historically use SystemExit for fail-fast boundary errors. Normalize
            # message-bearing exits to the CLI's input-error status instead of leaking a string as
            # the process exit code.
            if isinstance(exc.code, str):
                print(f"invalid debate configuration: {exc.code}", file=sys.stderr)
                code = 1
            else:
                raise
    finally:
        os.umask(previous_umask)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
