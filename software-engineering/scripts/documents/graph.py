"""Bounded graph projections over validated typed document records."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from heapq import heappop, heappush
from typing import Any

from ..policy.manifest import Check, FitnessDeclaration, Profile
from .contracts import RECORD_ROLES, DocumentContractRecord, state_predicates
from .currency import CurrencyFinding
from .validation import DocumentScan

MAX_GRAPH_NODES = 5_000
MAX_GRAPH_EDGES = 10_000
MAX_TRACE_DEPTH = 32
SUPPORTED_NAMESPACES = (
    *RECORD_ROLES,
    "requirement",
    "criterion",
    "check",
    "evidence",
    "run",
    "release",
    "source",
)


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    state: str
    title: str
    summary: str | None
    provenance: dict[str, Any] | None
    selection: dict[str, Any] | None
    partial: bool


@dataclass(frozen=True)
class GraphEdge:
    source: str
    type: str
    target: str
    provenance: dict[str, Any]
    partial: bool


@dataclass(frozen=True, order=True)
class GraphFinding:
    id: str
    severity: str
    message: str
    path: str
    line: int
    rationale: str
    repair: str
    ci_blocking: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["provenance"] = {"path": data.pop("path"), "line": data.pop("line")}
        return data


@dataclass(frozen=True)
class DocumentGraph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    findings: tuple[GraphFinding, ...]
    partial: bool
    limits: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "nodes": [asdict(item) for item in self.nodes],
            "edges": [asdict(item) for item in self.edges],
            "findings": [item.to_dict() for item in self.findings],
            "partial": self.partial,
            "limits": self.limits,
        }


@dataclass(frozen=True)
class GraphCheck:
    """The check metadata needed for graph projection, without a whole manifest."""

    name: str
    applies_to: tuple[str, ...]
    profiles: tuple[str, ...]
    fitness: tuple[str, ...]


@dataclass(frozen=True)
class TaskGraphNode:
    id: str
    title: str
    state: str
    depends_on: tuple[str, ...]
    parent: str | None
    children: tuple[str, ...]
    open_clarification: bool
    ready: bool
    wave: int | None
    provenance: dict[str, Any]


@dataclass(frozen=True, order=True)
class TaskGraphOrphan:
    task: str
    relationship: str
    target: str
    provenance: str


@dataclass(frozen=True, order=True)
class TaskGraphCycle:
    relationship: str
    tasks: tuple[str, ...]


@dataclass(frozen=True)
class TaskGraph:
    nodes: tuple[TaskGraphNode, ...]
    edges: tuple[dict[str, Any], ...]
    topological_order: tuple[str, ...]
    ready_set: tuple[str, ...]
    waves: tuple[tuple[str, ...], ...]
    cycles: tuple[TaskGraphCycle, ...]
    orphans: tuple[TaskGraphOrphan, ...]
    unresolved_order: tuple[str, ...]
    partial: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "nodes": [asdict(item) for item in self.nodes],
            "edges": list(self.edges),
            "topological_order": list(self.topological_order),
            "ready_set": list(self.ready_set),
            "waves": [
                {"level": level, "tasks": list(tasks)} for level, tasks in enumerate(self.waves)
            ],
            "cycles": [asdict(item) for item in self.cycles],
            "orphans": [asdict(item) for item in self.orphans],
            "unresolved_order": list(self.unresolved_order),
            "partial": self.partial,
        }


def build_task_graph(tasks: Sequence[Mapping[str, Any]]) -> TaskGraph:
    """Project task scheduling and hierarchy relationships without mutating source files."""
    tasks_by_id: dict[str, Mapping[str, Any]] = {}
    for task in tasks:
        tasks_by_id.setdefault(str(task["id"]), task)

    dependency_adjacency: dict[str, set[str]] = {task_id: set() for task_id in tasks_by_id}
    parent_adjacency: dict[str, set[str]] = {task_id: set() for task_id in tasks_by_id}
    outgoing: dict[str, set[str]] = {task_id: set() for task_id in tasks_by_id}
    indegree = {task_id: 0 for task_id in tasks_by_id}
    children: dict[str, set[str]] = {task_id: set() for task_id in tasks_by_id}
    edges: list[dict[str, Any]] = []
    orphans: list[TaskGraphOrphan] = []

    for task_id, task in tasks_by_id.items():
        provenance = _task_provenance_path(task)
        for dependency in _task_dependencies(task):
            resolved = dependency in tasks_by_id
            edges.append(
                {
                    "source": dependency,
                    "target": task_id,
                    "relationship": "depends_on",
                    "resolved": resolved,
                }
            )
            if not resolved:
                orphans.append(TaskGraphOrphan(task_id, "depends_on", dependency, provenance))
                continue
            dependency_adjacency[task_id].add(dependency)
            if task_id not in outgoing[dependency]:
                outgoing[dependency].add(task_id)
                indegree[task_id] += 1
        parent_value = task.get("parent")
        parent = str(parent_value) if parent_value not in {None, ""} else None
        if parent is None:
            continue
        resolved = parent in tasks_by_id
        edges.append(
            {
                "source": parent,
                "target": task_id,
                "relationship": "parent",
                "resolved": resolved,
            }
        )
        if not resolved:
            orphans.append(TaskGraphOrphan(task_id, "parent", parent, provenance))
            continue
        parent_adjacency[task_id].add(parent)
        children[parent].add(task_id)

    queue: list[str] = []
    levels = {task_id: 0 for task_id, degree in indegree.items() if degree == 0}
    for task_id, degree in indegree.items():
        if degree == 0:
            heappush(queue, task_id)
    order: list[str] = []
    while queue:
        current = heappop(queue)
        order.append(current)
        for dependent in sorted(outgoing[current]):
            levels[dependent] = max(levels.get(dependent, 0), levels[current] + 1)
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heappush(queue, dependent)

    unresolved_order = tuple(sorted(set(tasks_by_id) - set(order)))
    dependency_cycles = tuple(
        TaskGraphCycle("depends_on", cycle) for cycle in _task_cycles(dependency_adjacency)
    )
    parent_cycles = tuple(
        TaskGraphCycle("parent", cycle) for cycle in _task_cycles(parent_adjacency)
    )
    cycles = tuple(sorted((*dependency_cycles, *parent_cycles)))
    ready: list[str] = []
    nodes: list[TaskGraphNode] = []
    for task_id, task in sorted(tasks_by_id.items()):
        predicates = state_predicates(str(task.get("status", "unknown")))
        dependencies = _task_dependencies(task)
        dependencies_succeeded = all(
            dependency in tasks_by_id
            and state_predicates(str(tasks_by_id[dependency].get("status", "unknown")))[
                "is_terminal_success"
            ]
            for dependency in dependencies
        )
        is_ready = (
            predicates["is_open"]
            and dependencies_succeeded
            and not bool(task.get("open_clarification", False))
        )
        if is_ready:
            ready.append(task_id)
        parent_value = task.get("parent")
        nodes.append(
            TaskGraphNode(
                id=task_id,
                title=str(task.get("title", task_id)),
                state=str(task.get("status", "unknown")),
                depends_on=dependencies,
                parent=str(parent_value) if parent_value not in {None, ""} else None,
                children=tuple(sorted(children[task_id])),
                open_clarification=bool(task.get("open_clarification", False)),
                ready=is_ready,
                wave=levels.get(task_id),
                provenance=dict(task.get("provenance", {})),
            )
        )

    waves = tuple(
        tuple(sorted(task_id for task_id, level in levels.items() if level == wave))
        for wave in range(max(levels.values(), default=-1) + 1)
    )
    normalized_orphans = tuple(sorted(set(orphans)))
    return TaskGraph(
        nodes=tuple(nodes),
        edges=tuple(
            sorted(
                edges,
                key=lambda item: (
                    item["relationship"],
                    item["source"],
                    item["target"],
                ),
            )
        ),
        topological_order=tuple(order),
        ready_set=tuple(ready),
        waves=waves,
        cycles=cycles,
        orphans=normalized_orphans,
        unresolved_order=unresolved_order,
        partial=bool(cycles or normalized_orphans or unresolved_order),
    )


def render_task_graph_readme(graph: TaskGraph) -> str:
    """Render the read-only graph projection as a regenerable tasks/README.md view."""
    nodes = {item.id: item for item in graph.nodes}
    lines = [
        "# Task DAG",
        "",
        "<!-- Generated by `engineering task graph`; do not edit this projection by hand. -->",
        "",
        "## Ready set",
        "",
    ]
    lines.extend(_task_lines(graph.ready_set, nodes))
    lines.extend(("", "## Topological order", ""))
    if graph.topological_order:
        lines.extend(
            f"{index}. `{task_id}` — {nodes[task_id].title} ({nodes[task_id].state})"
            for index, task_id in enumerate(graph.topological_order, start=1)
        )
    else:
        lines.append("- None")
    lines.extend(("", "## Waves", ""))
    if graph.waves:
        for level, tasks in enumerate(graph.waves):
            lines.extend((f"### Wave {level}", "", *_task_lines(tasks, nodes), ""))
    else:
        lines.extend(("- None", ""))
    lines.extend(("## Parent hierarchy", ""))
    parents = [item for item in graph.nodes if item.children]
    if parents:
        for item in parents:
            lines.append(f"- `{item.id}` → {', '.join(f'`{child}`' for child in item.children)}")
    else:
        lines.append("- None")
    lines.extend(("", "## Cycles", ""))
    if graph.cycles:
        for cycle in graph.cycles:
            path = " → ".join((*cycle.tasks, cycle.tasks[0]))
            lines.append(f"- `{cycle.relationship}`: {path}")
    else:
        lines.append("- None")
    lines.extend(("", "## Orphans", ""))
    if graph.orphans:
        for orphan in graph.orphans:
            lines.append(
                f"- `{orphan.task}` {orphan.relationship} target `{orphan.target}` is missing "
                f"(`{orphan.provenance}`)"
            )
    else:
        lines.append("- None")
    if graph.unresolved_order:
        lines.extend(
            (
                "",
                "## Unresolved topological order",
                "",
                *[f"- `{task_id}`" for task_id in graph.unresolved_order],
            )
        )
    return "\n".join(lines)


def _task_lines(task_ids: Sequence[str], nodes: Mapping[str, TaskGraphNode]) -> list[str]:
    return [
        f"- `{task_id}` — {nodes[task_id].title} ({nodes[task_id].state})" for task_id in task_ids
    ] or ["- None"]


def _task_provenance_path(task: Mapping[str, Any]) -> str:
    provenance = task.get("provenance")
    return str(provenance.get("path", ".")) if isinstance(provenance, Mapping) else "."


def _task_dependencies(task: Mapping[str, Any]) -> tuple[str, ...]:
    declared = task.get("scheduling_dependencies", task.get("dependencies", ()))
    return tuple(dict.fromkeys(str(item) for item in declared))


def _task_cycles(adjacency: Mapping[str, set[str]]) -> tuple[tuple[str, ...], ...]:
    cycles: set[tuple[str, ...]] = set()
    color: dict[str, int] = {}
    parent: dict[str, str] = {}
    for origin in sorted(adjacency):
        if color.get(origin, 0):
            continue
        color[origin] = 1
        stack: list[tuple[str, Any]] = [(origin, iter(sorted(adjacency.get(origin, ()))))]
        while stack:
            current, neighbors = stack[-1]
            try:
                target = next(neighbors)
            except StopIteration:
                color[current] = 2
                stack.pop()
                continue
            if color.get(target, 0) == 0:
                parent[target] = current
                color[target] = 1
                stack.append((target, iter(sorted(adjacency.get(target, ())))))
            elif color[target] == 1:
                reverse = [current]
                while reverse[-1] != target:
                    reverse.append(parent[reverse[-1]])
                cycle = tuple(reversed(reverse))
                first = min(range(len(cycle)), key=cycle.__getitem__)
                cycles.add(cycle[first:] + cycle[:first])
    return tuple(sorted(cycles))


def graph_checks(
    checks: Mapping[str, Check],
    profiles: Mapping[str, Profile],
    fitness: Sequence[FitnessDeclaration],
) -> tuple[GraphCheck, ...]:
    """Project manifest check declarations into the graph domain's narrow input."""
    return tuple(
        GraphCheck(
            name,
            check.applies_to,
            tuple(
                sorted(
                    profile
                    for profile, declaration in profiles.items()
                    if name in declaration.checks
                )
            ),
            tuple(sorted(item.name for item in fitness if item.check == name)),
        )
        for name, check in sorted(checks.items())
    )


