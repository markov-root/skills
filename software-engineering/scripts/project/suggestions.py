"""Non-mutating, provenance-labelled engineering manifest suggestions."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_SUGGESTIONS = 500
_CONTROL_TOKENS = {"|", "||", "&&", ";", ">", ">>", "<", "2>", "2>>"}
_ROLES = {
    "test": ("test", "tests", "unit", "pytest", "vitest"),
    "lint": ("lint", "ruff", "eslint", "check"),
    "format": ("format", "fmt", "prettier"),
    "typecheck": ("typecheck", "type-check", "mypy", "pyright", "tsc"),
    "build": ("build", "compile", "package"),
}


def suggest_manifest(start: str | Path = ".", *, inspection: dict[str, Any]) -> dict[str, Any]:
    """Return review candidates only; never execute or write inferred policy."""
    root = Path(inspection["root"])
    suggestions: list[dict[str, Any]] = []

    candidates = _command_candidates(root, inspection)
    candidate_names = _candidate_names(candidates)
    for item, candidate_name in zip(candidates, candidate_names, strict=True):
        role = _role(item["name"], item["command_text"])
        if role == "other":
            continue
        proposal = {
            "name": candidate_name,
            "role": role,
            **_command_proposal(item["command_text"]),
            "applies_to": _applies_to(item["source"]),
        }
        suggestions.append(
            _suggestion(
                "check",
                proposal,
                item["source"],
                item["confidence"],
                item["rationale"],
            )
        )

    check_names = [item["proposal"]["name"] for item in suggestions if item["kind"] == "check"]
    fast = [
        item["proposal"]["name"]
        for item in suggestions
        if item["kind"] == "check" and item["proposal"]["role"] in {"lint", "format", "typecheck"}
    ]
    if fast:
        suggestions.append(
            _suggestion(
                "profile",
                {"name": "fast", "checks": list(dict.fromkeys(fast))},
                "derived:declared-check-candidates",
                "derived",
                "Groups fast static checks for review; ordering is not adopted policy.",
            )
        )
    if check_names:
        suggestions.append(
            _suggestion(
                "profile",
                {"name": "full", "checks": list(dict.fromkeys(check_names))},
                "derived:declared-check-candidates",
                "derived",
                "Groups every discovered check candidate for review.",
            )
        )

    for signal in inspection["risk_signals"]:
        if not signal["count"]:
            continue
        suggestions.append(
            _suggestion(
                "path-signal",
                {
                    "category": signal["category"],
                    "samples": signal["samples"],
                    "candidate_policy": False,
                },
                signal["source"],
                "observed-signal",
                (
                    "Paths match a built-in risk signal; review before translating samples "
                    "into project-owned globs."
                ),
            )
        )

    generated = next(item for item in inspection["risk_signals"] if item["category"] == "generated")
    schema_sources = _contained_glob(root, ("schemas/**/*", "schema/**/*", "openapi/**/*"))
    if generated["samples"] and schema_sources:
        generation = next(
            (
                item
                for item in candidates
                if any(
                    token in item["name"].lower() for token in ("generate", "codegen", "gen-client")
                )
            ),
            None,
        )
        suggestions.append(
            _suggestion(
                "generated-relationship",
                {
                    "name": "generated-artifacts",
                    "sources": schema_sources[:50],
                    "outputs": generated["samples"],
                    "command": (
                        _command_proposal(generation["command_text"])["command"]
                        if generation
                        else None
                    ),
                },
                (generation["source"] if generation else "derived:builtin-generated+schema-paths"),
                generation["confidence"] if generation else "observed-signal",
                (
                    "Source/output locations co-exist"
                    + (
                        " and a project-owned generation command was found"
                        if generation
                        else ", but no regeneration command was proven"
                    )
                    + "; the relationship remains incomplete until reviewed."
                ),
            )
        )

    suggestions = sorted(
        suggestions,
        key=lambda item: (item["kind"], item["source"], item["id"]),
    )[:MAX_SUGGESTIONS]
    findings = _conflicts(suggestions)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "review_required",
        "root": str(root),
        "contract": "manifest-review-candidate-v1",
        "manifest_schema_promise": False,
        "adopted": False,
        "writes_performed": False,
        "commands_executed": False,
        "inspection_truncated": bool(
            inspection["repository"]["scan_truncated"]
            or inspection["command_candidates"]["truncated"]
        ),
        "suggestions": suggestions,
        "findings": findings,
        "summary": {
            "suggestion_count": len(suggestions),
            "conflict_count": len(findings),
            "kinds": {
                kind: sum(item["kind"] == kind for item in suggestions)
                for kind in sorted({item["kind"] for item in suggestions})
            },
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Engineering manifest review candidates",
        "",
        (
            "> These candidates are not adopted policy, were not executed, and are not a stable "
            "engineering.yaml schema promise."
        ),
        "",
    ]
    for kind in sorted({item["kind"] for item in report["suggestions"]}):
        lines.extend((f"## {kind.replace('-', ' ').title()}", ""))
        for item in report["suggestions"]:
            if item["kind"] != kind:
                continue
            proposal = json.dumps(item["proposal"], sort_keys=True, separators=(",", ":"))
            lines.extend(
                (
                    f"- `{item['id']}` · `{item['confidence']}` · `{item['source']}`",
                    f"  - Rationale: {item['rationale']}",
                    f"  - Candidate: `{proposal}`",
                    "  - Adopted: `false`",
                )
            )
        lines.append("")
    lines.extend(("## Conflicts", ""))
    if report["findings"]:
        lines.extend(
            f"- {item['message']} ({', '.join(item['suggestion_ids'])})"
            for item in report["findings"]
        )
    else:
        lines.append("- none detected")
    lines.append("")
    return "\n".join(lines).rstrip()


def _command_candidates(root: Path, inspection: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    project_files = inspection["workspaces"]["project_files"]
    for relative in project_files:
        if Path(relative).name != "package.json":
            continue
        path = root / relative
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        scripts = value.get("scripts", {}) if isinstance(value, dict) else {}
        if not isinstance(scripts, dict):
            continue
        manager = _package_manager(path.parent, root)
        for name, script in sorted(scripts.items()):
            if isinstance(name, str) and isinstance(script, str):
                workspace = path.parent.relative_to(root).as_posix()
                prefix = [] if workspace == "." else ["--dir", workspace]
                command = shlex.join((manager, *prefix, "run", name))
                rows.append(
                    {
                        "name": name,
                        "command_text": command,
                        "source": f"{relative}#scripts.{name}",
                        "confidence": "declared-by-project",
                        "rationale": (
                            f"Package script declares {script!r}; invoke through the detected "
                            f"{manager} project boundary."
                        ),
                    }
                )
    for item in inspection["command_candidates"]["items"]:
        if item["kind"] == "package-script":
            continue
        confidence = (
            "documented-by-project" if item["kind"] == "documented-shell" else "declared-by-project"
        )
        rows.append(
            {
                "name": item["name"],
                "command_text": item["command"],
                "source": item["source"],
                "confidence": confidence,
                "rationale": (
                    "Command is present in contributor instructions."
                    if confidence == "documented-by-project"
                    else "Command is declared by a project-owned command surface."
                ),
            }
        )
    for path in _contained_glob(
        root,
        (
            ".github/workflows/*.yml",
            ".github/workflows/*.yaml",
            ".forgejo/workflows/*.yml",
            ".forgejo/workflows/*.yaml",
            ".gitlab-ci.yml",
        ),
    ):
        rows.extend(_ci_commands(root / path, path))
    unique = {(item["source"], item["name"], item["command_text"]): item for item in rows}
    return sorted(unique.values(), key=lambda item: (item["source"], item["name"]))


def _ci_commands(path: Path, relative: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pattern = re.compile(r"^\s*(?:-\s*)?run\s*:\s*([^|>].+?)\s*$")
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(),
        1,
    ):
        if match := pattern.match(line):
            command = match.group(1).strip().strip("\"'")
            rows.append(
                {
                    "name": f"ci-{line_number}",
                    "command_text": command,
                    "source": f"{relative}:{line_number}",
                    "confidence": "declared-by-project",
                    "rationale": (
                        "A project-owned CI step runs this command; local suitability remains "
                        "subject to environment review."
                    ),
                }
            )
    return rows


def _package_manager(directory: Path, root: Path) -> str:
    current = directory.resolve()
    root = root.resolve()
    while True:
        if (current / "pnpm-lock.yaml").is_file():
            return "pnpm"
        if (current / "yarn.lock").is_file():
            return "yarn"
        if (current / "package-lock.json").is_file():
            return "npm"
        if current == root:
            break
        current = current.parent
    return "npm"


def _command_proposal(command_text: str) -> dict[str, Any]:
    try:
        command = shlex.split(command_text)
    except ValueError:
        return {"command": None, "command_text": command_text, "requires_wrapper": True}
    env_prefix = bool(command and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", command[0]))
    if not command or env_prefix or any(token in _CONTROL_TOKENS for token in command):
        return {"command": None, "command_text": command_text, "requires_wrapper": True}
    return {"command": command, "command_text": command_text, "requires_wrapper": False}


def _role(name: str, command: str) -> str:
    lowered = f"{name} {command}".lower()
    for role, tokens in _ROLES.items():
        if any(re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", lowered) for token in tokens):
            return role
    return "other"


def _applies_to(source: str) -> list[str]:
    if source.endswith("package.json") or "#scripts." in source:
        parent = source.split("#", 1)[0]
        directory = Path(parent).parent.as_posix()
        return ["**/*"] if directory == "." else [f"{directory}/**"]
    return []


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")
    if not normalized or not normalized[0].isalpha():
        normalized = f"candidate-{normalized or 'check'}"
    return normalized[:80]


def _candidate_names(candidates: list[dict[str, str]]) -> list[str]:
    bases = [_safe_name(item["name"]) for item in candidates]
    counts = {name: bases.count(name) for name in set(bases)}
    used: set[str] = set()
    names: list[str] = []
    for base, item in zip(bases, candidates, strict=True):
        if counts[base] == 1:
            candidate = base
        else:
            source_scope = _safe_name(item["source"].split("#", 1)[0].split(":", 1)[0])
            candidate = f"{source_scope}-{base}"[:80]
        original = candidate
        suffix = 2
        while candidate in used:
            candidate = f"{original[:75]}-{suffix}"
            suffix += 1
        used.add(candidate)
        names.append(candidate)
    return names


def _suggestion(
    kind: str,
    proposal: dict[str, Any],
    source: str,
    confidence: str,
    rationale: str,
) -> dict[str, Any]:
    seed = json.dumps(
        {"kind": kind, "proposal": proposal, "source": source},
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "id": f"{kind}-{hashlib.sha256(seed.encode()).hexdigest()[:12]}",
        "kind": kind,
        "proposal": proposal,
        "source": source,
        "confidence": confidence,
        "rationale": rationale,
        "adopted": False,
    }


def _conflicts(suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_role: dict[str, list[dict[str, Any]]] = {}
    for item in suggestions:
        if item["kind"] == "check" and item["proposal"]["role"] != "other":
            by_role.setdefault(item["proposal"]["role"], []).append(item)
    findings = []
    for role, items in sorted(by_role.items()):
        commands = {
            json.dumps(
                item["proposal"].get("command")
                if item["proposal"].get("command") is not None
                else item["proposal"].get("command_text"),
                sort_keys=True,
            )
            for item in items
        }
        if len(commands) <= 1:
            continue
        findings.append(
            {
                "code": "candidate.conflicting-commands",
                "severity": "warning",
                "role": role,
                "message": (
                    f"Project-owned sources declare {len(commands)} distinct {role} commands; "
                    "all remain separate review candidates."
                ),
                "suggestion_ids": [item["id"] for item in items],
                "sources": [item["source"] for item in items],
            }
        )
    return findings


def _contained_glob(root: Path, patterns: tuple[str, ...]) -> list[str]:
    found: set[str] = set()
    for pattern in patterns:
        for candidate in root.glob(pattern):
            if not candidate.is_file():
                continue
            try:
                resolved = candidate.resolve()
                relative = resolved.relative_to(root.resolve()).as_posix()
            except (OSError, RuntimeError, ValueError):
                continue
            if any(
                part in {".git", ".engineering", "node_modules", "vendor"}
                for part in Path(relative).parts
            ):
                continue
            found.add(relative)
    return sorted(found)
