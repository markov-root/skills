"""Read-only task-DAG projection adapter."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from typing import Any

from ..documents.graph import build_task_graph, render_task_graph_readme
from ..documents.query import inventory
from ..policy.document_selection import resolve_document_selection
from ..policy.manifest import ManifestV2
from .contracts import (
    EXIT_CHECK_FAILED,
    EXIT_OK,
    CommandResult,
    CommandSpec,
    explanation,
)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        choices=("graph", "next"),
        help=(
            "graph projects the task DAG; next returns an advisory, read-only ready-ticket "
            "suggestion with no mutual-exclusion guarantee"
        ),
    )
    parser.add_argument(
        "--project",
        metavar="ID",
        help="select one manifest-v2 document project",
    )


def handle(args: argparse.Namespace) -> CommandResult:
    selection = resolve_document_selection(
        args.project_root,
        action="query",
        project_id=args.project,
    )
    root = selection.repository_root.resolve()
    if isinstance(selection.manifest, ManifestV2):
        scope = selection.selected_project
        if scope is None:
            raise AssertionError("task graph selection did not resolve one project")
        report = inventory(
            root,
            scope.task_inventory,
            docs_root=scope.docs_root,
            include_graph_metadata=True,
        )
        selected_project = scope.id
    else:
        policy = selection.manifest.task_inventory if selection.manifest is not None else None
        report = inventory(root, policy, include_graph_metadata=True)
        selected_project = None

    graph = build_task_graph(report["tasks"])
    if args.action == "next":
        ready = _ordered_ready_tasks(report["tasks"], graph.ready_set)
        limitations = [
            "The ready-ticket suggestion is advisory.",
            "The command is read-only and performs no writes or task-state mutation.",
            "The command guarantees no mutual exclusion and does not claim, lock, or dispatch tasks.",
        ]
        data = {
            "action": "next",
            "root_resolution": selection.to_dict(),
            "ready": ready,
            "source_findings": report["findings"],
            "limitations": limitations,
        }
        if selected_project is not None:
            data["selected_project"] = selected_project
        return CommandResult(
            "partial" if graph.partial or report["status"] == "partial" else "passed",
            root,
            data,
            EXIT_OK,
            _render_next(ready),
        )

    graph_data = graph.to_dict()
    failed = bool(graph.cycles or graph.orphans)
    data = {
        "action": "graph",
        "root_resolution": selection.to_dict(),
        "graph": graph_data,
        "source_findings": report["findings"],
        "limitations": [
            "Only declared depends_on and parent frontmatter relationships are projected.",
            "Ready means open, all declared dependencies terminal-success, and no open clarification marker.",
            "Parent hierarchy does not imply execution precedence; waves use depends_on only.",
            "The command performs no writes, locking, claims, dispatch, or scheduling mutation.",
        ],
    }
    if selected_project is not None:
        data["selected_project"] = selected_project
    return CommandResult(
        "failed" if failed else ("partial" if report["status"] == "partial" else "passed"),
        root,
        data,
        EXIT_CHECK_FAILED if failed else EXIT_OK,
        render_task_graph_readme(graph),
    )


SPEC = CommandSpec(
    "task",
    "project the task DAG or suggest advisory read-only next-ready tickets",
    configure,
    handle,
    explanation(
        "task",
        "Task dependency graph and next-ready suggestion",
        "Project task topological order, ready-set, waves, hierarchy, cycles, and orphaned references, or suggest ordered ready tickets, read-only.",
        (
            "declared task dependencies must be scheduled or reviewed",
            "a tasks/README.md DAG projection must be regenerated deterministically",
            "dependency or parent cycles and missing targets must be detected",
            "engineering task next should provide an advisory ordered suggestion from the current ready-set",
        ),
        (
            "claiming, locking, dispatching, or mutating task state",
            "treating parent hierarchy or touches hints as mergeability guarantees",
            "requiring mutual exclusion or proof that a suggested ticket is unclaimed",
        ),
        evidence=(
            "versioned JSON task graph with topological order, ready-set, waves, cycles, and orphans",
            "Markdown output suitable for a derived tasks/README.md projection",
            "ordered advisory ready-ticket JSON with optional priority and size hints",
        ),
        limitations=(
            "undeclared dependencies cannot be inferred from prose",
            "readiness is advisory and does not establish worktree isolation or merge safety",
            "task next is read-only and guarantees no mutual exclusion, claim, lock, or dispatch",
        ),
        next_commands=(
            "engineering task graph --json",
            "engineering task next --json",
            "engineering task graph > docs/tasks/README.md",
        ),
        references=(
            "docs/context/task-inventory.md",
            "docs/adr/0025-ratify-the-agent-scale-ticketing-and-records-design-v2.md",
        ),
    ),
)


_PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2}
_SIZE_ORDER = {"xs": 0, "s": 1, "m": 2, "l": 3}


def _ordered_ready_tasks(
    tasks: Sequence[Mapping[str, Any]], ready_set: Sequence[str]
) -> list[dict[str, str | None]]:
    tasks_by_id: dict[str, Mapping[str, Any]] = {}
    for task in tasks:
        tasks_by_id.setdefault(str(task["id"]), task)
    ready = [
        {
            "id": task_id,
            "title": str(tasks_by_id[task_id].get("title", task_id)),
            "priority": _task_detail(tasks_by_id[task_id], "priority"),
            "size": _task_detail(tasks_by_id[task_id], "size"),
        }
        for task_id in ready_set
    ]
    return sorted(
        ready,
        key=lambda task: (
            _PRIORITY_ORDER.get(task["priority"], len(_PRIORITY_ORDER)),
            _SIZE_ORDER.get(task["size"], len(_SIZE_ORDER)),
            task["id"],
        ),
    )


def _task_detail(task: Mapping[str, Any], field: str) -> str | None:
    details = task.get("details")
    if not isinstance(details, Mapping):
        return None
    value = details.get(field)
    return value if isinstance(value, str) and value else None


def _render_next(ready: Sequence[Mapping[str, str | None]]) -> str:
    lines = [
        "Advisory, read-only ready tickets (no mutual-exclusion guarantee):",
    ]
    if not ready:
        return "\n".join((*lines, "- No ready tickets."))
    for index, task in enumerate(ready, start=1):
        hints = [
            f"{field} {task[field]}" for field in ("priority", "size") if task[field] is not None
        ]
        suffix = f" ({', '.join(hints)})" if hints else ""
        lines.append(f"{index}. `{task['id']}` — {task['title']}{suffix}")
    return "\n".join(lines)
