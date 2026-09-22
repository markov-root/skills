"""One CLI registry; human output and a versioned JSON envelope."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .artifacts import Refusal, artifact
from .environment import Environment, atomic_json
from .inventory import compact, inventory
from .launchers import cli_apply, cli_plan, health
from .sync import apply, plan, remove

COMMANDS = {
    "list": "Show installed skill content and harness exposure",
    "diff": "Compare an exact source artifact with installed copies",
    "sync": "Preview or apply a source-to-install synchronization",
    "doctor": "Report observed installation and owned PATH health",
    "cli": "Preview or apply declared optional PATH launchers",
    "remove": "Preview or remove unchanged managed installations",
    "finish": "Validate, plan/sync, and run an installed-artifact smoke command",
}


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--version", action="version", version="skill-manager 0.1.0")
    commands = root.add_subparsers(dest="command", required=True)
    for name, help_text in COMMANDS.items():
        p = commands.add_parser(name, help=help_text)
        p.add_argument("--json", action="store_true")
        p.add_argument("--scope", choices=["global", "project"], default="global")
        p.add_argument("--project-root", type=Path, default=Path.cwd())
        p.add_argument("--state-dir", type=Path)
        p.add_argument(
            "--skills-command",
            help="JSON argv for the upstream CLI; default pins skills@1.5.23",
        )
        if name in ("list", "doctor", "remove"):
            p.add_argument("name", nargs=None if name == "remove" else "?")
        if name in ("diff", "sync", "finish", "cli"):
            p.add_argument("source", type=Path, nargs="?" if name == "sync" else None)
        if name in ("sync", "finish", "cli", "remove"):
            p.add_argument(
                "--apply", action="store_true", help="perform the reviewed operation"
            )
        if name in ("diff", "sync", "finish"):
            p.add_argument(
                "--accept-installed",
                action="store_true",
                help="explicitly replace differing installed files after reviewing them",
            )
        if name == "diff":
            p.add_argument(
                "--text",
                action="store_true",
                help="include bounded unified diffs for UTF-8 text files",
            )
        if name in ("sync", "finish"):
            p.add_argument(
                "--plan",
                type=Path,
                help="write preview here, or read it with sync --apply",
            )
        if name == "cli":
            p.add_argument("--bin-dir", type=Path, default=Path.home() / ".local/bin")
            p.add_argument(
                "--adopt-existing",
                action="store_true",
                help="adopt an exact target symlink or the exact legacy portfolio uv wrapper",
            )
            p.add_argument("--remove", action="store_true")
        if name == "finish":
            p.add_argument(
                "--validate-command",
                required=True,
                help="JSON argv; {source} expands to artifact path",
            )
            p.add_argument(
                "--smoke-command",
                required=True,
                help="JSON argv; {installed} expands to installed artifact",
            )
    return root


def argv_command(encoded, replacements):
    argv = json.loads(encoded)
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(s, str) for s in argv)
    ):
        raise Refusal("check command must be a nonempty JSON argv")
    return [replace_tokens(s, replacements) for s in argv]


def replace_tokens(text, replacements):
    for token, value in replacements.items():
        text = text.replace("{" + token + "}", str(value))
    return text


def finish(env, args):
    src = artifact(args.source)
    validation = argv_command(args.validate_command, {"source": src["path"]})
    checked = subprocess.run(
        validation, stdout=sys.stderr, stderr=sys.stderr, check=False
    )
    if checked.returncode:
        return {
            "status": "failed",
            "validation": checked.returncode,
            "sync": "not-run",
            "smoke": "not-run",
        }, 1
    if artifact(args.source)["hash"] != src["hash"]:
        raise Refusal(
            "validation changed the source artifact; review and validate it again"
        )
    current = plan(env, args.source, args.accept_installed)
    if args.plan:
        atomic_json(args.plan, current)
    if not args.apply:
        return {
            "status": "planned",
            "validation": 0,
            "plan": current,
            "smoke": "not-run",
        }, 3 if current["conflicts"] else 0
    synced = apply(env, current)
    if synced["status"] == "partial":
        return {
            "status": "partial",
            "validation": 0,
            "sync": synced,
            "smoke": "not-run",
        }, 1
    installed = env.shared / src["name"]
    smoke = argv_command(args.smoke_command, {"installed": installed})
    result = subprocess.run(
        smoke,
        env=dict(os.environ, INSTALL_DIR=str(installed), SKILL_NAME=src["name"]),
        stdout=sys.stderr,
        stderr=sys.stderr,
        check=False,
    )
    installed_stable = artifact(installed)["hash"] == src["hash"]
    paths = [p for p in health(env) if p["skill"] == src["name"]]
    success = (
        result.returncode == 0
        and installed_stable
        and all(p["status"] == "healthy" for p in paths)
    )
    return {
        "status": "passed" if success else "failed",
        "validation": 0,
        "sync": synced,
        "smoke": result.returncode,
        "path_health": paths,
        "installed_stable_after_smoke": installed_stable,
        "feedback": "optional: run skill-feedback onboard " + src["name"],
        "session_reload": "not verified; restart or reload the harness as required",
    }, 0 if success else 1


def execute(args):
    command = json.loads(args.skills_command) if args.skills_command else None
    env = Environment(args.scope, args.project_root, args.state_dir, command)
    if args.command in ("list", "doctor"):
        result = compact(inventory(env, args.name))
        bad = bool(result["unavailable_roots"]) or any(
            s["divergent"]
            or any(
                h["status"] in ("broken", "ambiguous") for h in s["harnesses"].values()
            )
            for s in result["skills"]
        )
        if args.command == "doctor":
            result["path_health"] = health(env)
            result["upstream_executable"] = shutil.which(env.command[0])
            result["last_operation"] = (
                json.loads((env.state_dir / "last-operation.json").read_text())
                if (env.state_dir / "last-operation.json").exists()
                else None
            )
            result["source_drift"] = []
            for name, record in env.state()["skills"].items():
                if args.name and args.name != name:
                    continue
                try:
                    current = plan(env, record["source"]["path"])
                    status = (
                        "conflict"
                        if current["conflicts"]
                        else "stale"
                        if any(c["changes"] for c in current["comparisons"])
                        else "current"
                    )
                except (OSError, ValueError) as exc:
                    status = "unavailable: " + str(exc)
                result["source_drift"].append({"name": name, "status": status})
            bad |= (
                any(x["status"] != "healthy" for x in result["path_health"])
                or any(x["status"] != "current" for x in result["source_drift"])
                or result["upstream_executable"] is None
                or (result["last_operation"] or {}).get("status")
                in ("partial", "in-progress")
            )
        result["status"] = "issues" if bad else "observed"
        return result, 1 if bad else 0
    if args.command == "finish":
        return finish(env, args)
    if args.command == "remove":
        result = remove(env, args.name, args.apply)
        return result, 1 if result["status"] == "partial" else 0
    if args.command == "cli":
        result = cli_plan(
            env, args.source, args.bin_dir, args.adopt_existing, args.remove
        )
        if args.apply:
            result = cli_apply(env, result)
        return result, 3 if result["status"] == "conflict" else 0
    if args.command == "sync" and args.apply and args.plan:
        if args.source or args.accept_installed:
            raise Refusal("apply a saved plan without a source or resolution flags")
        result = apply(env, json.loads(args.plan.read_text()))
        return result, 1 if result["status"] == "partial" else 0
    if args.source is None:
        raise Refusal("provide an exact artifact source or a saved sync plan")
    result = plan(env, args.source, args.accept_installed)
    if args.command == "diff" and args.text:
        from .textdiff import text_diffs

        result["text_diffs"] = text_diffs(result)
    if args.command == "sync" and args.plan:
        atomic_json(args.plan, result)
    if args.command == "sync" and args.apply:
        result = apply(env, result)
        return result, 1 if result["status"] == "partial" else 0
    code = (
        3
        if result["conflicts"]
        else 1
        if args.command == "diff" and any(c["changes"] for c in result["comparisons"])
        else 0
    )
    return result, code


def human(result):
    print("skill-manager:", result.get("status", result.get("kind", "result")))
    if "skills" in result:
        print(f"{'Skill':30} {'Claude':12} {'Codex':12} {'OpenCode':12} Source")
        for s in result["skills"]:
            states = [
                s["harnesses"][h]["status"]
                for h in ("claude-code", "codex", "opencode")
            ]
            source = (s["source"] or {}).get("path", "unknown")
            print(
                f"{s['name']:30} {states[0]:12} {states[1]:12} {states[2]:12} {source}"
            )
        for obs in result.get("observations", []):
            if obs["status"] == "present":
                print(
                    f"  {obs.get('name')}: version={obs.get('version') or 'unknown'} hash={obs['hash'][:12]} {obs['path']}"
                )
        for key in ("unavailable_roots", "path_health", "source_drift"):
            if result.get(key):
                print(key + ": " + json.dumps(result[key], ensure_ascii=False))
    elif "comparisons" in result:
        print("Source:", result["source"]["path"])
        for c in result["comparisons"]:
            print(c["classification"] + ": " + c["path"])
            for change in c["changes"]:
                print(f"  {change['change']:8} {change['path']}")
        for c in result["conflicts"]:
            print("CONFLICT:", c["path"], c["reason"])
        for entry in result.get("text_diffs", []):
            print(entry.get("diff", entry.get("note", "")))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result, code = execute(args)
    except (Refusal, OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        result, code = {"status": "refused", "error": str(exc)}, 3
    except KeyboardInterrupt:
        result, code = (
            {
                "status": "interrupted",
                "next": "inspect doctor and last-operation receipt before retrying",
            },
            130,
        )
    result = {"schema_version": 1, "command": args.command, **result}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        human(result)
    return code
