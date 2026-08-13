"""Bounded graph projections over validated typed document records."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from ..policy.manifest import Check, FitnessDeclaration, Profile
from .contracts import RECORD_ROLES, DocumentContractRecord
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
