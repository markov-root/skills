"""Adapter for adopted Markdown validation."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace

from ..documents.contracts import GENERIC_ROLES
from ..documents.markdown import DocFinding, findings_markdown
from ..documents.validation import (
    expand_markdown_paths,
    scan_typed_documents,
    validate_adopted_documents,
    validate_documents,
)
from ..policy.document_paths import DocumentContainment
from ..policy.manifest import ManifestV2
from ..project.context import AdoptedProject, load_adopted_project
from .contracts import EXIT_CHECK_FAILED, EXIT_OK, CommandResult, CommandSpec, explanation


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--markdown", action="store_true", help="render findings as Markdown")


def handle(args: argparse.Namespace) -> CommandResult:
    adopted = load_adopted_project(args.project_root)
    if isinstance(adopted.manifest, ManifestV2):
        return _handle_v2(args, adopted)
    policy = adopted.manifest.docs
    paths = expand_markdown_paths(adopted.root, policy.include or ("**/*.md",))
    findings = validate_documents(adopted.root, policy, paths)
    return CommandResult(
        "failed" if findings else "passed",
        adopted.root,
        {"findings": [asdict(item) for item in findings]},
        EXIT_CHECK_FAILED if findings else EXIT_OK,
        findings_markdown(findings) if args.markdown else None,
    )


def _handle_v2(args: argparse.Namespace, adopted: AdoptedProject) -> CommandResult:
    manifest = adopted.manifest
    if not isinstance(manifest, ManifestV2):
        raise TypeError("manifest-v2 docs handler received a legacy manifest")
    root = adopted.root.resolve()
    if root != manifest.path.parent.resolve():
        raise AssertionError("manifest-v2 docs root must remain the manifest repository root")

    policy = manifest.docs
    paths = expand_markdown_paths(root, policy.include or ("**/*.md",))
    global_containment = DocumentContainment.for_global(root)
    global_scan = scan_typed_documents(
        root,
        policy.currency,
        containment=global_containment,
    )
    tagged = [
        ("global", finding)
        for finding in validate_documents(
            root,
            policy,
            paths,
            containment=global_containment,
            typed_scan=global_scan,
        )
    ]
    global_identities = frozenset(
        f"{record.metadata['role']}:{record.metadata['id']}"
        for record in global_scan.records
        if record.metadata.get("role") in GENERIC_ROLES
    )

    for scope in manifest.document_projects.projects:
        containment = DocumentContainment.for_scope(root, scope)
        scan = scan_typed_documents(
            root,
            scope.currency,
            containment=containment,
            extra_known_identities=global_identities,
        )
        tagged.extend(
            (scope.id, finding)
            for finding in validate_adopted_documents(
                root,
                scope.currency,
                containment=containment,
                extra_known_identities=global_identities,
                typed_scan=scan,
            )
        )

    tagged = _dedupe_tagged_findings(tagged)
    findings = [{**asdict(finding), "project": project} for project, finding in tagged]
    return CommandResult(
        "failed" if findings else "passed",
        root,
        {"findings": findings},
        EXIT_CHECK_FAILED if findings else EXIT_OK,
        findings_markdown(_project_labeled_findings(tagged)) if args.markdown else None,
    )


def _dedupe_tagged_findings(
    tagged: list[tuple[str, DocFinding]],
) -> list[tuple[str, DocFinding]]:
    findings: list[tuple[str, DocFinding]] = []
    seen: set[tuple[object, ...]] = set()
    for project, finding in tagged:
        identity = (
            project,
            finding.code,
            finding.path,
            finding.line,
            finding.message,
        )
        if identity in seen:
            continue
        seen.add(identity)
        findings.append((project, finding))
    return findings


def _project_labeled_findings(
    tagged: list[tuple[str, DocFinding]],
) -> list[DocFinding]:
    return [
        finding
        if project == "global"
        else replace(finding, message=f"[{project}] {finding.message}")
        for project, finding in tagged
    ]


SPEC = CommandSpec(
    "docs",
    "validate declared Markdown documentation",
    configure,
    handle,
    explanation(
        "docs",
        "Documentation validation",
        "Validate adopted Markdown structure and optional role/currency policy read-only.",
        ("documentation links, structure, indexes, states, or task evidence are contractual",),
        ("grading prose truth or rewriting historical records",),
        prerequisites=("an adopted engineering.yaml with docs policy",),
        evidence=("path/line findings in JSON or Markdown",),
        limitations=("role authority exists only when the project explicitly adopts it",),
        next_commands=("engineering docs --json",),
    ),
)
