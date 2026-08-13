"""Preview-first generation of a starter ``engineering.yaml`` from review candidates.

This turns non-authoritative manifest suggestions (``project.suggestions``) into a minimal, valid
starter manifest for human review. It is preview-by-default, never overwrites an existing manifest
(policy is never clobbered), validates against the bundled schema before writing, and writes
atomically so an interrupted run cannot leave a partial file. The generated manifest carries a
review placeholder for ``core_outcome`` rather than inventing an approval fact.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from ..resources import schema_path

REVIEW_CORE_OUTCOME = "REVIEW: state the primary user outcome this project must preserve"
DEFAULT_RISK = "moderate"


class InitError(ValueError):
    """Initialization is unsafe: the manifest exists, or the generated manifest is invalid."""


@dataclass(frozen=True)
class InitPlan:
    root: Path
    target: Path
    apply: bool
    action: str  # create
    manifest_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": str(self.target),
            "mode": "apply" if self.apply else "dry-run",
            "action": self.action,
            "changed": self.apply,
            "manifest_preview": self.manifest_text,
        }


def build_manifest(report: dict[str, Any]) -> dict[str, Any]:
    """Assemble a minimal schema-valid manifest from suggestion review candidates."""

    checks: dict[str, Any] = {}
    profiles: dict[str, Any] = {}
    for suggestion in report.get("suggestions", []):
        proposal = suggestion.get("proposal", {})
        if suggestion.get("kind") == "check":
            entry: dict[str, Any] = {"command": list(proposal["command"])}
            if proposal.get("applies_to"):
                entry["applies_to"] = list(proposal["applies_to"])
            checks[proposal["name"]] = entry
        elif suggestion.get("kind") == "profile":
            profiles[proposal["name"]] = {"checks": list(proposal["checks"])}

    manifest: dict[str, Any] = {
        "version": 1,
        "project": {"risk": DEFAULT_RISK, "core_outcome": REVIEW_CORE_OUTCOME},
        "checks": checks,
    }
    if profiles:
        manifest["profiles"] = profiles
    return manifest


def _dump_yaml(manifest: dict[str, Any]) -> str:
    return yaml.safe_dump(manifest, sort_keys=False, default_flow_style=False)


def _validate(manifest: dict[str, Any]) -> None:
    schema = json.loads(Path(schema_path("engineering.schema.json")).read_text(encoding="utf-8"))
    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as exc:  # pragma: no cover - defensive
        raise InitError(f"refusing to write an invalid manifest: {exc.message}") from exc


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_name(f"{path.name}.se-init-tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def plan_init(root: str | Path, report: dict[str, Any], *, apply: bool) -> InitPlan:
    """Plan (and, with ``apply``, perform) starter-manifest initialization."""

    target = Path(root) / "engineering.yaml"
    if target.exists():
        raise InitError(
            f"{target} already exists; refusing to overwrite existing policy (init is create-only)"
        )
    manifest = build_manifest(report)
    _validate(manifest)
    text = _dump_yaml(manifest)
    plan = InitPlan(
        root=Path(root), target=target, apply=apply, action="create", manifest_text=text
    )
    if apply:
        _atomic_write(target, text)
    return plan
