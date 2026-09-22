"""Bounded skill identity and deterministic artifact observations; never follows nested links."""

import hashlib
import json
import os
from pathlib import Path
import re
import stat

NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
# Vercel 1.5.23 excludes these runtime artifacts. Other files are significant.
IGNORED_DIRS = {".git", "__pycache__", "__pypackages__"}
IGNORED_FILES = {"metadata.json"}


class Refusal(ValueError):
    """A prerequisite or evidence precondition is not satisfied."""


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def scalar(value):
    value = value.strip()
    if value.startswith('"'):
        try:
            return json.loads(value)
        except ValueError as exc:
            raise Refusal("unsupported quoted YAML scalar") from exc
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value.split(" #", 1)[0].strip()


def identity(path):
    text = (Path(path) / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        raise Refusal("SKILL.md has no bounded YAML frontmatter")
    header = match[1]
    names = re.findall(r"^name:[ \t]*(.*)$", header, re.M)
    if len(names) != 1:
        raise Refusal("expected one scalar name in SKILL.md")
    name = scalar(names[0])
    if not isinstance(name, str) or len(name) > 64 or not NAME.fullmatch(name):
        raise Refusal("unsupported or invalid skill name")
    metadata = re.search(r"^metadata:[ \t]*\r?\n((?:[ \t]+[^\n]*\n?)*)", header, re.M)
    versions = (
        re.findall(r"^[ \t]+version:[ \t]*(.*)$", metadata[1], re.M) if metadata else []
    )
    return {
        "name": name,
        "version": scalar(versions[0]) if len(versions) == 1 else None,
    }


def snapshot(path):
    root = Path(path)
    files = {}

    def failed(error):
        raise error

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=failed):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS | IGNORED_FILES)
        for name in sorted(names + dirs.copy()):
            if name in IGNORED_FILES:
                continue
            item = Path(directory) / name
            relative = item.relative_to(root).as_posix()
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode):
                files[relative] = {"kind": "symlink", "target": os.readlink(item)}
                if name in dirs:
                    dirs.remove(name)
            elif stat.S_ISREG(info.st_mode):
                h = hashlib.sha256()
                with item.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(chunk)
                files[relative] = {
                    "kind": "file",
                    "sha256": h.hexdigest(),
                    "mode": stat.S_IMODE(info.st_mode),
                    "size": info.st_size,
                }
            elif not stat.S_ISDIR(info.st_mode):
                raise Refusal(f"unsupported special file: {relative}")
    return {"hash": digest(files), "files": files}


def artifact(path):
    root = Path(path).expanduser().resolve(strict=True)
    if "dev" in root.parts or not (root / "SKILL.md").is_file():
        raise Refusal(
            "select the exact installable artifact containing SKILL.md, outside dev"
        )
    meta = identity(root)
    snap = snapshot(root)
    if any(v["kind"] == "symlink" for v in snap["files"].values()):
        raise Refusal(
            "source artifact contains symlinks; publish or sync a self-contained tree"
        )
    if any(p != "SKILL.md" and p.endswith("/SKILL.md") for p in snap["files"]):
        raise Refusal("source contains multiple discoverable skills")
    return {"path": str(root), **meta, **snap}


def file_changes(source, installed):
    before = installed.get("files", {})
    after = source["files"]
    return [
        {
            "path": p,
            "change": "added"
            if p not in before
            else "removed"
            if p not in after
            else "changed",
            "installed": before.get(p),
            "source": after.get(p),
        }
        for p in sorted(before.keys() | after.keys())
        if before.get(p) != after.get(p)
    ]
