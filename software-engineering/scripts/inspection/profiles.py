"""Explicit security/privacy profile selection and publication aggregation."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..project.discovery import discover_observation_root
from .dependencies import reconcile_dependency_evidence
from .dependency_imports import import_dependency_layers
from .models import InspectionLayer
from .privacy import run_privacy
from .publication import run_gitignore_hygiene
from .scanners.gitleaks import run_gitleaks
from .scanners.osv import run_osv


def run_active_inspection(
    start: str | Path,
    profiles: Sequence[str],
    *,
    target: str,
    offline: bool,
    dependency_evidence_paths: Sequence[str | Path] = (),
) -> dict[str, Any]:
    observed = discover_observation_root(start)
    root = observed.root.resolve()
    selected = set(profiles)
    if "publication" in selected:
        selected.update(("security", "privacy"))
    layers: list[InspectionLayer] = []
    if "security" in selected:
        layers.extend((run_gitleaks(root), run_osv(root, offline=offline)))
        layers.extend(import_dependency_layers(root, dependency_evidence_paths))
    if "privacy" in selected:
        layers.extend(run_privacy(root, target=target))
    if "publication" in selected:
        layers.append(run_gitignore_hygiene(root))
    findings = [finding for layer in layers for finding in layer.findings]
    dependency_records = tuple(
        evidence for layer in layers for evidence in layer.dependency_evidence
    )
    dependency_report = (
        reconcile_dependency_evidence(dependency_records) if "security" in selected else None
    )
    required_unavailable = any(layer.required and layer.status == "unavailable" for layer in layers)
    failed = any(layer.status == "failed" for layer in layers)
    if dependency_report is not None:
        required_unavailable = required_unavailable or dependency_report["status"] == "unavailable"
        failed = failed or dependency_report["status"] == "failed"
    status = "unavailable" if required_unavailable else ("failed" if failed else "passed")
    return {
        "schema_version": 1,
        "root": ".",
        "mode": "active",
        "profiles": sorted(set(profiles)),
        "expanded_domains": sorted({layer.domain for layer in layers}),
        "target": target,
        "offline": offline,
        "status": status,
        "summary": {
            "layers": len(layers),
            "passed": sum(layer.status == "passed" for layer in layers),
            "failed": sum(layer.status == "failed" for layer in layers),
            "unavailable": sum(layer.status == "unavailable" for layer in layers),
            "not_applicable": sum(layer.status == "not_applicable" for layer in layers),
            "findings": len(findings),
            "errors": sum(item.severity == "error" for item in findings),
            "warnings": sum(item.severity == "warning" for item in findings),
            "truncated": any(layer.truncated for layer in layers),
        },
        "layers": [layer.to_dict() for layer in layers],
        **({"dependency_evidence": dependency_report} if dependency_report is not None else {}),
        "coverage": {
            "covered": [
                item
                for item in (
                    (
                        "secret patterns in Git history and the current directory"
                        if "security" in selected
                        else None
                    ),
                    (
                        "population-scoped dependency evidence from OSV and bounded local imports"
                        if "security" in selected
                        else None
                    ),
                    (
                        "privacy candidates in current text, Git patch history, and Git identity"
                        if "privacy" in selected
                        else None
                    ),
                    (
                        "selected privacy-sensitive media metadata"
                        if "privacy" in selected
                        else None
                    ),
                    (
                        "portable private-path ignore rules and current Git index hygiene"
                        if "publication" in selected
                        else None
                    ),
                )
                if item is not None
            ],
            "not_covered": [
                "source-code SAST and data-flow analysis",
                "container-image and operating-system packages",
                "infrastructure-as-code and cloud posture",
                "malware or malicious-package behavior",
                "license policy and legal/privacy compliance",
            ],
        },
        "limitations": [
            "A passing profile supports only the named scopes, versions, and data sources.",
            "No result grants approval or permission to publish.",
        ],
        "next_commands": [
            f"engineering explain profile.inspect.{profile}" for profile in sorted(set(profiles))
        ],
    }
