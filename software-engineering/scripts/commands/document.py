"""Adapter for adopted typed-document roles, authoring, queries, and graph projections."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from ..documents.authoring import allocate_document
from ..documents.backfill import backfill_document
from ..documents.contracts import DOCUMENT_ROLES
from ..documents.currency import validate_currency
from ..documents.graph import (
    build_document_graph,
    explain_graph_node,
    graph_checks,
    trace_graph,
)
from ..documents.index import (
    list_documents,
    load_document_index,
    show_document,
)
from ..documents.query import compact as compact_document_query
from ..documents.query import inventory as document_query
from ..documents.validation import (
    role_catalog,
    validate_adopted_documents,
)
from ..policy.manifest import load_manifest
from ..project.classifier import git_changes
from ..project.context import load_adopted_project
from ..project.discovery import discover_observation_root, root_resolution
from .contracts import (
    DOCUMENT_AUTHORING,
    EXIT_CHECK_FAILED,
    EXIT_OK,
    CommandResult,
    CommandSpec,
    explanation,
)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        choices=(
            "roles",
            "validate",
            "new",
            "backfill",
            "query",
            "list",
            "show",
            "index",
            "graph",
            "trace",
            "explain",
        ),
    )
    parser.add_argument("identifiers", nargs="*", metavar="IDENTIFIER")
    parser.add_argument("--direction", choices=("inbound", "outbound", "both"), default="both")
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--title", help="reviewed title for 'document new/backfill'")
    parser.add_argument("--summary", help="reviewed one-line summary for 'document backfill'")
    parser.add_argument("--status", help="reviewed status when an existing document has none")
    parser.add_argument("--state", help="filter 'document list' to one lifecycle state")
    parser.add_argument(
        "--state-not", help="filter 'document list' to states other than this value"
    )
    parser.add_argument(
        "--role",
        choices=DOCUMENT_ROLES,
        help="role for 'document query/list' or reviewed role for 'document backfill'",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="emit dependency-aware actionable and blocked task buckets",
    )
    parser.add_argument(
        "--planning-filter",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="filter compact rows by an explicitly adopted planning value; repeatable",
    )
    parser.add_argument(
        "--planning-order",
        action="append",
        default=[],
        metavar="FIELD",
        help="order compact buckets by a field with an explicitly adopted order; repeatable",
    )


def _public_finding(item: Any) -> dict[str, Any]:
    stable_id = item.code if item.code.startswith("document.") else f"document.{item.code}"
    return {
        "id": stable_id,
        "severity": item.severity,
        "message": item.message,
        "provenance": {"path": item.path, "line": item.line},
        "rationale": item.rationale,
        "repair": item.repair,
        "ci_blocking": item.ci_blocking,
    }


def _render_roles(roles: Sequence[dict[str, Any]]) -> str:
    lines = ["# Adopted typed document roles", ""]
    if not roles:
        return "\n".join((*lines, "No typed roles are adopted.", ""))
    for role in roles:
        lines.extend(
            (
                f"## {role['role']}",
                "",
                f"- Authority: `{role['authority_kind']}`",
                f"- States: {', '.join(f'`{state}`' for state in role['states'])}",
                f"- Template: `{role['template']}`",
                f"- Index: `{role['index']}`",
                "",
            )
        )
    return "\n".join(lines)


def _render_findings(findings: Sequence[dict[str, Any]]) -> str:
    lines = ["# Typed document validation", ""]
    if not findings:
        return "\n".join((*lines, "No findings.", ""))
    for item in findings:
        provenance = item["provenance"]
        lines.extend(
            (
                f"- `{item['id']}` at `{provenance['path']}:{provenance['line']}`: {item['message']}",
                f"  Why: {item['rationale']}",
                f"  Repair: {item['repair']}",
            )
        )
    return "\n".join((*lines, ""))


def _render_graph(payload: dict[str, Any]) -> str:
    action = payload["action"]
    lines = [f"# Document {action}", ""]
    if action == "index":
        lines.extend(
            f"- `{item['id']}` — {item['title']} ({item['state']})" for item in payload["nodes"]
        )
    elif action == "trace":
        lines.extend(
            f"- depth {item['distance']}: `{item['id']}` ({item['state']})"
            for item in payload["trace"]["nodes"]
        )
    elif action == "explain":
        item = payload["explanation"]["node"]
        lines.extend(
            (
                f"- Node: `{item['id']}`",
                f"- Selected because: {payload['explanation']['selected_because']}",
                f"- Precedence: {payload['explanation']['precedence']}",
            )
        )
    else:
        lines.extend(
            (
                f"- Nodes: {len(payload['graph']['nodes'])}",
                f"- Edges: {len(payload['graph']['edges'])}",
                f"- Findings: {len(payload['graph']['findings'])}",
                f"- Partial: {str(payload['graph']['partial']).lower()}",
            )
        )
    findings = payload["graph"]["findings"] if action == "graph" else payload.get("findings", ())
    if findings:
        lines.extend(("", "## Findings", ""))
        for item in findings:
            provenance = item["provenance"]
            lines.extend(
                (
                    f"- `{item['id']}` at `{provenance['path']}:{provenance['line']}`: {item['message']}",
                    f"  Repair: {item['repair']}",
                )
            )
    return "\n".join((*lines, ""))


def _render_list(payload: dict[str, Any]) -> str:
    lines = ["# Document list", ""]
    if not payload["documents"]:
        return "\n".join((*lines, "No adopted documents matched.", ""))
    lines.extend(
        f"- `{item['id']}` — {item['title']} ({item['state']}): {item['summary']}"
        for item in payload["documents"]
    )
    return "\n".join((*lines, ""))


def _render_show(payload: dict[str, Any]) -> str:
    document = payload["document"]
    lines = [
        f"# {document['id']}",
        "",
        f"- Title: {document['title']}",
        f"- State: {document['state']}",
        f"- Summary: {document['summary']}",
        f"- Sections: {len(payload['body']['sections'])}",
    ]
    return "\n".join((*lines, ""))


def _render_inventory(report: dict[str, Any]) -> str:
    summary = report["summary"]
    if report.get("view") == "compact":

        def task_label(item: dict[str, Any]) -> str:
            planning = item.get("planning", {})
            suffix = ", ".join(
                f"{name}={detail['value']}" for name, detail in sorted(planning.items())
            )
            return f"{item['id']} [{suffix}]" if suffix else item["id"]

        def task_ids(name: str) -> str:
            return ", ".join(task_label(item) for item in report[name]) or "none"

        lines = [
            "# Task planning view",
            "",
            f"- Actionable: {task_ids('actionable')}",
            f"- Dependency-blocked: {task_ids('dependency_blocked')}",
            f"- Explicitly blocked: {task_ids('declared_blocked')}",
            f"- Needs inspection: {task_ids('needs_inspection')}",
            f"- Completed: {summary['completed']}",
            f"- Contradictions: {summary['contradictions']}",
        ]
        if rule := report.get("planning_rule"):
            filters = ", ".join(f"{item['field']}={item['value']}" for item in rule["filters"])
            lines.extend(
                (
                    f"- Planning filters: {filters or 'none'}",
                    f"- Planning order: {', '.join(rule['order_by']) or 'none'}",
                    f"- Missing planning values: {rule['missing_values']}",
                    f"- Planning tie-breaker: {rule['tie_breaker']}",
                )
            )
        return "\n".join(lines)
    counts = ", ".join(
        f"{name}={count}" for name, count in summary["status_counts"].items() if count
    )
    lines = [
        "# Task inventory",
        "",
        f"- Tasks: {summary['task_count']} ({counts or 'none'})",
        f"- Partial extractions: {summary['partial_extractions']}",
        f"- Contradictions: {summary['contradictions']}",
        f"- Stale handoffs: {summary['stale_handoffs']}",
    ]
    planned = [item for item in report["tasks"] if item.get("planning")]
    if planned:
        lines.extend(("", "## Authored planning metadata", ""))
        for item in planned:
            values = ", ".join(
                f"{name}={detail['value']} ({detail['provenance']['path']}:{detail['provenance']['line']})"
                for name, detail in sorted(item["planning"].items())
            )
            lines.append(f"- {item['id']}: {values}")
    return "\n".join(lines)


def _changed_paths(root) -> list[str]:
    return [item.path for item in git_changes(root)]


def _validate_options(args: argparse.Namespace) -> None:
    if args.action != "trace" and (args.direction != "both" or args.max_depth != 8):
        raise ValueError("--direction and --max-depth require 'document trace'")
    if args.action not in {"new", "backfill"} and args.title is not None:
        raise ValueError("--title requires 'document new' or 'document backfill'")
    if args.action != "backfill" and (args.summary is not None or args.status is not None):
        raise ValueError("--summary and --status require 'document backfill'")
    if args.action != "list" and (args.state is not None or args.state_not is not None):
        raise ValueError("--state and --state-not require 'document list'")
    if args.state is not None and args.state_not is not None:
        raise ValueError("--state and --state-not are mutually exclusive")


def _query(args: argparse.Namespace) -> CommandResult:
    if args.identifiers:
        raise ValueError("document query does not accept identifiers")
    if args.role != "task":
        raise ValueError("document query currently requires --role task")
    if (args.planning_filter or args.planning_order) and not args.compact:
        raise ValueError("--planning-filter and --planning-order require --compact")
    observed = discover_observation_root(args.project_root)
    policy = (
        load_manifest(observed.manifest).task_inventory if observed.manifest is not None else None
    )
    report = document_query(observed.root, policy)
    if args.compact:
        report = compact_document_query(
            report,
            None if policy is None else policy.planning,
            filters=tuple(args.planning_filter),
            order_by=tuple(args.planning_order),
        )
    resolution = root_resolution(observed)
    data = {
        "action": "query",
        "role": "task",
        "root_resolution": resolution,
        **{
            key: value
            for key, value in report.items()
            if key not in {"schema_version", "status", "root"}
        },
    }
    human = _render_inventory(report)
    if resolution["promoted"]:
        manifest_note = (
            "has no `engineering.yaml` of its own"
            if not resolution["requested_has_manifest"]
            else "did not supply the manifest used here"
        )
        human = (
            f"> Anchored to `{resolution['resolved']}` (promoted upward). "
            f"Requested `{resolution['requested']}` {manifest_note}; these tasks belong to "
            "the resolved root, not the requested workspace.\n\n" + human
        )
    return CommandResult(report["status"], observed.root, data, human=human)


def handle(args: argparse.Namespace) -> CommandResult:
    _validate_options(args)
    if args.action == "query":
        return _query(args)
    if (
        (args.action not in {"backfill", "list"} and args.role is not None)
        or args.compact
        or args.planning_filter
        or args.planning_order
    ):
        raise ValueError(
            "--role requires 'document query', 'document list', or 'document backfill'; "
            "--compact, --planning-filter, and --planning-order require 'document query'"
        )
    adopted = load_adopted_project(args.project_root)
    root, manifest = adopted.root, adopted.manifest
    roles = role_catalog(manifest.docs.currency)
    if args.action == "backfill":
        if len(args.identifiers) != 1:
            raise ValueError("document backfill requires exactly one repository-relative path")
        result = backfill_document(
            root,
            args.identifiers[0],
            role=args.role,
            title=args.title,
            summary=args.summary,
            status=args.status,
            policy=manifest.docs.currency,
        )
        data = {
            "action": "backfill",
            "document": asdict(result),
            "limitations": [
                "Only missing or derived v2 core metadata is minted; prose and review authority remain unchanged.",
                "Record-role documents still require a reviewed engineering_document extension and valid body contract.",
            ],
        }
        return CommandResult(
            "passed",
            root,
            data,
            human=f"Backfilled {result.path} ({result.uid}); Markdown body bytes preserved.",
        )
    if args.action == "new":
        if len(args.identifiers) != 1:
            raise ValueError("document new requires exactly one adopted role")
        allocation = allocate_document(
            root, manifest.docs.currency, args.identifiers[0], title=args.title
        )
        data = {
            "action": "new",
            "allocation": asdict(allocation),
            "limitations": [
                "Identity and dates are mechanical; ownership, scope, criteria, and evidence remain reviewed input.",
                "The new record still requires reviewed index registration where the adopted index demands it.",
            ],
        }
        human = (
            f"Created {allocation.path} ({allocation.uid})\n"
            "Review substantive placeholders and register the record in its adopted index."
        )
        return CommandResult("passed", root, data, human=human)
    if args.action == "roles":
        if args.identifiers:
            raise ValueError("document roles does not accept identifiers")
        return CommandResult(
            "passed",
            root,
            {
                "action": "roles",
                "count": len(roles),
                "roles": list(roles),
                "limitations": [
                    "Only explicitly adopted typed roles are listed.",
                    "A role declaration does not establish prose truth or approval.",
                ],
            },
            human=_render_roles(roles),
        )
    if args.action == "validate":
        if args.identifiers:
            raise ValueError("document validate does not accept identifiers")
        try:
            changed_document_paths = _changed_paths(root)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            changed_document_paths = None
        findings = validate_adopted_documents(
            root,
            manifest.docs.currency,
            changed_paths=changed_document_paths,
            current_date=datetime.now(UTC).date().isoformat(),
        )
        public_findings = [_public_finding(item) for item in findings]
        blocking = [item for item in findings if item.severity == "error" or item.ci_blocking]
        status = "failed" if blocking else ("partial" if findings else "passed")
        return CommandResult(
            status,
            root,
            {
                "action": "validate",
                "roles": [role["role"] for role in roles],
                "findings": public_findings,
                "limitations": [
                    "Validation proves recorded structure and internal lifecycle consistency only.",
                    "It does not prove prose truth, approval, evidence quality, or relationship completeness.",
                ],
            },
            EXIT_CHECK_FAILED if blocking else EXIT_OK,
            _render_findings(public_findings),
        )
    document_index = load_document_index(root, manifest.docs.currency)
    if args.action == "list":
        if args.identifiers:
            raise ValueError("document list does not accept identifiers")
        report = list_documents(
            document_index,
            role=args.role,
            state=args.state,
            state_not=args.state_not,
        )
        data = {"action": "list", **report}
        return CommandResult(
            "partial" if document_index.scan.partial else "passed",
            root,
            data,
            human=_render_list(data),
        )
    if args.action == "show":
        if len(args.identifiers) != 1:
            raise ValueError("document show requires exactly one identifier")
        data = {
            "action": "show",
            **show_document(document_index, root, args.identifiers[0]),
        }
        return CommandResult(
            "partial" if document_index.scan.partial else "passed",
            root,
            data,
            human=_render_show(data),
        )
    scan = document_index.scan
    graph = build_document_graph(
        scan,
        validate_currency(root, manifest.docs.currency),
        graph_checks(manifest.checks, manifest.profiles, manifest.fitness),
    )
    graph_data = graph.to_dict()
    has_errors = any(item.severity == "error" for item in graph.findings)
    status = "failed" if has_errors else ("partial" if graph.partial else "passed")
    if args.action == "index":
        if args.identifiers:
            raise ValueError("document index does not accept identifiers")
        data = {
            "action": "index",
            "nodes": graph_data["nodes"],
            "findings": graph_data["findings"],
            "partial": graph.partial,
            "limits": graph_data["limits"],
            "cache": document_index.cache,
        }
    elif args.action == "graph":
        if args.identifiers:
            raise ValueError("document graph does not accept identifiers")
        data = {"action": "graph", "graph": graph_data, "cache": document_index.cache}
    elif args.action == "trace":
        data = {
            "action": "trace",
            "trace": trace_graph(
                graph,
                tuple(args.identifiers),
                direction=args.direction,
                max_depth=args.max_depth,
            ),
            "findings": graph_data["findings"],
            "limits": graph_data["limits"],
            "cache": document_index.cache,
        }
    else:
        if len(args.identifiers) != 1:
            raise ValueError("document explain requires exactly one identifier")
        data = {
            "action": "explain",
            "explanation": explain_graph_node(graph, args.identifiers[0]),
            "findings": graph_data["findings"],
            "limits": graph_data["limits"],
            "cache": document_index.cache,
        }
    return CommandResult(
        status,
        root,
        data,
        EXIT_CHECK_FAILED if has_errors else EXIT_OK,
        _render_graph(data),
    )


SPEC = CommandSpec(
    "document",
    "list adopted typed roles or validate their metadata and currency contracts",
    configure,
    handle,
    explanation(
        "document",
        "Typed document roles",
        "Query, list, show, allocate, atomically backfill, validate, index, trace, graph, and explain document records.",
        (
            "a repository adopts typed task, ADR, audit, research, lesson, or handoff records",
            "document identity or currentness must be checked before continuation",
            "task state and dependency readiness must be reconstructed without writes",
        ),
        (
            "grading prose truth",
            "generating ownership, approval, criteria, or evidence",
        ),
        prerequisites=("an adopted engineering.yaml docs.currency role contract",),
        effects=DOCUMENT_AUTHORING,
        evidence=(
            "role registry with authority/state/template contracts",
            "stable findings with path/line provenance, rationale, repair, and CI semantics",
            "manifest-optional task and handoff query projections with explicit limitations",
            "cached cross-role document list/show projections with staleness checks",
            "bounded nodes/edges, partial external states, traversal direction/depth, and selection provenance",
        ),
        limitations=("valid metadata does not prove prose truth, approval, or evidence quality",),
        next_commands=(
            "engineering document query --role task --compact --json",
            "engineering document list --role ROLE --state STATE --json",
            "engineering document show IDENTIFIER --json",
            "engineering document roles --json",
            "engineering document new ROLE --title TITLE --json",
            "engineering document backfill PATH --role ROLE --title TITLE --summary SUMMARY --json",
            "engineering document validate --json",
            "engineering document graph --json",
            "engineering document trace IDENTIFIER --json",
            "engineering document explain IDENTIFIER --json",
        ),
        references=(
            "docs/context/document-contracts.md",
            "docs/adr/0017-adopt-versioned-document-role-contracts.md",
        ),
    ),
)
