"""Transitional human rendering for passive and active inspection reports."""

from __future__ import annotations

from typing import Any


def render_inspection(report: dict[str, Any]) -> str:
    repository = report["repository"]
    manifest = report["manifest"]
    git = report["git"]
    language_names = ", ".join(item["name"] for item in report["languages"]) or "none detected"
    manager_names = (
        ", ".join(item["name"] for item in report["package_managers"]) or "none detected"
    )
    instruction_count = len(report["instructions"]["sources"])
    conflict_count = len(report["instructions"]["findings"])
    command_count = len(report["command_candidates"]["items"])
    risk_names = (
        ", ".join(item["category"] for item in report["risk_signals"] if item["count"])
        or "none detected"
    )
    resolution = report.get("root_resolution") or {}
    promotion_note: list[str] = []
    if resolution.get("promoted"):
        detail = (
            "it has no `engineering.yaml` of its own"
            if not resolution.get("requested_has_manifest")
            else "its own `engineering.yaml` was NOT used; the resolved root's manifest was"
        )
        note = (
            f"- Requested: `{resolution['requested']}` — root PROMOTED upward; {detail}. "
            "This report describes the resolved root above, not the requested directory."
        )
        promotion_note = [note]
    lines = [
        "# Repository inspection",
        "",
        f"- Root: `{report['root']}`",
        *promotion_note,
        f"- Git: {'yes' if repository['git'] else 'no'}"
        + (
            f" · branch `{git.get('branch') or 'detached'}` · "
            f"{git.get('dirty_count', 0)} changed path(s)"
            if repository["git"]
            else ""
        ),
        f"- Engineering manifest: {manifest['status']}"
        + (
            f" ({len(manifest['path_findings'])} declared path(s) missing)"
            if manifest.get("path_findings")
            else ""
        ),
        f"- Instructions: {instruction_count} source(s), {conflict_count} finding(s)",
        f"- Languages: {language_names}",
        f"- Package managers: {manager_names}",
        f"- Candidate commands: {command_count} (observed only; none adopted)",
        f"- Risk signals: {risk_names}",
        "",
        "Use `engineering explain command.inspect` to see scope, effects, evidence, and limits.",
        'Run `engineering start --intent "..."` only after an engineering manifest is adopted.',
        "",
    ]
    return "\n".join(lines)


def render_active_inspection(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Active repository inspection",
        "",
        f"- Profiles: {', '.join(report['profiles'])}",
        f"- Target: {report['target']}",
        f"- Status: {report['status']}",
        f"- Layers: {summary['layers']}",
        (
            f"- Findings: {summary['findings']} "
            f"(errors={summary['errors']}, warnings={summary['warnings']})"
        ),
        f"- Truncated: {str(summary['truncated']).lower()}",
        "",
        "## Layers",
        "",
    ]
    for layer in report["layers"]:
        tool = layer["tool"]["name"] if layer.get("tool") else "built-in"
        lines.append(
            f"- {layer['name']}: {layer['status']} (tool={tool}, findings={len(layer['findings'])})"
        )
    dependency = report.get("dependency_evidence")
    if dependency:
        lines.extend(("", "## Dependency evidence populations", ""))
        for population in dependency["populations"]:
            statuses = ",".join(population["statuses"]) or "none"
            lines.append(
                f"- {population['name']}: {population['state']} "
                f"(required={str(population['required']).lower()}, statuses={statuses}, "
                f"sources={len(population['sources'])}, "
                f"advisories={population['unique_advisories']}, "
                f"stale={str(population['stale']).lower()}, "
                f"truncated={str(population['truncated']).lower()})"
            )
        lines.extend(("", "## Dependency release risks", ""))
        if dependency["release_risks"]:
            for risk in dependency["release_risks"]:
                lines.append(
                    f"- {risk['code']} (blocking={str(risk['blocking']).lower()}): "
                    f"{risk['message']}"
                )
        else:
            lines.append("- none in the reconciled evidence populations")
    findings = [finding for layer in report["layers"] for finding in layer["findings"]]
    if findings:
        lines.extend(("", "## Findings", ""))
        for finding in findings:
            location = finding.get("path") or finding["source"]
            if finding.get("line"):
                location += f":{finding['line']}"
            lines.append(
                f"- [{finding['severity']}] {finding['id']} at {location}: "
                f"{finding['message']} (fingerprint {finding['fingerprint'][:12]})"
            )
    lines.extend(("", "## Not covered", ""))
    lines.extend(f"- {item}" for item in report["coverage"]["not_covered"])
    lines.extend(
        (
            "",
            "No result grants approval or permission to publish.",
            (
                f"Run `engineering explain profile.inspect.{report['profiles'][0]}` "
                "for scope, effects, evidence, and limits."
            ),
        )
    )
    return "\n".join(lines)
