"""Adapter for adopted typed-document roles, authoring, queries, and graph projections."""

from __future__ import annotations

import argparse
import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..documents.authoring import allocate_document
from ..documents.backfill import backfill_document
from ..documents.contracts import (
    DOCUMENT_ROLES,
    GENERIC_ROLES,
    RECORD_ROLES,
    ROLE_CONTRACTS,
)
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
    expand_markdown_paths,
    role_catalog,
    scan_typed_documents,
    validate_adopted_documents,
    validate_documents,
)
from ..policy.document_paths import DocumentContainment
from ..policy.document_selection import DocumentSelection, resolve_document_selection
from ..policy.manifest import (
    _RECORD_ID_GLOB,
    _RECORD_ROLE_FOLDERS,
    DocsCurrencyPolicy,
    DocsPolicy,
    DocumentContractPolicy,
    DocumentRolePolicy,
    ManifestV2,
)
from ..policy.project_root import load_explicit_manifest, resolve_explicit_project_root
from ..project.classifier import git_changes
from ..project.discovery import discover_observation_root
from .contracts import (
    DOCUMENT_AUTHORING,
    EXIT_CHECK_FAILED,
    EXIT_OK,
    EXIT_UNAVAILABLE,
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
    parser.add_argument(
        "--docs-root",
        metavar="PATH",
        help=(
            "manifestless authoring root for 'document new/backfill'; requires an "
            "explicit --project-root and conflicts with adopted document policy"
        ),
    )
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
        "severity": getattr(item, "severity", "error"),
        "message": item.message,
        "provenance": {"path": item.path, "line": item.line},
        "rationale": getattr(item, "rationale", "the requested document contract was violated"),
        "repair": getattr(item, "repair", "repair the reported Markdown path or structure"),
        "ci_blocking": getattr(item, "ci_blocking", True),
    }


def _builtin_role_catalog() -> tuple[dict[str, Any], ...]:
    rows = []
    for role in DOCUMENT_ROLES:
        contract = ROLE_CONTRACTS[role]
        rows.append(
            {
                "role": role,
                "authority_kind": contract.authority_kind,
                "lifecycle": contract.lifecycle,
                "schema_version": 2,
                "states": list(contract.states),
                "initial_states": list(contract.initial_states),
                "settled_states": list(contract.settled_states),
                "required_sections": list(contract.required_sections),
                "include": [],
                "index": None,
                "template": f"bundled:assets/templates/{role}.md",
                "contract": {"version": 1, "role": role},
                "adopted": False,
            }
        )
    return tuple(rows)


def _missing_doc_policy(root: Path, *, role: str | None = None) -> ValueError:
    field = "$.docs.currency.roles"
    role_note = f" for role {role!r}" if role else ""
    command = f"engineering document roles --project-root {shlex.quote(str(root))}"
    return ValueError(
        f"missing manifest field `{field}`{role_note}; run `{command}` to retrieve the "
        "built-in role/template contract, then adopt the selected role under docs.currency.roles"
    )


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


def _changed_paths(root: Path) -> list[str]:
    observed = discover_observation_root(root)
    git_root = observed.git_root
    if git_root is None:
        raise RuntimeError("Git changed-path context is unavailable")
    prefix = root.resolve().relative_to(git_root.resolve()).as_posix()
    paths = []
    for item in git_changes(git_root):
        relative = item.path
        if prefix not in {"", "."}:
            marker = f"{prefix}/"
            if not relative.startswith(marker):
                continue
            relative = relative[len(marker) :]
        paths.append(relative)
    return paths


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
    selection = resolve_document_selection(
        args.project_root,
        action="query",
        project_id=getattr(args, "project", None),
    )
    if isinstance(selection.manifest, ManifestV2):
        return _query_v2(args, selection)
    resolution = resolve_explicit_project_root(args.project_root)
    manifest = load_explicit_manifest(resolution, required=False)
    policy = manifest.task_inventory if manifest is not None else None
    report = document_query(resolution.root, policy)
    if args.compact:
        report = compact_document_query(
            report,
            None if policy is None else policy.planning,
            filters=tuple(args.planning_filter),
            order_by=tuple(args.planning_order),
        )
    serialized_resolution = resolution.to_dict()
    data = {
        "action": "query",
        "role": "task",
        "root_resolution": serialized_resolution,
        **{
            key: value
            for key, value in report.items()
            if key not in {"schema_version", "status", "root"}
        },
    }
    human = _render_inventory(report)
    if resolution.changed:
        human = (
            f"> Warning: requested `{resolution.requested}` resolved to `{resolution.root}`; "
            "traversal remains anchored there and no ancestor repository was substituted.\n\n"
            + human
        )
    return CommandResult(report["status"], resolution.root, data, human=human)


