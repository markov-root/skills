"""Projection of bounded imported dependency evidence into inspection layers."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

from .dependencies import (
    MAX_IMPORTS,
    DependencyEvidenceError,
    evidence_is_stale,
    load_dependency_evidence,
)
from .models import ActiveFinding, InspectionLayer, fingerprint


def _import_layer(root: Path, path: str | Path, *, index: int) -> InspectionLayer:
    started = time.monotonic()
    try:
        evidence = load_dependency_evidence(root, path)
    except DependencyEvidenceError as exc:
        return InspectionLayer(
            f"dependency-evidence-import-{index}",
            "security",
            "unavailable",
            True,
            ("bounded local dependency evidence import",),
            (),
            None,
            round((time.monotonic() - started) * 1000),
            reason=str(exc),
            limitations=("Malformed or escaping imports cannot become dependency evidence.",),
        )
    stale = evidence_is_stale(evidence)
    status = (
        "unavailable"
        if evidence.required and (evidence.status == "unavailable" or evidence.truncated or stale)
        else evidence.status
    )
    findings = tuple(
        ActiveFinding(
            "security.dependency-vulnerability",
            "security",
            "error",
            f"dependency advisory {item.id} is {item.applicability}",
            fingerprint(
                f"dependency-import:{evidence.source_id}",
                evidence.import_artifact,
                ":".join(item.identity),
            ),
            evidence.source_id,
            evidence.import_artifact,
            advisory=item.id,
            package=item.package,
            version=item.version,
        )
        for item in evidence.advisories
        if item.applicability in {"affected", "unknown"}
    )
    if findings and status == "passed":
        status = "failed"
    reasons = []
    if stale:
        reasons.append("evidence is stale or has no bounded freshness claim")
    if evidence.truncated:
        reasons.append("evidence is truncated")
    if evidence.status == "unavailable":
        reasons.append("source reported unavailable")
    return InspectionLayer(
        f"dependency-evidence-{evidence.population}-{index}",
        "security",
        status,
        evidence.required,
        (evidence.population, *evidence.source_artifacts),
        findings,
        None,
        round((time.monotonic() - started) * 1000),
        truncated=evidence.truncated,
        reason="; ".join(reasons),
        limitations=evidence.limitations,
        dependency_evidence=(evidence,),
    )


def import_dependency_layers(
    root: Path, paths: Sequence[str | Path]
) -> tuple[InspectionLayer, ...]:
    if len(paths) > MAX_IMPORTS:
        return (
            InspectionLayer(
                "dependency-evidence-imports",
                "security",
                "unavailable",
                True,
                ("bounded local dependency evidence imports",),
                (),
                None,
                0,
                truncated=True,
                reason=f"dependency evidence imports exceeded the {MAX_IMPORTS} artifact bound",
            ),
        )
    return tuple(
        _import_layer(root, path, index=index) for index, path in enumerate(paths, start=1)
    )
