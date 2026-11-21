"""The artifact store (task 0005; specification §5; ADR 0003): one version contract for every kind.

Layout of an artifact folder::

    <kind>.yaml   src/   vX.Y.Z/ (+ receipt.json)   latest -> vX.Y.Z   approvals.yaml   CHANGELOG.md

Bump protocol (crash-safe): create vX.Y.Z/ holding an `.incomplete` marker → write outputs →
write receipt.json → remove the marker → repoint `latest` by atomic rename → append CHANGELOG.
A crash before the marker is removed leaves an incomplete folder that every later bump refuses
until it is removed; a crash after leaves `latest` behind the newest complete version, which
`summary` reports as `latest_behind`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from . import STANDARDS, __version__, formats, schemas

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
VDIR = re.compile(r"^v((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*))$")
INCOMPLETE = ".incomplete"
RECEIPT = "receipt.json"
LEVELS = ("major", "minor", "patch")


class StoreError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        next: str | None = None,
        repairable: bool = True,
    ):
        super().__init__(message)
        self.code, self.message, self.next, self.repairable = (
            code,
            message,
            next,
            repairable,
        )


def parse(v: str) -> tuple[int, int, int]:
    m = SEMVER.match(v)
    if not m:
        raise StoreError("version_invalid", f"not a semantic version: {v!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def next_version(prev: str | None, level: str) -> str:
    if prev is None:
        return "1.0.0"
    major, minor, patch = parse(prev)
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise StoreError(
        "level_invalid", f"level must be one of {', '.join(LEVELS)}: {level!r}"
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- reading


def version_dirs(art: Path) -> list[Path]:
    if not art.is_dir():
        return []
    out = [
        p
        for p in art.iterdir()
        if p.is_dir() and not p.is_symlink() and VDIR.match(p.name)
    ]
    return sorted(out, key=lambda p: parse(p.name[1:]))


def is_complete(vdir: Path) -> bool:
    return (vdir / RECEIPT).is_file() and not (vdir / INCOMPLETE).exists()


def complete_versions(art: Path) -> list[str]:
    return [p.name[1:] for p in version_dirs(art) if is_complete(p)]


def incomplete_versions(art: Path) -> list[str]:
    return [p.name[1:] for p in version_dirs(art) if not is_complete(p)]


def latest(art: Path) -> str | None:
    """The version `latest` points at, or None. Raises StoreError when `latest` is malformed."""
    link = art / "latest"
    if not link.exists() and not link.is_symlink():
        return None
    if not link.is_symlink():
        raise StoreError(
            "latest_not_symlink",
            f"{link} is a real file or directory, not a symlink "
            "(the m2-design failure mode).",
            next="move it aside, then re-run the bump",
        )
    target = os.readlink(link)
    m = VDIR.match(target)
    if not m or "/" in target:
        raise StoreError(
            "latest_invalid",
            f"{link} -> {target!r}; it must point at a sibling vX.Y.Z.",
        )
    vdir = art / target
    if not vdir.is_dir() or vdir.is_symlink():
        raise StoreError(
            "latest_dangling", f"{link} -> {target}, which does not exist."
        )
    if not is_complete(vdir):
        raise StoreError(
            "latest_incomplete", f"{link} -> {target}, which is incomplete."
        )
    return m.group(1)


def receipt(art: Path, version: str) -> dict[str, Any]:
    path = art / f"v{version}" / RECEIPT
    if not path.is_file():
        raise StoreError(
            "version_not_found",
            f"{art.name}: no version {version}",
            next="present … show",
        )
    return json.loads(path.read_text(encoding="utf-8"))


def receipt_digest(art: Path, version: str) -> str:
    return sha256(art / f"v{version}" / RECEIPT)


def load_approvals(art: Path) -> list[dict[str, Any]]:
    path = art / "approvals.yaml"
    if not path.is_file():
        return []
    data = formats.load(path) or {}
    errs = schemas.errors("approvals", data)
    if errs:
        raise StoreError("approvals_invalid", f"{path}: {errs[0]}")
    return list(data.get("approvals", []))


def approved_versions(art: Path) -> list[str]:
    """Versions with an approval whose recorded digest still matches the receipt."""
    out = []
    for a in load_approvals(art):
        try:
            if receipt_digest(art, a["version"]) == a["checks"]["digest"]:
                out.append(a["version"])
        except (StoreError, FileNotFoundError):
            continue
    return sorted(set(out), key=parse)


def summary(art: Path) -> dict[str, Any]:
    """Never raises: a malformed store is reported in `problems`."""
    kind = next(
        (k for k in ("script", "deck", "library-slide") if (art / f"{k}.yaml").is_file()),
        None,
    )
    out: dict[str, Any] = {
        "exists": art.is_dir() and (kind is not None or (art / "src").is_dir()),
        "kind": kind,
        "versions": complete_versions(art),
        "incomplete": incomplete_versions(art),
        "latest": None,
        "approved": [],
        "problems": [],
    }
    try:
        out["latest"] = latest(art)
    except StoreError as exc:
        out["problems"].append({"code": exc.code, "message": exc.message})
    try:
        out["approved"] = approved_versions(art)
    except StoreError as exc:
        out["problems"].append({"code": exc.code, "message": exc.message})
    if (
        out["versions"]
        and out["latest"]
        and parse(out["versions"][-1]) > parse(out["latest"])
    ):
        out["problems"].append(
            {
                "code": "latest_behind",
                "message": f"latest is {out['latest']} but "
                f"{out['versions'][-1]} is complete (a bump was interrupted after freezing).",
            }
        )
    for v in out["incomplete"]:
        out["problems"].append(
            {
                "code": "version_incomplete",
                "message": f"v{v} is incomplete "
                "(an interrupted bump); remove it before the next bump.",
            }
        )
    return out


# --------------------------------------------------------------------------- git


def git_state(repo_root: Path, paths: list[Path]) -> dict[str, Any]:
    try:
        head = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if head.returncode != 0:
            return {"commit": None, "dirty": True}
        rels = [str(p) for p in paths]
        st = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain", "--", *rels],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "commit": head.stdout.strip(),
            "dirty": bool(st.stdout.strip()) or st.returncode != 0,
        }
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": True}


# --------------------------------------------------------------------------- writing


def _no_symlinks(repo_root: Path, art: Path) -> None:
    """Refuse a symlink anywhere from the repository root down to the artifact, or inside src/."""
    try:
        rel = art.absolute().relative_to(repo_root.absolute())
    except ValueError:
        raise StoreError("outside_repository", f"{art} is not inside {repo_root}.", repairable=False)
    cur = repo_root.absolute()
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise StoreError("symlink_in_path", f"{cur} is a symlink; artifact paths must be real directories.")
    src = art / "src"
    for p in src.rglob("*"):
        if p.is_symlink():
            raise StoreError(
                "symlink_in_path", f"{p} is a symlink; src/ must hold real files."
            )


def src_files(art: Path) -> list[Path]:
    src = art / "src"
    if not src.is_dir():
        raise StoreError("src_missing", f"{art}/src/ does not exist.")
    return sorted(
        p for p in src.rglob("*") if p.is_file() and not p.name.startswith(".")
    )


@dataclass
class BumpResult:
    version: str
    previous: str | None
    receipt: dict[str, Any]
    path: Path
    warnings: list[str] = field(default_factory=list)


Produce = Callable[
    [Path, Path], None
]  # (artifact folder, version folder) → writes outputs


def _atomic_symlink(target: str, link: Path) -> None:
    tmp = link.with_name(f".latest.{secrets.token_hex(4)}.tmp")
    os.symlink(target, tmp)
    os.replace(
        tmp, link
    )  # rename(2) over the old symlink: never `ln -sfn` into a directory


def bump(
    repo_root: Path,
    art: Path,
    *,
    kind: str,
    level: str,
    note: str,
    produce: Produce,
    version: str | None = None,
    pins: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
    origin: str = "built",
    standard: int | None = None,
    extra_inputs: list[Path] | None = None,
    datasets: list[dict[str, Any]] | None = None,
) -> BumpResult:
    if not note or not note.strip():
        raise StoreError(
            "note_missing",
            "every version needs --note (it becomes the CHANGELOG line).",
        )
    if level not in LEVELS:
        raise StoreError("level_invalid", f"--level must be one of {', '.join(LEVELS)}")
    _no_symlinks(repo_root, art)
    if incomplete_versions(art):
        v = incomplete_versions(art)[0]
        raise StoreError(
            "version_incomplete",
            f"v{v} is incomplete (an earlier bump was interrupted).",
            next=f"inspect and remove {art / ('v' + v)}, then re-run",
        )
    prev = latest(art)
    complete = complete_versions(art)
    if complete and prev is not None and parse(complete[-1]) > parse(prev):
        raise StoreError(
            "latest_behind",
            f"latest is {prev} but v{complete[-1]} is complete.",
            next=f"repoint latest to v{complete[-1]} (ln -s v{complete[-1]} latest.new && mv -T latest.new latest), "
            "after checking that version",
        )
    new = version or next_version(prev, level)
    parse(new)
    if prev is not None and parse(new) <= parse(prev):
        raise StoreError(
            "version_not_increasing", f"{new} is not greater than latest {prev}."
        )
    vdir = art / f"v{new}"
    if vdir.exists() or vdir.is_symlink():
        raise StoreError(
            "version_exists", f"v{new} already exists; versions are immutable."
        )
    inputs = src_files(art) + list(extra_inputs or [])

    vdir.mkdir()
    (vdir / INCOMPLETE).write_text("bump in progress\n", encoding="utf-8")
    produce(art, vdir)
    outputs = {
        p.relative_to(repo_root).as_posix(): {
            "sha256": sha256(p),
            "bytes": p.stat().st_size,
        }
        for p in sorted(vdir.rglob("*"))
        if p.is_file() and p.name not in (RECEIPT, INCOMPLETE)
    }
    rec: dict[str, Any] = {
        "schema_version": 1,
        "kind": kind,
        "artifact": art.relative_to(repo_root).as_posix(),
        "version": new,
        "previous": prev,
        "level": level if prev is not None else "initial",
        "note": note.strip(),
        "created": _now(),
        "origin": origin,
        "inputs": {
            "files": {
                p.relative_to(repo_root).as_posix(): {
                    "sha256": sha256(p),
                    "bytes": p.stat().st_size,
                }
                for p in inputs
            }
        },
        "outputs": outputs,
        "tools": {
            "present": __version__,
            "standard": standard or STANDARDS[-1],
            **(tools or {}),
        },
        "git": git_state(
            repo_root,
            [
                art.relative_to(repo_root) / "src",
                art.relative_to(repo_root) / f"{kind}.yaml",
            ],
        ),
    }
    if pins:
        rec["inputs"]["pins"] = pins
    if datasets:  # deck data snapshotted from dataset: references (task 0022)
        rec["inputs"]["datasets"] = datasets
    errs = schemas.errors("receipt", rec)
    if errs:
        raise StoreError(
            "receipt_invalid",
            f"internal: receipt fails its schema: {errs[0]}",
            repairable=False,
        )
    (vdir / RECEIPT).write_text(
        json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (vdir / INCOMPLETE).unlink()
    _atomic_symlink(f"v{new}", art / "latest")
    with (art / "CHANGELOG.md").open("a", encoding="utf-8") as fh:
        if fh.tell() == 0:
            fh.write(f"# Changelog — {art.relative_to(repo_root).as_posix()}\n\n")
        fh.write(f"- {new} ({rec['level']}, {rec['created'][:10]}): {rec['note']}\n")
    return BumpResult(new, prev, rec, vdir)


def verify(repo_root: Path, art: Path, version: str) -> list[dict[str, str]]:
    """Recompute every output hash of one version; [] when it verifies."""
    rec = receipt(art, version)
    findings = []
    vdir = art / f"v{version}"
    listed = set(rec.get("outputs", {}))
    for rel, meta in rec.get("outputs", {}).items():
        p = repo_root / rel
        if not p.is_file():
            findings.append({"code": "output_missing", "path": rel})
        elif sha256(p) != meta["sha256"]:
            findings.append({"code": "output_changed", "path": rel})
    for p in sorted(vdir.rglob("*")):
        if (
            p.is_file()
            and p.name not in (RECEIPT, INCOMPLETE)
            and p.relative_to(repo_root).as_posix() not in listed
        ):
            findings.append(
                {"code": "output_unlisted", "path": p.relative_to(repo_root).as_posix()}
            )
    for name, pin in rec.get("inputs", {}).get("pins", {}).items():
        p = repo_root / pin["path"]
        if not p.is_file():
            findings.append({"code": "pin_missing", "path": pin["path"]})
        elif sha256(p) != pin["sha256"]:
            # A pin to another version's receipt must never change (immutable store). A pin to a
            # live input (the brand token file) records what this version was built with; the
            # file moving on afterwards is history, not damage (found in the pilot, 2026-11-12).
            live = not pin["path"].endswith(RECEIPT)
            findings.append(
                {"code": "pin_since_changed" if live else "pin_changed", "path": pin["path"]}
            )
    return findings


def approve(
    repo_root: Path,
    art: Path,
    version: str,
    *,
    by: str,
    checks: dict[str, Any],
    concerns: dict[str, int] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Append one approval. Refuses a version that does not verify or was built from a dirty tree."""
    rec = receipt(art, version)
    bad = verify(repo_root, art, version)
    if bad:
        raise StoreError(
            "version_unverified",
            f"v{version} does not verify: {bad[0]['code']} {bad[0]['path']}",
            repairable=False,
        )
    if rec["git"]["dirty"]:
        raise StoreError(
            "dirty_build",
            f"v{version} was built from uncommitted sources; approval needs a "
            "version built from a clean tree.",
            next="commit src/, bump again, then approve",
        )
    entry: dict[str, Any] = {
        "version": version,
        "at": _now(),
        "by": by,
        "checks": {"digest": receipt_digest(art, version), **checks},
    }
    if concerns is not None:
        entry["concerns"] = concerns
    if note:
        entry["note"] = note
    path = art / "approvals.yaml"
    existing = load_approvals(art)
    doc = {"schema_version": 1, "approvals": existing + [entry]}
    errs = schemas.errors("approvals", doc)
    if errs:
        raise StoreError("approvals_invalid", f"internal: {errs[0]}", repairable=False)
    tmp = path.with_name(".approvals.yaml.tmp")
    tmp.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    os.replace(tmp, path)
    return entry


def _now() -> str:
    from .context import (
        now_iso,
    )  # late import: context imports console, which imports this package

    return now_iso()


def copy_tree(src: Path, dst: Path) -> None:
    """Copy src/ contents (regular files only, dotfiles skipped) into dst."""
    for p in sorted(src.rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            out = dst / p.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, out)