def _query_v2(args: argparse.Namespace, selection: DocumentSelection) -> CommandResult:
    scope = selection.selected_project
    if scope is None:
        raise AssertionError("manifest-v2 query selection did not resolve one project")
    root = _v2_repository_root(selection)
    report = document_query(
        root,
        scope.task_inventory,
        docs_root=scope.docs_root,
    )
    if args.compact:
        report = compact_document_query(
            report,
            scope.task_inventory.planning,
            filters=tuple(args.planning_filter),
            order_by=tuple(args.planning_order),
        )
    data = {
        "action": "query",
        "role": "task",
        "root_resolution": selection.to_dict(),
        "selected_project": scope.id,
        **{
            key: value
            for key, value in report.items()
            if key not in {"schema_version", "status", "root"}
        },
    }
    return CommandResult(
        report["status"],
        root,
        data,
        human=_render_inventory(report),
    )


def _synthetic_manifestless_policy(docs_root_rel: str, role: str) -> DocsCurrencyPolicy:
    """Task 0106: built-in defaults for one role, expressed against the selected docs root.

    Record roles allocate in their canonical subfolder; living/meta roles allocate
    FLAT in the docs root (document_id "role-NNNN"), mirroring the adopted
    convention where living/meta roles sit beside their catalog index.
    """
    if role in RECORD_ROLES:
        folder = _RECORD_ROLE_FOLDERS[role]
        index = f"{docs_root_rel}/{folder}/README.md"
        include = (f"{docs_root_rel}/{folder}/{_RECORD_ID_GLOB}",)
    else:
        index = f"{docs_root_rel}/catalog.md"
        include = (f"{docs_root_rel}/{_RECORD_ID_GLOB}",)
    return DocsCurrencyPolicy(
        roles=(
            DocumentRolePolicy(
                role,
                include,
                index,
                4,
                (),
                None,
                DocumentContractPolicy(1, role),
            ),
        )
    )


def _reject_nested_project_directory(directory: Path, root: Path, purpose: str) -> None:
    """Task 0106: refuse writes whose ancestry crosses into another project.

    Walks from the target directory up to (excluding) the explicit project root;
    a manifest anywhere in that ancestry means the write would land inside a
    nested project. Unrelated sibling manifests are not in the ancestry and do
    not block. No scan caps, no fail-open truncation; runs before any mutation.
    """
    current = directory.resolve()
    boundary = root.resolve()
    while current != boundary:
        if (current / "engineering.yaml").is_file():
            raise ValueError(
                f"{purpose} lies inside another project ({current}); manifestless "
                "authoring cannot write across a project boundary"
            )
        parent = current.parent
        if parent == current:
            break
        current = parent