def build_document_graph(
    scan: DocumentScan,
    currency_findings: Sequence[CurrencyFinding],
    checks: Sequence[GraphCheck],
) -> DocumentGraph:
    """Project one validated document scan; this function never reparses repository files."""
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    findings = [
        *(_scan_finding(item) for item in currency_findings),
        *(_scan_finding(item) for item in scan.findings),
    ]
    selections = {item.source: item for item in scan.selections}
    projections = {item.source: item for item in scan.projections}
    records: dict[str, DocumentContractRecord] = {}
    truncated = False

    for record in scan.records:
        identity = _record_id(record)
        selection = selections.get(record.source)
        projection = projections.get(record.source)
        records[identity] = record
        if not _add_node(
            nodes,
            GraphNode(
                identity,
                str(record.metadata["role"]),
                str(record.metadata["state"]),
                str(record.metadata["title"]),
                projection.summary if projection else None,
                {"path": record.source, "line": 1},
                asdict(selection) if selection else None,
                False,
            ),
        ):
            truncated = True
            break

    for check in checks:
        if not _add_node(
            nodes,
            GraphNode(
                f"check:{check.name}",
                "check",
                "declared",
                check.name,
                None,
                {"path": "engineering.yaml", "line": 1},
                {
                    "source": f"engineering.yaml#checks.{check.name}",
                    "precedence": "explicit-manifest",
                    "applies_to": list(check.applies_to),
                    "profiles": list(check.profiles),
                    "fitness": list(check.fitness),
                },
                False,
            ),
        ):
            truncated = True
            break

    seen_edges: dict[tuple[str, str, str], GraphEdge] = {}
    for record in scan.records:
        source = _record_id(record)
        for index, relationship in enumerate(record.metadata["relationships"]):
            edge = GraphEdge(
                source,
                relationship["type"],
                relationship["target"],
                {
                    "path": record.source,
                    "line": 1,
                    "field": f"relationships[{index}]",
                    "declared": True,
                },
                False,
            )
            truncated |= not _add_edge(edge, nodes, edges, seen_edges, records, findings)

    if truncated:
        findings.append(
            _finding(
                "graph.truncated",
                "error",
                "graph construction reached a configured node or edge bound",
                ".",
                "bounded graph construction cannot claim complete traversal",
                "reduce the adopted scope or split the graph before retrying",
            )
        )

    connected = {edge.source for edge in edges} | {edge.target for edge in edges}
    for identity, record in records.items():
        if identity not in connected:
            findings.append(
                _finding(
                    "graph.orphan-document",
                    "warning",
                    f"{identity} has no recorded inbound or outbound relationship",
                    record.source,
                    "an isolated record cannot participate in impact or trace navigation",
                    "review whether an explicit relationship is warranted; do not invent one",
                    ci_blocking=False,
                )
            )
    findings.extend(_cycle_findings(edges, records))
    normalized_findings = tuple(sorted(set(findings)))
    normalized_nodes = tuple(nodes[key] for key in sorted(nodes))
    normalized_edges = tuple(
        sorted(
            edges,
            key=lambda item: (
                item.source,
                item.type,
                item.target,
                item.provenance["field"],
            ),
        )
    )
    return DocumentGraph(
        normalized_nodes,
        normalized_edges,
        normalized_findings,
        scan.partial
        or truncated
        or any(item.partial for item in normalized_nodes)
        or bool(normalized_findings),
        {
            "max_nodes": MAX_GRAPH_NODES,
            "max_edges": MAX_GRAPH_EDGES,
            "max_trace_depth": MAX_TRACE_DEPTH,
        },
    )


