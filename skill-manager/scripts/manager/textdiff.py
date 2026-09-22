"""Explicit, bounded text rendering separate from the content-only plan contract."""

import difflib
import hashlib
from pathlib import Path

from .artifacts import Refusal


def content(root, relative, evidence):
    if evidence is None:
        return ""
    if evidence["kind"] != "file" or evidence["size"] > 128 * 1024:
        return None
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise Refusal("text diff target changed or escapes its artifact")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != evidence["sha256"]:
        raise Refusal("text changed while rendering; retry diff")
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def text_diffs(plan):
    results = []
    remaining = 2000
    for comparison in plan["comparisons"]:
        for change in comparison["changes"]:
            item = {"installed_path": comparison["path"], "path": change["path"]}
            if remaining <= 0:
                return results + [
                    {
                        "note": "Text output truncated after 2000 diff lines; file manifests remain complete."
                    }
                ]
            before = content(
                Path(comparison["path"]), change["path"], change["installed"]
            )
            after = content(
                Path(plan["source"]["path"]), change["path"], change["source"]
            )
            if before is None or after is None:
                item["note"] = (
                    f"{change['path']}: binary, link, or file over 128 KiB; see content/permission manifest"
                )
            else:
                lines = list(
                    difflib.unified_diff(
                        before.splitlines(keepends=True),
                        after.splitlines(keepends=True),
                        fromfile="installed/" + change["path"],
                        tofile="source/" + change["path"],
                    )
                )
                item["diff"] = "".join(lines[:remaining])
                item["truncated"] = len(lines) > remaining
                remaining -= min(len(lines), remaining)
            results.append(item)
    return results