def _handle_manifestless(args: argparse.Namespace, root_argument: str) -> CommandResult:
    """Task 0106: explicit --project-root + --docs-root authoring with built-in defaults.

    Authority reuses the existing resolver (manifest-optional 'roles' probe, non-
    mutating): an exact non-adopting v1 manifest is allowed and shadows ancestors;
    any exact v2 or ancestor v2 registry means adopted policy takes precedence and
    the explicit --docs-root selection conflicts; a malformed manifest surfaces its
    diagnostics and is never treated as absence.
    """
    authority = resolve_document_selection(root_argument, action="roles", project_id=None)
    manifest = authority.manifest
    if isinstance(manifest, ManifestV2):
        # ValueError (not TypeError) so app.py maps this to EXIT_INVALID_POLICY.
        # Name the ACTUAL registry manifest, not the requested child root.
        raise ValueError(  # noqa: TRY004
            f"--docs-root conflicts with the adopted manifest-v2 registry at "
            f"{manifest.path}; use --project <id> with the adopted registry instead"
        )
    if manifest is not None and manifest.docs.currency is not None:
        raise ValueError(
            f"--docs-root conflicts with adopted document policy at "
            f"{manifest.path}; omit --docs-root to author under the adopted policy"
        )

    resolution = resolve_explicit_project_root(root_argument)
    root = resolution.root
    docs_root_request = Path(args.docs_root)
    docs_root = docs_root_request if docs_root_request.is_absolute() else root / docs_root_request
    containment = DocumentContainment.for_project_docs(root, docs_root)
    docs_root_resolved = containment.docs_root
    docs_root_rel = docs_root_resolved.relative_to(root).as_posix()

    if args.action == "new":
        if len(args.identifiers) != 1:
            raise ValueError("document new requires exactly one adopted role")
        role = args.identifiers[0]
        policy = _synthetic_manifestless_policy(docs_root_rel, role)
        allocation_directory = docs_root_resolved / _RECORD_ROLE_FOLDERS.get(role, "")
        _reject_nested_project_directory(
            allocation_directory,
            root,
            purpose=f"{role!r} allocation directory {allocation_directory}",
        )
        allocation = allocate_document(
            root,
            policy,
            role,
            title=args.title,
            docs_root=docs_root_resolved,
        )
        data = {
            "action": "new",
            "allocation": asdict(allocation),
            "adopted": False,
            "docs_root": str(docs_root_resolved),
            "defaults": "synthesized built-in role contract (unadopted)",
            "root_resolution": resolution.to_dict(),
            "limitations": [
                "Identity and dates are mechanical; ownership, scope, criteria, and evidence remain reviewed input.",
                "The new record still requires reviewed index registration where the adopted index demands it.",
                "Manifestless authoring writes no manifest and adopts no policy.",
            ],
        }
        return CommandResult(
            "passed",
            root,
            data,
            human=(
                f"Created {allocation.path} ({allocation.uid})\n"
                f"Manifestless mode: built-in defaults (unadopted); docs root: {docs_root_resolved}\n"
                "Review substantive placeholders; there is no adopted index to register in "
                "unless a manifest is adopted later."
            ),
        )

    # backfill
    if len(args.identifiers) != 1:
        raise ValueError("document backfill requires exactly one repository-relative path")
    candidate = Path(args.identifiers[0])
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate_directory = candidate.resolve().parent
    except OSError as exc:
        raise ValueError(f"backfill target is unreachable: {exc}") from exc
    _reject_nested_project_directory(
        candidate_directory,
        root,
        purpose=f"backfill target {args.identifiers[0]!r}",
    )
    result = backfill_document(
        root,
        args.identifiers[0],
        role=args.role,
        title=args.title,
        summary=args.summary,
        status=args.status,
        policy=None,
        docs_root=docs_root_resolved,
    )
    data = {
        "action": "backfill",
        "document": asdict(result),
        "adopted": False,
        "docs_root": str(docs_root_resolved),
        "defaults": "synthesized built-in role contract (unadopted)",
        "root_resolution": resolution.to_dict(),
        "limitations": [
            "Only missing or derived v2 core metadata is minted; prose and review authority remain unchanged.",
            "Record-role documents still require a reviewed engineering_document extension and valid body contract.",
            "Manifestless authoring writes no manifest and adopts no policy.",
        ],
    }
    return CommandResult(
        "passed",
        root,
        data,
        human=(
            f"Backfilled {result.path} ({result.uid}); Markdown body bytes preserved.\n"
            f"Manifestless mode: built-in defaults (unadopted); docs root: {docs_root_resolved}"
        ),
    )