def trace_graph(
    graph: DocumentGraph,
    starts: tuple[str, ...],
    *,
    direction: str = "both",
    max_depth: int = 8,
) -> dict[str, Any]:
    if not starts:
        raise ValueError("document trace requires at least one identifier")
    if direction not in {"inbound", "outbound", "both"}:
        raise ValueError("direction must be inbound, outbound, or both")
    if max_depth < 0 or max_depth > MAX_TRACE_DEPTH:
        raise ValueError(f"max depth must be between 0 and {MAX_TRACE_DEPTH}")
    nodes = {item.id: item for item in graph.nodes}
    unknown = sorted(set(starts) - nodes.keys())
    if unknown:
        raise KeyError(f"unknown graph identifiers: {unknown}")
    adjacency: dict[str, list[tuple[str, GraphEdge, str]]] = {}
    for edge in graph.edges:
        if direction in {"outbound", "both"}:
            adjacency.setdefault(edge.source, []).append((edge.target, edge, "outbound"))
        if direction in {"inbound", "both"}:
            adjacency.setdefault(edge.target, []).append((edge.source, edge, "inbound"))
    visited = {item: 0 for item in starts}
    queue = deque(sorted(starts))
    traversals: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str, str]] = set()
    depth_truncated = False
    while queue:
        current = queue.popleft()
        depth = visited[current]
        if depth >= max_depth:
            if any(
                target not in visited for target, _edge, _direction in adjacency.get(current, ())
            ):
                depth_truncated = True
            continue
        for target, edge, traversal_direction in sorted(
            adjacency.get(current, ()),
            key=lambda item: (item[0], item[1].type, item[2]),
        ):
            edge_key = (
                edge.source,
                edge.type,
                edge.target,
                str(edge.provenance["field"]),
            )
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            next_depth = depth + 1
            traversals.append(
                {
                    "from": current,
                    "to": target,
                    "depth": next_depth,
                    "direction": traversal_direction,
                    "edge": asdict(edge),
                }
            )
            if target not in visited:
                visited[target] = next_depth
                queue.append(target)
    return {
        "starts": list(dict.fromkeys(starts)),
        "direction": direction,
        "max_depth": max_depth,
        "nodes": [
            {**asdict(nodes[identity]), "distance": distance}
            for identity, distance in sorted(visited.items(), key=lambda item: (item[1], item[0]))
        ],
        "traversals": traversals,
        "partial": graph.partial or depth_truncated,
    }


