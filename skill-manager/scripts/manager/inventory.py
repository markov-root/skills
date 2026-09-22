"""Observe installed paths; filesystem evidence is not proof of a live harness reload."""

import os
from pathlib import Path

from .artifacts import identity, snapshot


def observe(path):
    path = Path(path)
    result = {
        "path": str(path),
        "link": os.readlink(path) if path.is_symlink() else None,
    }
    if not path.exists():
        return {**result, "status": "broken" if path.is_symlink() else "absent"}
    try:
        result["resolved"] = str(path.resolve(strict=True))
        return {**result, "status": "present", **identity(path), **snapshot(path)}
    except (OSError, ValueError, RuntimeError) as exc:
        return {**result, "status": "unavailable", "error": str(exc)}


def inventory(env, selected=None):
    roots = env.roots()
    observations = {}
    failures = []
    names = {selected} if selected else set()
    for root in dict.fromkeys(p for paths in roots.values() for p in paths):
        try:
            if not root.exists():
                if root.is_symlink():
                    failures.append({"path": str(root), "error": "broken skill root"})
                continue
            for entry in sorted(root.iterdir()):
                if entry.name.startswith("."):
                    # Codex bundled system skills remain distinguishable and read-only.
                    if entry.name == ".system" and entry.is_dir():
                        for child in sorted(entry.iterdir()):
                            if child.is_dir() and (child / "SKILL.md").is_file():
                                observations[str(child)] = {
                                    **observe(child),
                                    "category": "system",
                                }
                    continue
                if entry.is_dir() or entry.is_symlink():
                    if selected is None or entry.name == selected:
                        names.add(entry.name)
        except OSError as exc:
            failures.append({"path": str(root), "error": str(exc)})
    for name in sorted(names):
        for paths in roots.values():
            for root in paths:
                target = root / name
                if str(target) not in observations:
                    observations[str(target)] = {**observe(target), "category": "user"}
    records = []
    state = env.state()
    for name in sorted(names):
        exposures = {}
        hashes = set()
        for harness, paths in roots.items():
            candidates = [observations[str(p / name)] for p in paths]
            present = [c for c in candidates if c["status"] == "present"]
            physical = {c["resolved"] for c in present}
            for c in present:
                hashes.add(c["hash"])
            status = "absent"
            if any(c["status"] in ("broken", "unavailable") for c in candidates):
                status = "broken"
            elif len(physical) > 1 or any(c.get("name") != name for c in present):
                status = "ambiguous"
            elif present:
                status = "present"
            exposures[harness] = {
                "status": status,
                "paths": [c["path"] for c in candidates if c["status"] != "absent"],
            }
        records.append(
            {
                "name": name,
                "harnesses": exposures,
                "divergent": len(hashes) > 1,
                "managed": name in state["skills"],
                "source": state["skills"].get(name, {}).get("source"),
                "source_evidence": "manager-receipt"
                if name in state["skills"]
                else "unknown",
            }
        )
    return {
        "skills": records,
        "observations": list(observations.values()),
        "unavailable_roots": failures,
        "limitations": [
            "Observed discovery paths; running-session reload and precedence are not inferred.",
            "Third-party origin is unknown without a Manager receipt; metadata versions do not establish content equality.",
        ],
    }


def compact(result):
    # File manifests belong in explicit diff output, not ordinary inventory.
    return {
        **result,
        "observations": [
            {k: v for k, v in o.items() if k != "files"} for o in result["observations"]
        ],
    }