def handle(args: argparse.Namespace) -> CommandResult:
    # Task 0106: normalize an omitted --project-root to "." for every document verb
    # (parser sets the document default to None so explicitness is detectable), then
    # route the explicit docs-root write mode before any mutation.
    explicit_project_root = getattr(args, "project_root", None) is not None
    if not explicit_project_root:
        args.project_root = "."
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
    # Task 0106: the manifestless route runs AFTER the shared option checks above so
    # explicit mode preserves the same rejection semantics (e.g. --compact/--planning-*
    # on new/backfill are still rejected before any write; backfill --role stays valid).
    if getattr(args, "docs_root", None) is not None:
        if args.action not in {"new", "backfill"}:
            raise ValueError("--docs-root requires 'document new' or 'document backfill'")
        if not explicit_project_root:
            raise ValueError(
                "manifestless --docs-root authoring requires an explicit --project-root"
            )
        if getattr(args, "project", None) is not None:
            raise ValueError("--project conflicts with --docs-root; choose one selection")
        return _handle_manifestless(args, args.project_root)
    selection = resolve_document_selection(
        args.project_root,
        action=args.action,
        project_id=getattr(args, "project", None),
    )
    if isinstance(selection.manifest, ManifestV2):
        return _handle_v2(args, selection)
    resolution = resolve_explicit_project_root(args.project_root)
    root = resolution.root
    manifest = load_explicit_manifest(resolution, required=False)
    adopted_roles = role_catalog(manifest.docs.currency) if manifest is not None else ()
    if args.action == "roles":
        if args.identifiers:
            raise ValueError("document roles does not accept identifiers")
        roles = adopted_roles or _builtin_role_catalog()
        adopted = bool(adopted_roles)
        return CommandResult(
            "passed",
            root,
            {
                "action": "roles",
                "adopted": adopted,
                "root_resolution": resolution.to_dict(),
                "count": len(roles),
                "roles": list(roles),
                "limitations": [
                    (
                        "Only explicitly adopted typed roles are listed."
                        if adopted
                        else "Built-in templates are retrieval aids; they are not adopted project policy."
                    ),
                    "A role/template declaration does not establish prose truth or approval.",
                ],
            },
            human=_render_roles(roles),
        )
    if args.action == "validate" and (manifest is None or manifest.docs.currency is None):
        if args.identifiers:
            raise ValueError("document validate does not accept identifiers")
        docs_policy = manifest.docs if manifest is not None else DocsPolicy()
        paths = expand_markdown_paths(root, docs_policy.include or ("**/*.md",))
        findings = validate_documents(root, docs_policy, paths)
        public_findings = [_public_finding(item) for item in findings]
        return CommandResult(
            "failed" if findings else "passed",
            root,
            {
                "action": "validate",
                "adopted": False,
                "root_resolution": resolution.to_dict(),
                "roles": [],
                "findings": public_findings,
                "limitations": [
                    "Without docs.currency adoption, validation is limited to read-only Markdown/link structure.",
                    "Run engineering document roles to retrieve templates before adopting typed roles.",
                ],
            },
            EXIT_CHECK_FAILED if findings else EXIT_OK,
            _render_findings(public_findings),
        )
    if manifest is None:
        load_explicit_manifest(resolution, required=True)
        raise AssertionError("required manifest loader did not fail")
    if manifest.docs.currency is None:
        role = args.identifiers[0] if args.action == "new" and args.identifiers else None
        raise _missing_doc_policy(root, role=role)
    roles = adopted_roles
    if args.action == "new" and args.identifiers:
        requested_role = args.identifiers[0]
        if not any(item["role"] == requested_role for item in roles):
            raise _missing_doc_policy(root, role=requested_role)
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
    if args.action == "validate":
        if args.identifiers:
            raise ValueError("document validate does not accept identifiers")
        changed_document_paths, changed_provenance = _changed_paths_provenance(root)
        current_date = datetime.now(UTC).date().isoformat()
        findings = validate_adopted_documents(
            root,
            manifest.docs.currency,
            changed_paths=changed_document_paths,
            current_date=current_date,
        )
        public_findings = [_public_finding(item) for item in findings]
        blocking = [item for item in findings if item.severity == "error" or item.ci_blocking]
        human = _render_findings(public_findings)
        if changed_provenance["mode"] == "unavailable":
            status = "unavailable"
            exit_code = EXIT_UNAVAILABLE
            human = f"{_unavailable_human(changed_provenance)}\n{human}"
        else:
            status = "failed" if blocking else ("partial" if findings else "passed")
            exit_code = EXIT_CHECK_FAILED if blocking else EXIT_OK
        return CommandResult(
            status,
            root,
            {
                "action": "validate",
                "adopted": True,
                "root_resolution": resolution.to_dict(),
                "roles": [role["role"] for role in roles],
                "findings": public_findings,
                "changed_paths": {**changed_provenance, "validation_date": current_date},
                "limitations": [
                    "Validation proves recorded structure and internal lifecycle consistency only.",
                    "It does not prove prose truth, approval, evidence quality, or relationship completeness.",
                ],
            },
            exit_code,
            human,
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


def _v2_catalog(selection: DocumentSelection) -> tuple[dict[str, Any], ...]:
    manifest = selection.manifest
    if not isinstance(manifest, ManifestV2):
        raise TypeError("manifest-v2 catalog received a legacy selection")
    scope = selection.selected_project
    if scope is None:
        raise AssertionError("manifest-v2 identity selection did not resolve one project")
    return (*role_catalog(scope.currency), *role_catalog(manifest.docs.currency))


def _v2_repository_root(selection: DocumentSelection) -> Path:
    manifest = selection.manifest
    if not isinstance(manifest, ManifestV2):
        raise TypeError("manifest-v2 root guard received a legacy selection")
    repository_root = selection.repository_root.resolve()
    manifest_root = manifest.path.parent.resolve()
    if repository_root != manifest_root:
        raise AssertionError("manifest-v2 capability root must remain the manifest repository root")
    return repository_root


def _tagged_public_finding(item: Any, project: str) -> dict[str, Any]:
    finding = _public_finding(item)
    finding["project"] = project
    return finding


def _dedupe_v2_findings(findings: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[object, ...]] = set()
    deduped = []
    for finding in findings:
        provenance = finding["provenance"]
        identity = (
            finding["project"],
            finding["id"],
            provenance["path"],
            provenance["line"],
            finding["message"],
        )
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(finding)
    return deduped


def _changed_paths_provenance(root: Path) -> tuple[list[str] | None, dict[str, Any]]:
    """Resolve changed paths once per validate path and describe the ratchet inputs.

    Task 0105: discovery failure is explicit — the report records an unavailable
    mode with the reason and the strict-legacy fallback policy instead of a silent
    all-clear, while the current-worktree policy (staged+unstaged+untracked) is
    recorded honestly when listing succeeds.
    """
    try:
        paths = _changed_paths(root)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return None, {
            "mode": "unavailable",
            "paths": None,
            "count": None,
            "reason": str(exc) or type(exc).__name__,
            "policy": "strict-legacy-fallback",
        }
    unique = sorted({path.removeprefix("./") for path in paths if path})
    return paths, {
        "mode": "listed",
        "paths": unique,
        "count": len(unique),
        "reason": None,
        "policy": "current-worktree",
    }


def _unavailable_human(provenance: dict[str, Any]) -> str:
    return (
        f"Changed-path discovery unavailable: {provenance['reason']}\n"
        "Strict legacy fallback applied; this result is not a clean pass."
    )


def _validate_v2(args: argparse.Namespace, selection: DocumentSelection) -> CommandResult:
    if args.identifiers:
        raise ValueError("document validate does not accept identifiers")
    manifest = selection.manifest
    if not isinstance(manifest, ManifestV2):
        raise TypeError("manifest-v2 validation received a legacy selection")
    root = _v2_repository_root(selection)
    changed_document_paths, changed_provenance = _changed_paths_provenance(root)
    current_date = datetime.now(UTC).date().isoformat()

    markdown_policy = DocsPolicy(
        include=manifest.docs.include,
        required_headings=manifest.docs.required_headings,
        forbid_legacy_links=manifest.docs.forbid_legacy_links,
    )
    paths = expand_markdown_paths(root, markdown_policy.include or ("**/*.md",))
    tagged = [
        _tagged_public_finding(item, "global")
        for item in validate_documents(
            root,
            markdown_policy,
            paths,
            changed_paths=changed_document_paths,
            current_date=current_date,
        )
    ]

    global_containment = DocumentContainment.for_global(root)
    global_scan = scan_typed_documents(
        root,
        manifest.docs.currency,
        changed_paths=changed_document_paths or (),
        current_date=current_date,
        containment=global_containment,
    )
    tagged.extend(
        _tagged_public_finding(item, "global")
        for item in validate_adopted_documents(
            root,
            manifest.docs.currency,
            changed_paths=changed_document_paths,
            current_date=current_date,
            containment=global_containment,
            typed_scan=global_scan,
        )
    )
    global_identities = frozenset(
        f"{record.metadata['role']}:{record.metadata['id']}"
        for record in global_scan.records
        if record.metadata.get("role") in GENERIC_ROLES
    )

    for scope in selection.projects:
        containment = DocumentContainment.for_scope(root, scope)
        scan = scan_typed_documents(
            root,
            scope.currency,
            changed_paths=changed_document_paths or (),
            current_date=current_date,
            containment=containment,
            extra_known_identities=global_identities,
        )
        tagged.extend(
            _tagged_public_finding(item, scope.id)
            for item in validate_adopted_documents(
                root,
                scope.currency,
                changed_paths=changed_document_paths,
                current_date=current_date,
                containment=containment,
                extra_known_identities=global_identities,
                typed_scan=scan,
            )
        )

    public_findings = _dedupe_v2_findings(tagged)
    blocking = [
        item for item in public_findings if item["severity"] == "error" or item["ci_blocking"]
    ]
    role_names = []
    for scope in selection.projects:
        role_names.extend(item["role"] for item in role_catalog(scope.currency))
    role_names.extend(item["role"] for item in role_catalog(manifest.docs.currency))
    roles = list(dict.fromkeys(role_names))
    human = _render_findings(public_findings)
    if changed_provenance["mode"] == "unavailable":
        status = "unavailable"
        exit_code = EXIT_UNAVAILABLE
        human = f"{_unavailable_human(changed_provenance)}\n{human}"
    else:
        status = "failed" if blocking else ("partial" if public_findings else "passed")
        exit_code = EXIT_CHECK_FAILED if blocking else EXIT_OK
    return CommandResult(
        status,
        root,
        {
            "action": "validate",
            "adopted": True,
            "root_resolution": selection.to_dict(),
            "selected_project": (
                None if selection.selected_project is None else selection.selected_project.id
            ),
            "roles": roles,
            "findings": public_findings,
            "changed_paths": {
                **changed_provenance,
                "validation_date": current_date,
            },
            "limitations": [
                "Validation proves recorded structure and internal lifecycle consistency only.",
                "It does not prove prose truth, approval, evidence quality, or relationship completeness.",
            ],
        },
        exit_code,
        human,
    )


def _handle_v2(args: argparse.Namespace, selection: DocumentSelection) -> CommandResult:
    if args.action == "validate":
        return _validate_v2(args, selection)
    manifest = selection.manifest
    if not isinstance(manifest, ManifestV2):
        raise TypeError("manifest-v2 handler received a legacy selection")
    scope = selection.selected_project
    if scope is None:
        raise AssertionError("manifest-v2 identity selection did not resolve one project")
    root = _v2_repository_root(selection)
    roles = _v2_catalog(selection)
    if args.action == "roles":
        if args.identifiers:
            raise ValueError("document roles does not accept identifiers")
        return CommandResult(
            "passed",
            root,
            {
                "action": "roles",
                "adopted": True,
                "root_resolution": selection.to_dict(),
                "selected_project": scope.id,
                "count": len(roles),
                "roles": list(roles),
                "limitations": [
                    "Only explicitly adopted typed roles are listed.",
                    "A role/template declaration does not establish prose truth or approval.",
                ],
            },
            human=_render_roles(roles),
        )
    if args.action == "new" and args.identifiers:
        requested_role = args.identifiers[0]
        if not any(item["role"] == requested_role for item in roles):
            raise _missing_doc_policy(root, role=requested_role)
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
            policy=scope.currency,
            docs_root=scope.docs_root,
        )
        return CommandResult(
            "passed",
            root,
            {
                "action": "backfill",
                "selected_project": scope.id,
                "document": asdict(result),
                "limitations": [
                    "Only missing or derived v2 core metadata is minted; prose and review authority remain unchanged.",
                    "Record-role documents still require a reviewed engineering_document extension and valid body contract.",
                ],
            },
            human=f"Backfilled {result.path} ({result.uid}); Markdown body bytes preserved.",
        )
    if args.action == "new":
        if len(args.identifiers) != 1:
            raise ValueError("document new requires exactly one adopted role")
        allocation = allocate_document(
            root,
            scope.currency,
            args.identifiers[0],
            title=args.title,
            docs_root=scope.docs_root,
        )
        data = {
            "action": "new",
            "selected_project": scope.id,
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

    document_index = load_document_index(
        root,
        scope.currency,
        docs_root=scope.docs_root,
        workspace_root=scope.root,
        project_id=scope.id,
    )
    if args.action == "list":
        if args.identifiers:
            raise ValueError("document list does not accept identifiers")
        report = list_documents(
            document_index,
            role=args.role,
            state=args.state,
            state_not=args.state_not,
        )
        data = {"action": "list", "selected_project": scope.id, **report}
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
            "selected_project": scope.id,
            **show_document(
                document_index,
                root,
                args.identifiers[0],
                docs_root=scope.docs_root,
            ),
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
        validate_currency(root, scope.currency, docs_root=scope.docs_root),
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
            "selected_project": scope.id,
            "nodes": graph_data["nodes"],
            "findings": graph_data["findings"],
            "partial": graph.partial,
            "limits": graph_data["limits"],
            "cache": document_index.cache,
        }
    elif args.action == "graph":
        if args.identifiers:
            raise ValueError("document graph does not accept identifiers")
        data = {
            "action": "graph",
            "selected_project": scope.id,
            "graph": graph_data,
            "cache": document_index.cache,
        }
    elif args.action == "trace":
        data = {
            "action": "trace",
            "selected_project": scope.id,
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
            "selected_project": scope.id,
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
