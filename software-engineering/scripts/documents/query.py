"""Read-only, provenance-preserving document query projections."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml

from ..policy.manifest import TaskInventoryPolicy, TaskPlanningPolicy

SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 1_000_000
MAX_DOCUMENTS = 2_000
KNOWN_STATUSES = {"todo", "partial", "blocked", "done"}
_STATUS = re.compile(r"^\s*[-*]?\s*Status\s*:\s*(.+?)\s*$", re.IGNORECASE)
_DEPENDS = re.compile(r"^\s*[-*]?\s*Depends\s+on\s*:\s*(.+?)\s*$", re.IGNORECASE)
_PLANNING = re.compile(r"^\s*[-*]\s+X-Planning\s*:\s*(.*?)\s*$", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(?:\[([ xX])\]\s+)?(.+?)\s*$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_TASK_ID = re.compile(r"(?<!\d)(\d{4})(?!\d)")
_RANGE = re.compile(r"(?<!\d)(\d{4})\s*[–-]\s*(\d{4})(?!\d)")


@dataclass(frozen=True)
class Provenance:
    path: str
    line: int


@dataclass(frozen=True)
class Criterion:
    text: str
    checked: bool | None
    provenance: Provenance


@dataclass(frozen=True)
class DocumentLink:
    label: str
    target: str
    kind: str
    exists: bool | None
    provenance: Provenance


@dataclass(frozen=True)
class PlanningValue:
    value: str
    provenance: Provenance


@dataclass(frozen=True)
class InventoryFinding:
    code: str
    severity: str
    message: str
    provenance: Provenance
    task_id: str | None = None


@dataclass(frozen=True)
class TaskRecord:
    id: str
    title: str
    summary: str | None
    summary_provenance: Provenance | None
    status: str
    status_explicit: bool
    dependencies: tuple[str, ...]
    dependency_text: str | None
    acceptance: tuple[Criterion, ...]
    evidence: tuple[Criterion, ...]
    links: tuple[DocumentLink, ...]
    extraction: str
    format: str
    provenance: Provenance
    planning: dict[str, PlanningValue]


@dataclass(frozen=True)
class HandoffRecord:
    path: str
    title: str
    state: str
    referenced_tasks: tuple[str, ...]
    next_tasks: tuple[str, ...]
    links: tuple[DocumentLink, ...]
    provenance: Provenance


def inventory(
    root: Path,
    policy: TaskInventoryPolicy | None = None,
) -> dict[str, Any]:
    """Inventory task/handoff Markdown without mutating or inferring project state."""
    root = root.resolve()
    policy = policy or TaskInventoryPolicy()
    findings: list[InventoryFinding] = []
    task_paths = tuple(
        path
        for path in _expand(root, policy.include, findings, "task")
        if path.stem.lower() not in {"readme", "index"}
    )
    handoff_paths = tuple(
        path
        for path in _expand(root, policy.handoffs, findings, "handoff")
        if path.stem.lower() not in {"readme", "index"}
    )
    decision_paths = tuple(
        path
        for path in _expand(root, policy.decisions, findings, "decision")
        if path.stem.lower() not in {"readme", "index"}
    )
    decision_ids = {
        match.group(1)
        for path in decision_paths
        if (match := _TASK_ID.search(path.stem)) is not None
    }

    tasks = [
        _parse_task(root, path, decision_ids, findings, policy.planning) for path in task_paths
    ]
    tasks_by_id: dict[str, TaskRecord] = {}
    for task in tasks:
        if existing := tasks_by_id.get(task.id):
            findings.append(
                InventoryFinding(
                    "task.duplicate-id",
                    "error",
                    f"task ID {task.id} is also declared by {existing.provenance.path}",
                    task.provenance,
                    task.id,
                )
            )
        else:
            tasks_by_id[task.id] = task
    _dependency_findings(tasks, tasks_by_id, findings)

    handoffs = [
        _parse_handoff(root, path, tasks_by_id, decision_ids, findings) for path in handoff_paths
    ]
    summary = {
        "task_count": len(tasks),
        "status_counts": {
            status: sum(task.status == status for task in tasks)
            for status in (*sorted(KNOWN_STATUSES), "unknown")
        },
        "partial_extractions": sum(task.extraction == "partial" for task in tasks),
        "contradictions": sum(item.severity == "error" for item in findings),
        "stale_handoffs": sum(item.state == "stale" for item in handoffs),
    }
    sources: dict[str, Any] = {
        "task_globs": list(policy.include),
        "handoff_globs": list(policy.handoffs),
        "decision_globs": list(policy.decisions),
    }
    if policy.planning is not None:
        sources["planning_contract"] = _planning_contract(policy.planning)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "partial"
        if findings or any(task.extraction == "partial" for task in tasks)
        else "complete",
        "root": str(root),
        "sources": sources,
        "summary": summary,
        "tasks": [_task_json(item) for item in tasks],
        "handoffs": [_jsonable(asdict(item)) for item in handoffs],
        "findings": [_jsonable(asdict(item)) for item in sorted(findings, key=_finding_key)],
    }


def compact(
    report: dict[str, Any],
    planning: TaskPlanningPolicy | None = None,
    *,
    filters: tuple[str, ...] = (),
    order_by: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Project a full inventory into a bounded dependency-aware planning view."""
    if (filters or order_by) and planning is None:
        raise ValueError("planning filters and ordering require an adopted task planning contract")
    parsed_filters = _planning_filters(filters, planning)
    selected_order = _planning_order(order_by, planning)
    all_tasks = report["tasks"]
    tasks = [
        item
        for item in all_tasks
        if all(
            item.get("planning", {}).get(field, {}).get("value") == value
            for field, value in parsed_filters
        )
    ]
    status_by_id = {item["id"]: item["status"] for item in all_tasks}
    buckets: dict[str, list[dict[str, Any]]] = {
        "actionable": [],
        "dependency_blocked": [],
        "declared_blocked": [],
        "needs_inspection": [],
    }
    completed = sum(item["status"] == "done" for item in all_tasks)
    for item in tasks:
        if item["status"] == "done":
            continue
        incomplete = [
            dependency
            for dependency in item["dependencies"]
            if status_by_id.get(dependency) != "done"
        ]
        row = {
            "id": item["id"],
            "title": item["title"],
            "summary": item["summary"],
            "summary_provenance": item["summary_provenance"],
            "status": item["status"],
            "dependencies": item["dependencies"],
            "incomplete_dependencies": incomplete,
            "provenance": item["provenance"],
        }
        if item.get("planning"):
            row["planning"] = item["planning"]
        if item["status"] == "blocked":
            buckets["declared_blocked"].append(row)
        elif item["status"] == "unknown" or item["extraction"] == "partial":
            buckets["needs_inspection"].append(row)
        elif incomplete:
            buckets["dependency_blocked"].append(row)
        else:
            buckets["actionable"].append(row)

    if selected_order:
        for rows in buckets.values():
            rows.sort(key=lambda item: _planning_sort_key(item, selected_order, planning))

    errors = [
        {
            "code": item["code"],
            "task_id": item["task_id"],
            "provenance": item["provenance"],
        }
        for item in report["findings"]
        if item["severity"] == "error"
    ]
    compact_report = {
        "schema_version": report["schema_version"],
        "status": report["status"],
        "root": report["root"],
        "view": "compact",
        "summary": {
            **report["summary"],
            "completed": completed,
            **({"selected_task_count": len(tasks)} if parsed_filters else {}),
            **{f"{name}_count": len(rows) for name, rows in buckets.items()},
        },
        **buckets,
        "error_findings": errors[:100],
        "error_findings_truncated": len(errors) > 100,
        "limitations": [
            "Readiness is derived only from explicit status and declared dependencies.",
            "An explicitly blocked task remains blocked even when its dependencies are done.",
            "Read the source task before implementation; acceptance and blocker prose are omitted.",
        ],
    }
    if planning is not None:
        compact_report["planning_rule"] = {
            "extension": "x-planning",
            "fields": _planning_contract(planning)["fields"],
            "filters": [{"field": field, "value": value} for field, value in parsed_filters],
            "order_by": list(selected_order),
            "default_order_applied": bool(not order_by and planning.default_order),
            "missing_values": "last",
            "tie_breaker": "task-id" if selected_order else "source-path",
        }
    return compact_report


