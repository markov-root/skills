"""`present doctor` — core prerequisites, neighbour capabilities, and the repository in view.

Core failures exit 1. A missing neighbour or optional tool is a `capability_unavailable` warning
(repairable, with the install step) and never a pass (portfolio ADR 0004 D1).
"""

from __future__ import annotations

import os
import shutil
import sys
from importlib import metadata
from pathlib import Path

from .. import SKILL_ROOT, STANDARDS, __version__, feedback, formats, schemas
from ..console import Effects, Result, leaf
from ..repo import MARKER, find_repo

NEIGHBOURS = {
    # name: (relative launcher inside the skill folder, what present uses it for, install hint)
    "visuals": (
        "scripts/visuals",
        "visual render/publish and visual pins (task 0009)",
        "npx skills add ~/Skills --full-depth --skill visuals --agent '*'",
    ),
    "writing": (
        "scripts/revoice_check.py",
        "lossless re-voice check in `script check` (writing task 0041)",
        "npx skills add ~/Skills --full-depth --skill writing --agent '*' (writing >= 0.10.0)",
    ),
}


def skill_dirs() -> list[Path]:
    """Where neighbour skills may live: an explicit override, else beside this skill and in harness dirs."""
    override = os.environ.get("PRESENT_SKILL_DIRS")
    if override is not None:
        return [Path(p) for p in override.split(os.pathsep) if p]
    here = SKILL_ROOT
    # monorepo layout: <repo>/<name>/public  → siblings are <repo>/*/public
    dirs = [here.parent.parent] if here.name == "public" else [here.parent]
    home = Path.home()
    dirs += [
        home / ".agents/skills",
        home / ".claude/skills",
        home / ".codex/skills",
        home / ".config/opencode/skills",
        home / ".pi/agent/skills",
    ]
    return dirs


def find_neighbour(name: str, rel: str) -> Path | None:
    for base in skill_dirs():
        for cand in (base / name / rel, base / name / "public" / rel):
            if cand.is_file():
                return cand
    return None


def _check(name, ok, detail, **extra):
    return {"name": name, "ok": ok, "detail": detail, **extra}


