#!/usr/bin/env python3
"""`visuals new` — scaffold a new graphic's contract wiring, and nothing else.

Task 0006. Emits, per ADR 0004: a `BRIEF.md` stub (a form, not an example), a
source master whose preamble resolves the project theme and shared assets at
the correct relative depth for where the file actually sits, a frame manifest
in the documented format, and a source-credit element — on a deliberately
empty canvas. No layout, no type scale, no colour choice, no composition: a
scaffold that produces a designed starting point is a defect in this skill.

Refusals (never silent, never partial):
- outside an adopted project (no visuals.toml resolves): exit 3 — the
  scaffold cannot wire profiles or theme without the contract layer;
- target directory already exists without --force: exit 2, name it;
- theme unresolvable: exit 3, before anything is written.

`--force` never overwrites ANY existing file — it fills only the absent ones
and reports the skips. "Force" conventionally implies overwrite; here it
deliberately does not, so an edited BRIEF.md or source master is untouchable
by construction (criterion 6).

The project-level shared stylesheet `visuals/_shared/theme.css` is derived
from the project's own theme reference (never hand-written: F7) and is
reported as its own action — written (first visual in this project) or
reused — because a per-visual command writing outside the directory it was
asked to create must be visible, not a surprise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # capability domain (task 0003); never a handler-to-handler import
import scaffold  # this command's capability domain (task 0006)
import scaffold_style  # explicit project-owned style wiring (task 0021)


def main(argv: list[str]) -> int:
    """Handler entry point. `argv` is this command's own arguments, without
    the program name or the command name (the dispatcher owns no flags)."""
    parser = argparse.ArgumentParser(
        prog="visuals new", add_help=False, description="Scaffold a new graphic."
    )
    parser.add_argument("kind", help="artifact kind: presentation | poster | figure | diagram")
    parser.add_argument(
        "slug",
        help="visual name under the project's visuals/ directory; nested families "
        "use a path ('family/demo') and get the correct relative depth",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="scaffold into an existing directory, writing ONLY the files that "
        "are absent — never overwrites an existing file (an edited BRIEF.md "
        "or source master is untouchable); skips are reported",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit a structured report of the scaffold"
    )
    parser.add_argument(
        "--style", help="use this project's declared scaffold wiring for a named style"
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2  # usage

    cwd = Path.cwd()
    config_resolved = config.resolve_config(cwd)
    if config_resolved is None:
        message = (
            f"refusing to scaffold: no {config.CONFIG_NAME} resolves from {cwd} — "
            "run 'visuals init' first; a scaffold without the project contract "
            "layer cannot wire the theme or the canvas profiles"
        )
        if args.json:
            print(json.dumps({"command": "new", "written": [], "mode": "refused",
                              "message": message}, indent=2))
        else:
            print(message, file=sys.stderr)
        return 3

    try:
        plan = (
            scaffold_style.plan_scaffold_style(
                config_resolved, args.kind, args.slug, args.force, args.style
            )
            if args.style is not None else
            scaffold.plan_scaffold(config_resolved, args.kind, args.slug, args.force)
        )
    except scaffold.ScaffoldRefused as exc:
        if args.json:
            print(json.dumps({"command": "new", "written": [], "mode": "refused",
                              "message": str(exc)}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code

    applied = scaffold.apply_plan(plan)

    rel = lambda p: os.path.relpath(p, config_resolved.root)  # noqa: E731
    if args.json:
        print(
            json.dumps(
                {
                    "command": "new",
                    "kind": args.kind,
                    **({"style": args.style} if args.style is not None else {}),
                    "visual_dir": str(applied.visual_dir),
                    "written": [str(p) for p in applied.written],
                    "skipped": [str(p) for p in applied.skipped],
                    "canvas_profile": {
                        "name": applied.profile.name,
                        "basis": applied.profile.basis,
                    },
                    "shared_theme": None if args.style is not None else (
                        {"path": str(applied.theme.path), "status": applied.theme.status,
                         "derived_from": applied.theme.derived_from}
                        if applied.theme else
                        {"status": "reused", "path": str(
                            config_resolved.root / scaffold.VISUALS_DIR
                            / scaffold.SHARED_DIR / scaffold.THEME_CSS_NAME)}
                    ),
                },
                indent=2,
            )
        )
    else:
        print(f"scaffolded {rel(applied.visual_dir)}/ (kind {args.kind})")
        for path in applied.written:
            note = ""
            if applied.theme is not None and path == applied.theme.path:
                note = (
                    f" — project shared stylesheet, derived from theme "
                    f"'{applied.theme.derived_from}' (first visual in this project)"
                )
            print(f"  wrote {rel(path)}{note}")
        for path in applied.skipped:
            print(f"  skipped {rel(path)} (exists; never overwritten)")
        basis_note = (
            "project style declaration"
            if applied.profile.basis == "style-declaration" else
            "matches this kind's name"
            if applied.profile.basis == "name-match" else
            "project default (no profile is named for this kind)"
        )
        print(
            f"  canvas profile: {applied.profile.name} ({basis_note}; "
            "recorded in BRIEF.md)"
        )
        print(f"next: visuals render {args.slug}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