def _parse_task(
    root: Path,
    path: Path,
    decision_ids: set[str],
    findings: list[InventoryFinding],
    planning_policy: TaskPlanningPolicy | None,
) -> TaskRecord:
    relative = path.relative_to(root).as_posix()
    text = _read(path, relative, findings)
    lines = text.splitlines()
    frontmatter, body_start = _frontmatter(lines)
    title, title_line = _title(lines, body_start, path.stem)
    identifier = _identifier(path, title, frontmatter)
    summary, summary_provenance = _projection_summary(lines, frontmatter, relative)
    status, status_explicit, status_line = _status(lines, frontmatter)
    dependency_text, _dependency_line = _dependency_text(lines, frontmatter)
    dependencies = _dependency_ids(dependency_text or "")
    sections = _sections(lines)
    acceptance = _section_criteria(lines, sections, {"done when", "acceptance criteria"}, relative)
    evidence = _section_criteria(lines, sections, {"evidence", "verification"}, relative)
    links = _links(root, path, lines, sections, decision_ids, findings)
    format_name = (
        "typed"
        if _typed_metadata(frontmatter)
        else (
            "frontmatter"
            if frontmatter
            else ("contract-v1" if status_explicit and acceptance else "legacy")
        )
    )
    extraction = "complete" if status_explicit else "partial"
    planning, planning_valid = _planning_metadata(
        lines,
        frontmatter,
        body_start,
        relative,
        identifier,
        planning_policy,
        findings,
    )
    if not planning_valid:
        extraction = "partial"
    if not status_explicit:
        findings.append(
            InventoryFinding(
                "task.status-unknown",
                "warning",
                "no explicit task status was found; checkbox state was not promoted to status",
                Provenance(relative, title_line),
                identifier,
            )
        )
    if status not in KNOWN_STATUSES and status != "unknown":
        findings.append(
            InventoryFinding(
                "task.status-unrecognized",
                "warning",
                f"unrecognized explicit status {status!r}",
                Provenance(relative, status_line),
                identifier,
            )
        )
        extraction = "partial"
    explicitly_checked = [item.checked for item in acceptance if item.checked is not None]
    if (
        status in {"todo", "partial", "blocked"}
        and explicitly_checked
        and all(explicitly_checked)
        and evidence
    ):
        findings.append(
            InventoryFinding(
                "task.status-evidence-contradiction",
                "error",
                (
                    f"explicit status {status!r} conflicts with fully checked acceptance "
                    "criteria plus recorded evidence; status remains authoritative"
                ),
                Provenance(relative, status_line),
                identifier,
            )
        )
    if status == "done" and any(item.checked is False for item in acceptance):
        findings.append(
            InventoryFinding(
                "task.unchecked-acceptance",
                "info",
                (
                    "done task contains unchecked acceptance boxes; this is reported for review "
                    "but is not treated as proof of incompletion"
                ),
                Provenance(relative, status_line),
                identifier,
            )
        )
    return TaskRecord(
        id=identifier,
        title=title,
        summary=summary,
        summary_provenance=summary_provenance,
        status=status,
        status_explicit=status_explicit,
        dependencies=dependencies,
        dependency_text=dependency_text,
        acceptance=acceptance,
        evidence=evidence,
        links=links,
        extraction=extraction,
        format=format_name,
        provenance=Provenance(relative, title_line),
        planning=planning,
    )


