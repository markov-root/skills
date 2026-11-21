"""Shared lookups for commands: the repository, its manifest, a talk, today's date, neighbour CLIs.

Every lookup walks up or reads a manifest; nothing counts parent directories (ADR 0005).
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import formats, schemas
from .console import Result
from .repo import MARKER, find_repo

TALK_FILE = Path("audience") / "talk.yaml"

DEFAULT_CLAIMS = {
    "id_pattern": r"C-\d+[a-z]?",
    "statuses": ["VERIFIED", "SECONDARY", "SOFT", "UNVERIFIED"],
    "blocking_tiers": [],
}


@dataclass
class Repo:
    root: Path
    manifest: dict[str, Any]

    @property
    def legacy(self) -> list[str]:
        return list(self.manifest.get("legacy", {}).get("talks", []))

    @property
    def claims(self) -> dict[str, Any]:
        return {**DEFAULT_CLAIMS, **self.manifest.get("claims", {})}

    @property
    def standard(self) -> int:
        return int(self.manifest.get("standard", 1))

    def rel(self, path: Path) -> str:
        """Repository-relative POSIX path (receipts never hold absolute paths)."""
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    def rel_any(self, path: Path) -> str:
        """Repository-relative path without resolving symlinks (for reporting links themselves)."""
        try:
            return Path(os.path.abspath(path)).relative_to(self.root.absolute()).as_posix()
        except ValueError:
            return str(path)

    def talks(self) -> list[Path]:
        return sorted(
            p
            for p in self.root.iterdir()
            if p.is_dir() and not p.name.startswith(".") and (p / TALK_FILE).is_file()
        )


def require_repo(res: Result, start: Path | None = None) -> Repo | None:
    """The repository in view, or None with `repository_not_found` / `manifest_invalid` recorded."""
    root = find_repo(start)
    if root is None:
        res.error(
            "repository_not_found",
            f"no {MARKER} in this directory or any parent.",
            repairable=True,
            next="cd into a presentations repository, or create presentations.toml "
            "(specification §2; validate it with `present schema check presentations.toml`)",
        )
        return None
    try:
        manifest = formats.load(root / MARKER)
    except Exception as exc:
        res.error("manifest_unreadable", f"{root / MARKER}: {exc}", repairable=True)
        return None
    errs = schemas.errors("presentations", manifest)
    if errs:
        res.error(
            "manifest_invalid",
            f"{MARKER}: {errs[0]}",
            repairable=True,
            next=f"present schema check {root / MARKER}",
        )
        return None
    return Repo(root, manifest)


def talk_of(repo: Repo, start: Path) -> Path | None:
    """The talk containing `start`: the nearest ancestor (inside the repo) holding audience/talk.yaml."""
    here = start.resolve()
    root = repo.root.resolve()
    for cand in (here, *here.parents):
        if cand == root or root not in cand.parents:
            return None
        if (cand / TALK_FILE).is_file():
            return cand
    return None


def require_talk(res: Result, repo: Repo, name: str | None) -> Path | None:
    """A named talk, or the talk containing the working directory."""
    if name:
        cand = Path(name)
        talk = cand if cand.is_absolute() else (repo.root / name)
        if not talk.is_dir():
            # also accept a path relative to the working directory (e.g. "." inside a talk)
            talk = (Path.cwd() / name).resolve()
        found = talk_of(repo, talk) if talk.is_dir() else None
        if found is None:
            if (repo.root / name).is_dir() and name in repo.legacy:
                res.error(
                    "talk_legacy",
                    f"{name} is a legacy talk (no audience/talk.yaml); it follows "
                    "the repository's legacy conventions.",
                    repairable=False,
                    next="present talk list",
                )
            else:
                res.error(
                    "talk_not_found",
                    f"no standard-1 talk named {name!r} in {repo.root}",
                    repairable=True,
                    next="present talk list",
                )
        return found
    found = talk_of(repo, Path.cwd())
    if found is None:
        res.error(
            "talk_not_found",
            "the working directory is not inside a talk, and no talk was named.",
            repairable=True,
            next="present talk list, then pass the talk name",
        )
    return found


def load_talk(res: Result, talk: Path) -> dict[str, Any] | None:
    try:
        data = formats.load(talk / TALK_FILE)
    except Exception as exc:
        res.error("talk_unreadable", f"{talk / TALK_FILE}: {exc}", repairable=True)
        return None
    errs = schemas.errors("talk", data)
    if errs:
        res.error(
            "talk_invalid",
            f"{talk.name}/{TALK_FILE.as_posix()}: {errs[0]}",
            repairable=True,
            next=f"present schema check {talk / TALK_FILE}",
        )
        return None
    return data


def value(field: Any) -> Any:
    """talk.yaml fields may be `x` or `{value: x, source: …}`."""
    return field.get("value") if isinstance(field, dict) else field


def today() -> _dt.date:
    """Today, overridable for tests and replays with PRESENT_TODAY=YYYY-MM-DD."""
    fixed = os.environ.get("PRESENT_TODAY")
    return _dt.date.fromisoformat(fixed) if fixed else _dt.date.today()


def now_iso() -> str:
    fixed = os.environ.get("PRESENT_NOW")
    if fixed:
        return fixed
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def engineering_cli() -> str | None:
    """The software-engineering `engineering` command; PRESENT_ENGINEERING overrides ('' disables)."""
    override = os.environ.get("PRESENT_ENGINEERING")
    if override is not None:
        return override or None
    return shutil.which("engineering")


def skill_feedback_cli() -> str | None:
    """The `skill-feedback` command (the lesson transport); PRESENT_SKILL_FEEDBACK overrides ('' disables)."""
    override = os.environ.get("PRESENT_SKILL_FEEDBACK")
    if override is not None:
        return override or None
    return shutil.which("skill-feedback")


def _module_dir_of(repo: Repo, start: Path) -> Path | None:
    here = start.resolve()
    for cand in (here, *here.parents):
        if cand == repo.root.resolve():
            return None
        if cand.parent.name == "modules" and (cand.parent.parent / TALK_FILE).is_file():
            return cand
    return None


def require_artifact(res: Result, repo: Repo, ref: str | None, kind: str, *,
                     must_exist: bool = True) -> Path | None:
    """Resolve a script/deck artifact folder.

    `ref` may be an artifact path, a module path, `<talk>/<module>`, or a talk with one module;
    with no ref, the working directory decides. `must_exist=False` (for `new`) accepts a module
    whose artifact folder has no manifest yet.
    """
    def from_dir(d: Path) -> Path | None:
        d = d.resolve()
        if (d / f"{kind}.yaml").is_file() or (d.name == kind and d.parent.parent.name == "modules"):
            return d
        if d.parent.name == "modules":
            return d / kind
        talk = d if (d / TALK_FILE).is_file() else None
        if talk is not None:
            mods = sorted(p for p in (talk / "modules").iterdir() if p.is_dir()) if (talk / "modules").is_dir() else []
            if len(mods) == 1:
                return mods[0] / kind
            res.error("module_ambiguous", f"{talk.name} has {len(mods)} modules; name one.",
                      repairable=True, next=f"present {kind} … {talk.name}/<module>")
            return None
        mod = _module_dir_of(repo, d)
        return (mod / kind) if mod else None

    if ref:
        cands = [Path.cwd() / ref, repo.root / ref]
        parts = Path(ref).parts
        if len(parts) == 2:
            cands.append(repo.root / parts[0] / "modules" / parts[1])
        art = None
        for c in cands:
            if c.is_dir():
                art = from_dir(c)
                if art is not None or res.errors:
                    break
    else:
        art = from_dir(Path.cwd())
    if res.errors:
        return None
    if art is None:
        res.error("artifact_not_found", f"no {kind} artifact at {ref or 'the working directory'}.",
                  repairable=True, next=f"present {kind} … <talk>/<module>")
        return None
    if must_exist and not (art / f"{kind}.yaml").is_file():
        res.error("artifact_not_found", f"{repo.rel(art.parent) if art.parent.exists() else art}: no "
                  f"{kind}.yaml.", repairable=True, next=f"present {kind} new {repo.rel(art.parent)}"
                  if art.parent.exists() else None)
        return None
    return art


def talk_of_artifact(art: Path) -> Path:
    """modules/<m>/<kind> → the talk folder."""
    return art.parent.parent.parent