def explain_graph_node(graph: DocumentGraph, identifier: str) -> dict[str, Any]:
    nodes = {item.id: item for item in graph.nodes}
    if identifier not in nodes:
        raise KeyError(f"unknown graph identifier: {identifier}")
    inbound = [asdict(item) for item in graph.edges if item.target == identifier]
    outbound = [asdict(item) for item in graph.edges if item.source == identifier]
    return {
        "node": asdict(nodes[identifier]),
        "selected_because": nodes[identifier].selection,
        "precedence": (
            nodes[identifier].selection.get(
                "precedence",
                nodes[identifier].selection.get("registry_precedence"),
            )
            if nodes[identifier].selection
            else None
        ),
        "inbound": inbound,
        "outbound": outbound,
        "omissions": [
            "No prose-inferred relationships are included.",
            "External evidence/source/release nodes remain partial unless represented by adopted records.",
        ],
    }


def _add_node(nodes: dict[str, GraphNode], node: GraphNode) -> bool:
    if node.id in nodes:
        return True
    if len(nodes) >= MAX_GRAPH_NODES:
        return False
    nodes[node.id] = node
    return True


def _add_edge(
    edge: GraphEdge,
    nodes: dict[str, GraphNode],
    edges: list[GraphEdge],
    seen: dict[tuple[str, str, str], GraphEdge],
    records: dict[str, DocumentContractRecord],
    findings: list[GraphFinding],
) -> bool:
    if len(edges) >= MAX_GRAPH_EDGES:
        return False
    key = (edge.source, edge.type, edge.target)
    if key in seen:
        findings.append(
            _finding(
                "graph.duplicate-edge",
                "error",
                f"duplicate edge {edge.source} {edge.type} {edge.target}",
                edge.provenance["path"],
                "duplicate graph edges inflate trace evidence and can carry conflicting provenance",
                "retain one authoritative field for the relationship",
            )
        )
        return True
    seen[key] = edge
    namespace = edge.target.split(":", 1)[0]
    if namespace not in SUPPORTED_NAMESPACES:
        findings.append(
            _finding(
                "graph.unknown-namespace",
                "error",
                f"unsupported relationship namespace {namespace!r} in {edge.target}",
                edge.provenance["path"],
                "unknown namespaces have no stable graph or resolution semantics",
                "use a supported namespace or version the graph contract",
            )
        )
    if edge.target not in nodes:
        if namespace in RECORD_ROLES or namespace == "check":
            findings.append(
                _finding(
                    "graph.broken-target",
                    "error",
                    f"{edge.source} {edge.type} target {edge.target} is missing",
                    edge.provenance["path"],
                    "a locally owned relationship must resolve in the adopted graph",
                    "add the declared target or repair/remove the stale edge",
                )
            )
        if not _add_node(
            nodes,
            GraphNode(
                edge.target,
                namespace,
                "external-unverified",
                edge.target,
                None,
                None,
                None,
                True,
            ),
        ):
            return False
    target_record = records.get(edge.target)
    if target_record is not None and target_record.metadata["state"] == "superseded":
        findings.append(
            _finding(
                "graph.target-superseded",
                "warning",
                f"{edge.source} points to superseded target {edge.target}",
                edge.provenance["path"],
                "historical targets may not represent current authority",
                "review the successor chain and update the edge when current authority is intended",
                ci_blocking=False,
            )
        )
    edges.append(edge)
    return True