def _parse_handoff(
    root: Path,
    path: Path,
    tasks: dict[str, TaskRecord],
    decision_ids: set[str],
    findings: list[InventoryFinding],
) -> HandoffRecord:
    relative = path.relative_to(root).as_posix()
    text = _read(path, relative, findings)
    lines = text.splitlines()
    title, title_line = _title(lines, 0, path.stem)
    sections = _sections(lines)
    referenced = tuple(
        task_id for task_id in dict.fromkeys(_TASK_ID.findall(text)) if task_id in tasks
    )
    next_ids: list[str] = []
    for heading, (start, end) in sections.items():
        if any(token in heading for token in ("next", "resume", "current implementation")):
            next_ids.extend(_TASK_ID.findall("\n".join(lines[start:end])))
    for line in lines:
        if re.search(
            r"\b(next|resume|continue|in[- ]progress|current task)\b",
            line,
            re.IGNORECASE,
        ):
            next_ids.extend(_TASK_ID.findall(line))
    next_tasks = tuple(task_id for task_id in dict.fromkeys(next_ids) if task_id in tasks)
    lowered = text.lower()
    if "superseded" in lowered:
        state = "superseded"
    elif any(tasks.get(task_id) and tasks[task_id].status == "done" for task_id in next_tasks):
        state = "stale"
        for task_id in next_tasks:
            if tasks.get(task_id) and tasks[task_id].status == "done":
                findings.append(
                    InventoryFinding(
                        "handoff.stale-next-task",
                        "warning",
                        f"handoff names completed task {task_id} as next/current work",
                        Provenance(relative, title_line),
                        task_id,
                    )
                )
    else:
        state = "current" if next_tasks else "unknown"
    return HandoffRecord(
        relative,
        title,
        state,
        referenced,
        next_tasks,
        _links(root, path, lines, sections, decision_ids, findings),
        Provenance(relative, title_line),
    )


