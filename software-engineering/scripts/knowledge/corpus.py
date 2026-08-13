"""Bounded knowledge-frontmatter parsing, routing, and index generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import jsonschema
import yaml

from ..resources import schema_path, skill_root

MAX_FILES = 128
MAX_FRONTMATTER_BYTES = 16_384
INDEX_HEADER = "# Engineering knowledge index"
SENTENCE_BREAK = re.compile(r"[.!?]\s+\S")
SOURCE_GROUP = re.compile(r"^src-[a-z][a-z0-9-]{1,79}$")
SOURCE_COLUMNS = (
    "Source",
    "Publisher / Author",
    "URL",
    "Accessed",
    "Status",
    "Informs",
    "Groups",
    "Re-verify when",
)
SOURCE_STATUSES = {"verified", "unverified", "paywalled", "archived"}


@dataclass(frozen=True)
class KnowledgeRecord:
    id: str
    path: str
    summary: str
    routes: tuple[str, ...]
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceRecord:
    title: str
    publisher: str
    url: str
    accessed: str
    status: str
    informs: tuple[str, ...]
    groups: tuple[str, ...]
    reverify_when: str
    line: int


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str


def _schema(root: Path | None = None) -> dict[str, Any]:
    path = (
        root / "assets" / "schemas" / "knowledge-v1.schema.json"
        if root is not None
        else schema_path("knowledge-v1.schema.json")
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def route_vocabulary(root: Path | None = None) -> tuple[str, ...]:
    return tuple(_schema(root)["properties"]["routes"]["items"]["enum"])


def _frontmatter(path: Path) -> tuple[dict[str, Any] | None, Finding | None]:
    with path.open("rb") as handle:
        raw = handle.read(MAX_FRONTMATTER_BYTES + 1)
    if len(raw) > MAX_FRONTMATTER_BYTES and b"\n---\n" not in raw[:MAX_FRONTMATTER_BYTES]:
        return None, Finding(
            "knowledge.frontmatter-too-large", path.name, "frontmatter is unbounded"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, Finding("knowledge.encoding", path.name, "knowledge must be UTF-8")
    if not text.startswith("---\n"):
        return None, Finding("knowledge.frontmatter-missing", path.name, "frontmatter is required")
    closing = text.find("\n---\n", 4)
    if closing < 0:
        return None, Finding("knowledge.frontmatter-unclosed", path.name, "frontmatter is unclosed")
    try:
        loaded = yaml.safe_load(text[4:closing])
    except yaml.YAMLError as exc:
        return None, Finding("knowledge.frontmatter-invalid", path.name, str(exc))
    if not isinstance(loaded, dict) or set(loaded) != {"knowledge"}:
        return None, Finding(
            "knowledge.wrapper-invalid", path.name, "frontmatter must contain only 'knowledge'"
        )
    metadata = loaded["knowledge"]
    if not isinstance(metadata, dict):
        return None, Finding("knowledge.metadata-invalid", path.name, "knowledge must be a mapping")
    return metadata, None


def scan_corpus(
    root: Path | None = None,
) -> tuple[tuple[KnowledgeRecord, ...], tuple[Finding, ...]]:
    base = (root or skill_root()) / "knowledge"
    paths = sorted(path for path in base.glob("*.md") if path.name != "INDEX.md")
    findings: list[Finding] = []
    records: list[KnowledgeRecord] = []
    if len(paths) > MAX_FILES:
        findings.append(Finding("knowledge.too-many-files", "knowledge", f"limit is {MAX_FILES}"))
        paths = paths[:MAX_FILES]
    validator = jsonschema.Draft202012Validator(_schema(root or skill_root()))
    for path in paths:
        metadata, parsing = _frontmatter(path)
        if parsing is not None:
            findings.append(parsing)
            continue
        assert metadata is not None
        errors = sorted(validator.iter_errors(metadata), key=lambda item: list(item.absolute_path))
        if errors:
            findings.extend(
                Finding(
                    "knowledge.metadata-invalid",
                    path.name,
                    f"{'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}",
                )
                for error in errors
            )
            continue
        if SENTENCE_BREAK.search(metadata["summary"][:-1]):
            findings.append(
                Finding(
                    "knowledge.summary-multiple-sentences",
                    path.name,
                    "summary must be one sentence",
                )
            )
        records.append(
            KnowledgeRecord(
                metadata["id"],
                f"knowledge/{path.name}",
                metadata["summary"],
                tuple(metadata["routes"]),
                tuple(metadata.get("sources", ())),
            )
        )
    ids: dict[str, str] = {}
    for record in records:
        if previous := ids.get(record.id):
            findings.append(
                Finding("knowledge.duplicate-id", record.path, f"also declared by {previous}")
            )
        ids[record.id] = record.path
        if Path(record.path).stem != record.id:
            findings.append(
                Finding("knowledge.filename-id", record.path, "id must equal the filename stem")
            )
    used_routes = {route for record in records for route in record.routes}
    for route in sorted(set(route_vocabulary(root or skill_root())) - used_routes):
        findings.append(Finding("knowledge.dead-route", "knowledge", route))
    return tuple(sorted(records, key=lambda item: item.id)), tuple(findings)


def build_index(records: tuple[KnowledgeRecord, ...]) -> str:
    lines = [
        INDEX_HEADER,
        "",
        "> Generated from knowledge frontmatter by `scripts.knowledge`; do not edit by hand.",
        "",
        "Read this compact index first, select the smallest route-matching set, then open only those full files.",
        "",
    ]
    rows = [("Knowledge", "Routes", "Retrieval summary")]
    for record in records:
        route_text = ", ".join(f"`{route}`" for route in record.routes)
        rows.append((f"[`{record.id}`]({record.id}.md)", route_text, record.summary))
    widths = tuple(max(len(row[column]) for row in rows) for column in range(3))
    lines.append(
        "| " + " | ".join(value.ljust(widths[i]) for i, value in enumerate(rows[0])) + " |"
    )
    lines.append("| " + " | ".join("-" * width for width in widths) + " |")
    lines.extend(
        "| " + " | ".join(value.ljust(widths[i]) for i, value in enumerate(row)) + " |"
        for row in rows[1:]
    )
    lines.extend(
        (
            "",
            "Unknown route IDs select nothing; inspect the task and project policy instead of guessing.",
            "",
        )
    )
    return "\n".join(lines)


def validate_corpus(root: Path | None = None) -> tuple[Finding, ...]:
    base = root or skill_root()
    records, findings = scan_corpus(base)
    source_register = base / "references" / "SOURCES.md"
    if not source_register.is_file():
        source_findings: tuple[Finding, ...] = (
            Finding(
                "knowledge.source-register-missing",
                "references/SOURCES.md",
                "source register is required",
            ),
        )
    else:
        source_findings = _validate_sources(source_register, records)
    index = base / "knowledge" / "INDEX.md"
    expected = build_index(records)
    drift = ()
    if not index.is_file() or index.read_text(encoding="utf-8") != expected:
        drift = (Finding("knowledge.index-drift", "knowledge/INDEX.md", "regenerate index"),)
    return (*findings, *source_findings, *drift)


def _cells(line: str) -> tuple[str, ...]:
    return tuple(cell.strip() for cell in line.strip().strip("|").split("|"))


def _items(value: str) -> set[str]:
    return {item.strip().strip("`") for item in value.split(",") if item.strip()}


def _validate_sources(path: Path, records: tuple[KnowledgeRecord, ...]) -> tuple[Finding, ...]:
    _records, findings = scan_source_register(path, records)
    return findings


def scan_source_register(
    path: Path, records: tuple[KnowledgeRecord, ...]
) -> tuple[tuple[SourceRecord, ...], tuple[Finding, ...]]:
    relative = "references/SOURCES.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return (), (
            Finding("knowledge.source-encoding", relative, "source register must be UTF-8"),
        )
    header = next(
        (index for index, line in enumerate(lines) if _cells(line) == SOURCE_COLUMNS), None
    )
    if header is None or header + 1 >= len(lines):
        return (), (
            Finding(
                "knowledge.source-table-invalid",
                relative,
                f"required columns are: {', '.join(SOURCE_COLUMNS)}",
            ),
        )
    delimiter = _cells(lines[header + 1])
    if len(delimiter) != len(SOURCE_COLUMNS) or any(
        not re.fullmatch(r":?-{3,}:?", cell) for cell in delimiter
    ):
        return (), (Finding("knowledge.source-table-invalid", relative, "invalid table delimiter"),)

    known_records = {record.id for record in records}
    owners: dict[str, set[str]] = {}
    for record in records:
        for group in record.sources:
            owners.setdefault(group, set()).add(record.id)
    observed_groups: set[str] = set()
    observed_urls: set[str] = set()
    source_records: list[SourceRecord] = []
    output: list[Finding] = []
    for number, line in enumerate(lines[header + 2 :], header + 3):
        if not line.strip().startswith("|"):
            if line.strip():
                output.append(
                    Finding(
                        "knowledge.source-table-invalid",
                        relative,
                        f"line {number}: non-table content after source header",
                    )
                )
            continue
        cells = _cells(line)
        if len(cells) != len(SOURCE_COLUMNS) or any(not cell for cell in cells):
            output.append(
                Finding(
                    "knowledge.source-row-invalid",
                    relative,
                    f"line {number}: expected {len(SOURCE_COLUMNS)} non-empty cells",
                )
            )
            continue
        title, publisher, raw_url, accessed, status, informs_raw, groups_raw, trigger = cells
        url = raw_url.removeprefix("<").removesuffix(">")
        informs = _items(informs_raw)
        groups = _items(groups_raw)
        source_records.append(
            SourceRecord(
                title,
                publisher,
                url,
                accessed,
                status,
                tuple(sorted(informs)),
                tuple(sorted(groups)),
                trigger,
                number,
            )
        )
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            output.append(
                Finding("knowledge.source-url-invalid", relative, f"line {number}: {raw_url}")
            )
        if url in observed_urls:
            output.append(
                Finding("knowledge.source-url-duplicate", relative, f"line {number}: {url}")
            )
        observed_urls.add(url)
        try:
            date.fromisoformat(accessed)
        except ValueError:
            output.append(
                Finding("knowledge.source-accessed-invalid", relative, f"line {number}: {accessed}")
            )
        if status not in SOURCE_STATUSES:
            output.append(
                Finding("knowledge.source-status-invalid", relative, f"line {number}: {status}")
            )
        unknown_informs = informs - known_records
        if unknown_informs:
            output.append(
                Finding(
                    "knowledge.source-informs-missing",
                    relative,
                    f"line {number}: {', '.join(sorted(unknown_informs))}",
                )
            )
        for group in groups:
            if not SOURCE_GROUP.fullmatch(group) or group not in owners:
                output.append(
                    Finding(
                        "knowledge.source-group-invalid",
                        relative,
                        f"line {number}: {group}",
                    )
                )
            elif not informs.intersection(owners[group]):
                output.append(
                    Finding(
                        "knowledge.source-group-owner-mismatch",
                        relative,
                        f"line {number}: {group}",
                    )
                )
        observed_groups.update(groups)
    for group in sorted(set(owners) - observed_groups):
        output.append(Finding("knowledge.source-missing", relative, group))
    return tuple(source_records), tuple(output)


def select_records(
    records: tuple[KnowledgeRecord, ...], routes: tuple[str, ...]
) -> tuple[KnowledgeRecord, ...]:
    selected = set(routes)
    unknown = selected - set(route_vocabulary())
    if unknown:
        return ()
    return tuple(record for record in records if selected.intersection(record.routes))


def read_selected(root: Path, records: tuple[KnowledgeRecord, ...]) -> dict[str, str]:
    return {record.id: (root / record.path).read_text(encoding="utf-8") for record in records}