def _cycle_findings(
    edges: list[GraphEdge],
    records: dict[str, DocumentContractRecord],
) -> tuple[GraphFinding, ...]:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if edge.target in records:
            adjacency.setdefault(edge.source, set()).add(edge.target)
    cycles: set[tuple[str, ...]] = set()
    color: dict[str, int] = {}
    parent: dict[str, str] = {}
    for origin in sorted(adjacency):
        if color.get(origin, 0):
            continue
        color[origin] = 1
        stack: list[tuple[str, Any]] = [(origin, iter(sorted(adjacency.get(origin, ()))))]
        while stack:
            current, neighbors = stack[-1]
            try:
                target = next(neighbors)
            except StopIteration:
                color[current] = 2
                stack.pop()
                continue
            if color.get(target, 0) == 0:
                parent[target] = current
                color[target] = 1
                stack.append((target, iter(sorted(adjacency.get(target, ())))))
            elif color[target] == 1:
                reverse = [current]
                while reverse[-1] != target:
                    reverse.append(parent[reverse[-1]])
                cycle = tuple(reversed(reverse))
                first = min(range(len(cycle)), key=cycle.__getitem__)
                cycles.add(cycle[first:] + cycle[:first])
    return tuple(
        _finding(
            "graph.cycle",
            "error",
            "relationship cycle: " + " -> ".join((*cycle, cycle[0])),
            records[cycle[0]].source,
            "directed cycles make precedence and impact traversal ambiguous",
            "review edge direction and remove the relationship that closes the unintended cycle",
        )
        for cycle in sorted(cycles)
    )


def _record_id(record: DocumentContractRecord) -> str:
    return f"{record.metadata['role']}:{record.metadata['id']}"


def _scan_finding(item: Any) -> GraphFinding:
    return GraphFinding(
        item.code,
        item.severity,
        item.message,
        item.path,
        item.line,
        item.rationale,
        item.repair,
        item.ci_blocking,
    )


def _finding(
    identifier: str,
    severity: str,
    message: str,
    path: str,
    rationale: str,
    repair: str,
    *,
    ci_blocking: bool = True,
) -> GraphFinding:
    return GraphFinding(
        identifier,
        severity,
        message,
        path,
        1,
        rationale,
        repair,
        ci_blocking,
    )