def _dependency_findings(
    tasks: list[TaskRecord],
    tasks_by_id: dict[str, TaskRecord],
    findings: list[InventoryFinding],
) -> None:
    for task in tasks:
        for dependency in task.dependencies:
            depended = tasks_by_id.get(dependency)
            if depended is None:
                findings.append(
                    InventoryFinding(
                        "task.dependency-missing",
                        "error",
                        f"declared dependency {dependency} has no inventoried task",
                        task.provenance,
                        task.id,
                    )
                )
            elif task.status == "done" and depended.status != "done":
                findings.append(
                    InventoryFinding(
                        "task.dependency-contradiction",
                        "error",
                        (
                            f"task is done while dependency {dependency} has explicit "
                            f"status {depended.status!r}"
                        ),
                        task.provenance,
                        task.id,
                    )
                )


def _expand(
    root: Path,
    patterns: tuple[str, ...],
    findings: list[InventoryFinding],
    kind: str,
) -> tuple[Path, ...]:
    found: set[Path] = set()
    for pattern in patterns:
        for candidate in root.glob(pattern):
            if not candidate.is_file():
                continue
            try:
                resolved = candidate.resolve()
                resolved.relative_to(root)
            except (OSError, RuntimeError, ValueError):
                findings.append(
                    InventoryFinding(
                        "source.outside-root",
                        "error",
                        f"{kind} source resolves outside the project",
                        Provenance(candidate.relative_to(root).as_posix(), 1),
                    )
                )
                continue
            found.add(resolved)
            if len(found) >= MAX_DOCUMENTS:
                findings.append(
                    InventoryFinding(
                        "source.truncated",
                        "warning",
                        f"{kind} source scan stopped at {MAX_DOCUMENTS} documents",
                        Provenance(".", 1),
                    )
                )
                return tuple(sorted(found))
    return tuple(sorted(found))


def _read(path: Path, relative: str, findings: list[InventoryFinding]) -> str:
    data = path.read_bytes()
    if len(data) > MAX_DOCUMENT_BYTES:
        findings.append(
            InventoryFinding(
                "source.document-truncated",
                "warning",
                f"document was truncated at {MAX_DOCUMENT_BYTES} bytes",
                Provenance(relative, 1),
            )
        )
        data = data[:MAX_DOCUMENT_BYTES]
    return data.decode("utf-8", errors="replace")