@leaf(
    "doctor",
    summary="check prerequisites, neighbour skills and the repository in view",
    effects=Effects(
        description="Reads the environment, the launcher, `skill-feedback collection --json` "
        "(read-only) and, if found, presentations.toml."
    ),
    task="0003",
)
def doctor(ns, res: Result) -> Result:
    checks = []
    py_ok = sys.version_info >= (3, 11)
    checks.append(_check("python", py_ok, sys.version.split()[0], required=">=3.11"))
    for dist in (
        "pyyaml",
        "jsonschema",
        "python-pptx",
        "pillow",
    ):  # deck engine needs the last two
        try:
            checks.append(_check(dist, True, metadata.version(dist)))
        except metadata.PackageNotFoundError:
            checks.append(_check(dist, False, "not installed"))
    bad = []
    for name in schemas.NAMES:
        try:
            schemas.validator(name)
        except Exception as exc:  # a broken schema is a broken artifact
            bad.append(f"{name}: {exc}")
    checks.append(
        _check(
            "schemas",
            not bad,
            f"{len(schemas.NAMES) - len(bad)}/{len(schemas.NAMES)} load",
            failures=bad,
        )
    )
    core_ok = all(c["ok"] for c in checks)

    capabilities = []
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    capabilities.append(
        _check(
            "libreoffice",
            bool(soffice),
            soffice or "not on PATH",
            used_for="deck PDF and contact sheet (task 0008)",
        )
    )
    if not soffice:
        res.warn(
            "capability_unavailable",
            "LibreOffice not found; deck rendering will be unavailable.",
            next="sudo apt install libreoffice-impress",
        )
    for tool, (hint, used_for) in {
        "pdftoppm": (
            "sudo apt install poppler-utils",
            "deck contact sheets and galleries",
        ),
        "montage": ("sudo apt install imagemagick", "contact sheets"),
    }.items():
        path = shutil.which(tool)
        capabilities.append(
            _check(tool, bool(path), path or "not on PATH", used_for=used_for)
        )
        if not path:
            res.warn(
                "capability_unavailable",
                f"{tool} not found; {used_for} will be unavailable.",
                next=hint,
            )
    eng = shutil.which("engineering")
    capabilities.append(
        _check(
            "engineering",
            bool(eng),
            eng or "not on PATH",
            used_for="record allocation in `talk new` (task 0004)",
        )
    )
    if not eng:
        res.warn(
            "capability_unavailable",
            "software-engineering `engineering` CLI not found; `talk new` will "
            "scaffold records without allocating them.",
            next="install the software-engineering skill",
        )
    for name, (rel, used_for, hint) in NEIGHBOURS.items():
        path = find_neighbour(name, rel)
        capabilities.append(
            _check(
                name,
                path is not None,
                str(path) if path else "not found",
                used_for=used_for,
            )
        )
        if path is None:
            res.warn(
                "capability_unavailable",
                f"{name}: {rel} not found; {used_for} is unavailable.",
                next=hint,
            )
    from ..references import (  # evidence CLIs (task 0022; canonical grammar task 0024)
        find_cli,
        find_datasets_cli,
        install_hint,
    )

    research_path = find_cli("research")
    capabilities.append(
        _check(
            "research",
            research_path is not None,
            str(research_path) if research_path else "not found",
            used_for="resolving literature: references in `claims check|pin`",
        )
    )
    if research_path is None:
        res.warn(
            "capability_unavailable",
            "research CLI not found; resolving literature: references is unavailable.",
            next=install_hint("research"),
        )
    datasets_path, datasets_prefix = find_datasets_cli()
    via = (
        "the `research` CLI (`research dataset …`)" if datasets_prefix
        else "the standalone `datasets` binary"
    )
    capabilities.append(
        _check(
            "datasets",
            datasets_path is not None,
            (f"{datasets_path} via {via}" if datasets_path else "not found"),
            used_for="resolving dataset: references; snapshotting deck data",
        )
    )
    if datasets_path is None:
        res.warn(
            "capability_unavailable",
            "datasets CLI not found; resolving dataset: references and snapshotting deck data "
            "are unavailable.",
            next=install_hint("datasets"),
        )

    repo = find_repo()
    repo_info: dict = {"found": repo is not None, "marker": MARKER}
    if repo is None:
        res.warn(
            "repository_not_found",
            f"no {MARKER} in this directory or any parent.",
            next="cd into a "
            "presentations repository, or create presentations.toml (see the skill's specification §2)",
        )
    else:
        repo_info["root"] = str(repo)
        try:
            manifest = formats.load(repo / MARKER)
            errs = schemas.errors("presentations", manifest)
            repo_info["valid"] = not errs
            repo_info["errors"] = errs
            repo_info["standard"] = (
                manifest.get("standard") if isinstance(manifest, dict) else None
            )
            if errs:
                res.warn(
                    "manifest_invalid",
                    f"{MARKER} does not match the schema: {errs[0]}",
                    next="present explain doctor",
                )
            elif repo_info["standard"] not in STANDARDS:
                res.warn(
                    "standard_unsupported",
                    f"standard {repo_info['standard']} is not one this release validates "
                    f"({', '.join(map(str, STANDARDS))}).",
                    next="upgrade the presentation skill",
                )
        except Exception as exc:
            repo_info["valid"] = False
            res.warn(
                "manifest_unreadable", f"{MARKER}: {exc}", next=f"fix {repo / MARKER}"
            )

    fb = {"adapter": feedback.adapter_state(), "collection": feedback.collection_state()}
    if not fb["adapter"]["managed"]:
        res.warn(
            "feedback_adapter_missing",
            f"{fb['adapter']['path']} is not a skill-feedback managed adapter; calls are not counted.",
            next="skill-feedback wrapper presentation --feature cli --target public/scripts/cli/present "
            "--output public/scripts/present --apply",
        )

    res.data = {
        "present": __version__,
        "skill_root": str(SKILL_ROOT),
        "standards": list(STANDARDS),
        "core": checks,
        "capabilities": capabilities,
        "repository": repo_info,
        "feedback": fb,
    }
    res.text.append(
        f"present {__version__} — standards {', '.join(map(str, STANDARDS))}"
    )
    for c in checks + capabilities:
        res.text.append(
            f"  {'ok ' if c['ok'] else 'MISSING'} {c['name']:<12} {c['detail']}"
        )
    res.text.append(f"  repository: {repo_info.get('root', 'none found')}")
    ad, col = fb["adapter"], fb["collection"]
    res.text.append(
        f"  feedback: adapter {'managed' if ad['managed'] else 'NOT managed'} "
        f"(feature {ad['feature']}); collection {col['state']}"
        + (f" ({col['env_opt_out']})" if col["env_opt_out"] else "")
    )
    if not core_ok:
        missing = ", ".join(c["name"] for c in checks if not c["ok"])
        return res.error(
            "core_prerequisite_missing",
            f"core prerequisites missing: {missing}",
            repairable=True,
            next="run present through its launcher (uv run --script) so dependencies resolve",
        )
    return res