def _frontmatter(lines: list[str]) -> tuple[dict[str, Any], int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, 0
    try:
        value = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError:
        return {}, end + 1
    return (value if isinstance(value, dict) else {}), end + 1


def _title(lines: list[str], start: int, fallback: str) -> tuple[str, int]:
    for index, line in enumerate(lines[start:], start=start):
        if match := _HEADING.match(line):
            return match.group(2), index + 1
    return fallback, 1


def _identifier(path: Path, title: str, frontmatter: dict[str, Any]) -> str:
    declared = _typed_metadata(frontmatter).get("id", frontmatter.get("id"))
    if isinstance(declared, (str, int)) and str(declared):
        return str(declared)
    if match := _TASK_ID.search(path.stem):
        return match.group(1)
    if match := _TASK_ID.search(title):
        return match.group(1)
    return path.stem


def _status(lines: list[str], frontmatter: dict[str, Any]) -> tuple[str, bool, int]:
    typed = _typed_metadata(frontmatter)
    declared = typed.get("state", frontmatter.get("status"))
    if isinstance(declared, str) and declared.strip():
        field = "state" if "state" in typed else "status"
        return declared.strip().lower(), True, _mapping_line(lines, field, 1)
    for index, line in enumerate(lines):
        if match := _STATUS.match(line):
            return match.group(1).strip().lower(), True, index + 1
    return "unknown", False, 1


def _projection_summary(
    lines: list[str], frontmatter: dict[str, Any], relative: str
) -> tuple[str | None, Provenance | None]:
    value = frontmatter.get("summary")
    if not isinstance(value, str) or not value.strip():
        return None, None
    line = _mapping_line(lines, "summary", 1)
    return value.strip(), Provenance(relative, line)


def _dependency_text(lines: list[str], frontmatter: dict[str, Any]) -> tuple[str | None, int]:
    relationships = _typed_metadata(frontmatter).get("relationships")
    if isinstance(relationships, list):
        targets = [
            relationship.get("target")
            for relationship in relationships
            if isinstance(relationship, dict)
            and relationship.get("type") == "depends-on"
            and isinstance(relationship.get("target"), str)
            and relationship["target"].startswith("task:")
        ]
        if targets:
            return ", ".join(targets), _mapping_line(lines, "relationships", 1)
    declared = frontmatter.get("depends_on")
    if isinstance(declared, list):
        return ", ".join(str(item) for item in declared), 1
    if isinstance(declared, (str, int)):
        return str(declared), 1
    for index, line in enumerate(lines):
        if match := _DEPENDS.match(line):
            return match.group(1).strip(), index + 1
    return None, 1


def _typed_metadata(frontmatter: dict[str, Any]) -> dict[str, Any]:
    value = frontmatter.get("engineering_document")
    return value if isinstance(value, dict) else {}


def _dependency_ids(value: str) -> tuple[str, ...]:
    found: list[str] = []
    occupied: list[tuple[int, int]] = []
    for match in _RANGE.finditer(value):
        first, last = int(match.group(1)), int(match.group(2))
        if 0 <= last - first <= 100:
            found.extend(f"{number:04d}" for number in range(first, last + 1))
        else:
            found.extend((match.group(1), match.group(2)))
        occupied.append(match.span())
    for match in _TASK_ID.finditer(value):
        if not any(start <= match.start() < end for start, end in occupied):
            found.append(match.group(1))
    return tuple(dict.fromkeys(found))


def _planning_metadata(
    lines: list[str],
    frontmatter: dict[str, Any],
    body_start: int,
    relative: str,
    task_id: str,
    policy: TaskPlanningPolicy | None,
    findings: list[InventoryFinding],
) -> tuple[dict[str, PlanningValue], bool]:
    if policy is None:
        return {}, True

    carriers: list[tuple[str, Any, int]] = []
    direct = frontmatter.get("x-planning")
    if direct is not None:
        carriers.append(("frontmatter extension", direct, _mapping_line(lines, "x-planning", 1)))
    document = frontmatter.get("engineering_document")
    if isinstance(document, dict):
        extensions = document.get("extensions")
        if isinstance(extensions, dict) and "x-planning" in extensions:
            carriers.append(
                (
                    "typed metadata extension",
                    extensions["x-planning"],
                    _mapping_line(lines, "x-planning", 1),
                )
            )
    for index, line in enumerate(lines[body_start:], start=body_start + 1):
        if match := _PLANNING.match(line):
            carriers.append(("Markdown extension", match.group(1), index))

    if not carriers:
        return {}, True
    if len(carriers) != 1:
        findings.append(
            InventoryFinding(
                "task.planning-carrier-conflict",
                "error",
                "x-planning must be declared through exactly one metadata carrier",
                Provenance(relative, carriers[1][2]),
                task_id,
            )
        )
        return {}, False

    carrier_name, raw, carrier_line = carriers[0]
    if isinstance(raw, dict):
        values = raw
    elif isinstance(raw, str):
        values = {}
        if raw.strip():
            for fragment in raw.split(";"):
                name, separator, value = fragment.strip().partition("=")
                if not separator or not name.strip() or not value.strip():
                    findings.append(
                        InventoryFinding(
                            "task.planning-invalid",
                            "error",
                            (
                                "Markdown x-planning entries must use "
                                "field=value pairs separated by semicolons"
                            ),
                            Provenance(relative, carrier_line),
                            task_id,
                        )
                    )
                    return {}, False
                normalized_name = name.strip()
                if normalized_name in values:
                    findings.append(
                        InventoryFinding(
                            "task.planning-field-duplicate",
                            "error",
                            f"Markdown x-planning field {normalized_name!r} was repeated",
                            Provenance(relative, carrier_line),
                            task_id,
                        )
                    )
                    return {}, False
                values[normalized_name] = value.strip()
    else:
        findings.append(
            InventoryFinding(
                "task.planning-invalid",
                "error",
                f"{carrier_name} x-planning must be a mapping",
                Provenance(relative, carrier_line),
                task_id,
            )
        )
        return {}, False

    valid = True
    parsed: dict[str, PlanningValue] = {}
    for name in sorted(values, key=lambda item: str(item)):
        line = (
            _mapping_line(lines, name, carrier_line)
            if isinstance(raw, dict) and isinstance(name, str)
            else carrier_line
        )
        if not isinstance(name, str):
            findings.append(
                InventoryFinding(
                    "task.planning-field-invalid",
                    "error",
                    "x-planning field names must be strings",
                    Provenance(relative, line),
                    task_id,
                )
            )
            valid = False
            continue
        if name not in policy.fields:
            findings.append(
                InventoryFinding(
                    "task.planning-field-unknown",
                    "error",
                    f"x-planning field {name!r} is not declared by the project",
                    Provenance(relative, line),
                    task_id,
                )
            )
            valid = False
            continue
        value = values[name]
        allowed = policy.fields[name].values
        if not isinstance(value, str) or value not in allowed:
            findings.append(
                InventoryFinding(
                    "task.planning-value-invalid",
                    "error",
                    f"x-planning field {name!r} must be one of {list(allowed)!r}",
                    Provenance(relative, line),
                    task_id,
                )
            )
            valid = False
            continue
        parsed[name] = PlanningValue(value, Provenance(relative, line))
    return parsed, valid


def _mapping_line(lines: list[str], key: str, fallback: int) -> int:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:")
    for index, line in enumerate(lines, start=1):
        if pattern.match(line):
            return index
    return fallback


def _planning_contract(policy: TaskPlanningPolicy) -> dict[str, Any]:
    return {
        "extension": "x-planning",
        "fields": {
            name: {
                "values": list(policy.fields[name].values),
                "order": list(policy.fields[name].order),
            }
            for name in sorted(policy.fields)
        },
        "default_order": list(policy.default_order),
    }


def _planning_filters(
    filters: tuple[str, ...],
    policy: TaskPlanningPolicy | None,
) -> tuple[tuple[str, str], ...]:
    parsed: list[tuple[str, str]] = []
    seen: set[str] = set()
    for expression in filters:
        field, separator, value = expression.partition("=")
        if not separator or not field or not value:
            raise ValueError("planning filters must use FIELD=VALUE")
        if policy is None or field not in policy.fields:
            raise ValueError(f"planning filter field {field!r} is not adopted")
        if value not in policy.fields[field].values:
            raise ValueError(
                f"planning filter {field!r} must be one of {list(policy.fields[field].values)!r}"
            )
        if field in seen:
            raise ValueError(f"planning filter field {field!r} was repeated")
        seen.add(field)
        parsed.append((field, value))
    return tuple(parsed)


def _planning_order(
    order_by: tuple[str, ...],
    policy: TaskPlanningPolicy | None,
) -> tuple[str, ...]:
    selected = order_by or (() if policy is None else policy.default_order)
    if len(set(selected)) != len(selected):
        raise ValueError("planning order fields must not repeat")
    for field in selected:
        if policy is None or field not in policy.fields:
            raise ValueError(f"planning order field {field!r} is not adopted")
        if not policy.fields[field].order:
            raise ValueError(f"planning field {field!r} has no explicit order")
    return tuple(selected)


def _planning_sort_key(
    item: dict[str, Any],
    order_by: tuple[str, ...],
    policy: TaskPlanningPolicy | None,
) -> tuple[Any, ...]:
    assert policy is not None
    key: list[Any] = []
    metadata = item.get("planning", {})
    for field in order_by:
        value = metadata.get(field, {}).get("value")
        order = policy.fields[field].order
        key.append((value is None, order.index(value) if value in order else len(order)))
    key.append(item["id"])
    return tuple(key)


def _sections(lines: list[str]) -> dict[str, tuple[int, int]]:
    headings: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        if match := _HEADING.match(line):
            headings.append((match.group(2).strip().lower(), index + 1))
    return {
        heading: (start, headings[index + 1][1] - 1 if index + 1 < len(headings) else len(lines))
        for index, (heading, start) in enumerate(headings)
    }


def _section_criteria(
    lines: list[str],
    sections: dict[str, tuple[int, int]],
    names: set[str],
    relative: str,
) -> tuple[Criterion, ...]:
    found: list[Criterion] = []
    for heading, (start, end) in sections.items():
        if heading not in names:
            continue
        for index in range(start, end):
            if match := _BULLET.match(lines[index]):
                marker = match.group(1)
                checked = None if marker is None else marker.lower() == "x"
                found.append(Criterion(match.group(2), checked, Provenance(relative, index + 1)))
    return tuple(found)


def _links(
    root: Path,
    document: Path,
    lines: list[str],
    sections: dict[str, tuple[int, int]],
    decision_ids: set[str],
    findings: list[InventoryFinding],
) -> tuple[DocumentLink, ...]:
    evidence_lines = {
        index + 1
        for heading, (start, end) in sections.items()
        if heading in {"evidence", "verification"}
        for index in range(start, end)
    }
    found: list[DocumentLink] = []
    for index, line in enumerate(lines, start=1):
        for match in _LINK.finditer(line):
            label, target = match.groups()
            split = urlsplit(target)
            if split.scheme or target.startswith("#"):
                exists: bool | None = None
                kind = "external" if split.scheme else "anchor"
            else:
                decoded = unquote(split.path)
                candidate = (document.parent / decoded).resolve()
                try:
                    candidate.relative_to(root)
                    exists = candidate.exists()
                except ValueError:
                    exists = None
                    kind = "external-local"
                else:
                    kind = "evidence" if index in evidence_lines else "local"
                    if "adr" in candidate.parts or "decisions" in candidate.parts:
                        kind = "decision"
            found.append(
                DocumentLink(
                    label,
                    target,
                    kind,
                    exists,
                    Provenance(document.relative_to(root).as_posix(), index),
                )
            )
        for decision_id in re.findall(r"\bADR\s+(\d{4})\b", line, re.IGNORECASE):
            found.append(
                DocumentLink(
                    f"ADR {decision_id}",
                    decision_id,
                    "decision",
                    decision_id in decision_ids,
                    Provenance(document.relative_to(root).as_posix(), index),
                )
            )
    return tuple(found)


def _finding_key(item: InventoryFinding) -> tuple[str, int, str]:
    return item.provenance.path, item.provenance.line, item.code


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _task_json(item: TaskRecord) -> dict[str, Any]:
    value = asdict(item)
    if not value["planning"]:
        value.pop("planning")
    return _jsonable(value)
