"""Opt-in, read-only documentation currency validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from ..policy.manifest import DocsCurrencyPolicy, DocumentRolePolicy, TaskInventoryPolicy
from .markdown import DocFinding, table_cells
from .query import inventory

MAX_DOCUMENT_BYTES = 1_000_000
MAX_DOCUMENTS = 2_000
MARKDOWN = MarkdownIt("commonmark").enable("table")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_PLACEHOLDERS = {
    "populate before marking done.",
    "populate before marking `done`.",
    "todo",
    "tbd",
}


@dataclass(frozen=True)
class CurrencyFinding(DocFinding):
    severity: str
    rationale: str
    repair: str
    ci_blocking: bool = True


_RULES = {
    "currency.current-missing": (
        "warning",
        "an adopted current-record role requires exactly one authoritative record",
        "mark exactly one indexed record with the configured current state",
    ),
    "currency.current-multiple": (
        "error",
        "multiple current records make continuation authority ambiguous",
        "retain one current record and mark the older records with an inactive state",
    ),
    "currency.done-evidence-missing": (
        "warning",
        "a done task requires durable completion evidence rather than status alone",
        "add a configured evidence section with concrete verification or change the task status",
    ),
    "currency.duplicate-id": (
        "error",
        "duplicate identifiers make role records and links ambiguous",
        "renumber the newer record and update its reviewed references",
    ),
    "currency.index-entry-missing": (
        "warning",
        "an adopted role index must cover every configured record",
        "add one link to the record in the configured role index",
    ),
    "currency.index-missing": (
        "error",
        "a configured role index is required to establish current navigation authority",
        "create the declared index or repair its repository-relative path",
    ),
    "currency.index-target-duplicate": (
        "warning",
        "duplicate index targets obscure whether records are intentionally represented twice",
        "retain one authoritative index link for the record",
    ),
    "currency.record-id-missing": (
        "warning",
        "configured records require an extractable role-local identifier",
        "rename the record or repair the role id_pattern",
    ),
    "currency.required-pointer-missing": (
        "warning",
        "declared current-truth entry points must remain available",
        "restore the declared document or remove the policy after maintainer review",
    ),
    "currency.role-empty": (
        "warning",
        "an adopted document role should not silently select no records",
        "repair the role include patterns or remove the unused role declaration",
    ),
    "currency.source-outside-root": (
        "error",
        "documentation policy may not follow sources outside the repository",
        "replace the escaping symlink or repair the declared path",
    ),
    "currency.source-truncated": (
        "warning",
        "bounded validation cannot establish currency for uninspected content",
        "reduce the configured scope or split oversized documents",
    ),
    "currency.state-missing": (
        "warning",
        "every indexed record in a stateful role needs an explicit recognized state",
        "add a state matching the role state_pattern to the record's index entry",
    ),
}


def validate_currency(root: Path, policy: DocsCurrencyPolicy | None) -> tuple[CurrencyFinding, ...]:
    """Validate only explicitly adopted currency invariants."""
    if policy is None:
        return ()
    root = root.resolve()
    findings: list[CurrencyFinding] = []
    for role in policy.roles:
        _validate_role(root, role, findings)
    for pointer in policy.required_current_truth:
        _validate_required_pointer(root, pointer, findings)
    if policy.done_task_evidence is not None:
        _validate_done_task_evidence(root, policy, findings)
    return tuple(sorted(findings, key=lambda item: (item.path, item.line, item.code, item.message)))


def _validate_role(
    root: Path,
    role: DocumentRolePolicy,
    findings: list[CurrencyFinding],
) -> None:
    documents = _expand(root, role.include, findings)
    index = _contained_path(root, role.index, findings)
    documents = tuple(path for path in documents if index is None or path != index)
    if not documents:
        findings.append(
            _finding(
                "currency.role-empty",
                role.index,
                1,
                f"role {role.name!r} matched no record documents",
            )
        )

    identifiers: dict[str, list[str]] = {}
    for document in documents:
        relative = document.relative_to(root).as_posix()
        identifier = document.name[: role.id_prefix_digits]
        if len(identifier) != role.id_prefix_digits or not identifier.isdigit():
            findings.append(
                _finding(
                    "currency.record-id-missing",
                    relative,
                    1,
                    f"role {role.name!r} requires a {role.id_prefix_digits}-digit filename prefix",
                )
            )
            continue
        identifiers.setdefault(identifier, []).append(relative)

    for identifier, sources in sorted(identifiers.items()):
        if len(sources) < 2:
            continue
        collision = ", ".join(sources)
        for source in sources:
            findings.append(
                _finding(
                    "currency.duplicate-id",
                    source,
                    1,
                    f"role {role.name!r} ID {identifier!r} is declared by: {collision}",
                )
            )

    if index is None:
        return
    if not index.is_file():
        findings.append(
            _finding(
                "currency.index-missing",
                role.index,
                1,
                f"role {role.name!r} index does not exist",
            )
        )
        return

    index_text = _read(index, root, findings)
    links = _local_links(root, index, index_text)
    document_set = set(documents)
    indexed: dict[Path, tuple[int, str]] = {}
    for target, line, source_line in links:
        if target not in document_set:
            continue
        if target in indexed:
            findings.append(
                _finding(
                    "currency.index-target-duplicate",
                    role.index,
                    line,
                    f"role {role.name!r} target {target.relative_to(root).as_posix()} is repeated",
                )
            )
            continue
        indexed[target] = (line, source_line)

    for document in documents:
        if document not in indexed:
            findings.append(
                _finding(
                    "currency.index-entry-missing",
                    document.relative_to(root).as_posix(),
                    1,
                    f"role {role.name!r} record is absent from {role.index}",
                )
            )

    if role.states and role.current_state is not None:
        current: list[tuple[Path, int]] = []
        for document, (line, source_line) in indexed.items():
            cells = {cell.strip() for cell in table_cells(source_line)}
            matched_states = [state for state in role.states if state in cells]
            if len(matched_states) != 1:
                findings.append(
                    _finding(
                        "currency.state-missing",
                        role.index,
                        line,
                        f"role {role.name!r} target "
                        f"{document.relative_to(root).as_posix()} has no single recognized state",
                    )
                )
                continue
            if matched_states[0] == role.current_state:
                current.append((document, line))
        if not current:
            findings.append(
                _finding(
                    "currency.current-missing",
                    role.index,
                    1,
                    f"role {role.name!r} has no {role.current_state!r} index entry",
                )
            )
        elif len(current) > 1:
            paths = ", ".join(path.relative_to(root).as_posix() for path, _line in current)
            findings.append(
                _finding(
                    "currency.current-multiple",
                    role.index,
                    current[1][1],
                    f"role {role.name!r} has {len(current)} current entries: {paths}",
                )
            )


def _validate_required_pointer(
    root: Path,
    relative: str,
    findings: list[CurrencyFinding],
) -> None:
    path = _contained_path(root, relative, findings)
    if path is not None and not path.is_file():
        findings.append(
            _finding(
                "currency.required-pointer-missing",
                relative,
                1,
                "declared current-truth pointer does not exist",
            )
        )


def _validate_done_task_evidence(
    root: Path,
    policy: DocsCurrencyPolicy,
    findings: list[CurrencyFinding],
) -> None:
    declaration = policy.done_task_evidence
    if declaration is None:
        return
    report = inventory(
        root,
        TaskInventoryPolicy(include=declaration.include, handoffs=(), decisions=()),
    )
    for issue in report["findings"]:
        if issue["code"] == "source.outside-root":
            findings.append(
                _finding(
                    "currency.source-outside-root",
                    issue["provenance"]["path"],
                    issue["provenance"]["line"],
                    issue["message"],
                )
            )
        elif issue["code"] in {"source.truncated", "source.document-truncated"}:
            findings.append(
                _finding(
                    "currency.source-truncated",
                    issue["provenance"]["path"],
                    issue["provenance"]["line"],
                    issue["message"],
                )
            )
    for task in report["tasks"]:
        if task["status"] != "done":
            continue
        relative = task["provenance"]["path"]
        path = _contained_path(root, relative, findings)
        if path is None or not path.is_file():
            continue
        text = _read(path, root, findings)
        if not _has_substantive_section(text, declaration.headings):
            findings.append(
                _finding(
                    "currency.done-evidence-missing",
                    relative,
                    task["provenance"]["line"],
                    f"done task {task['id']} lacks a substantive configured evidence section",
                )
            )


def _has_substantive_section(text: str, headings: tuple[str, ...]) -> bool:
    lines = text.splitlines()
    accepted = {heading.strip().casefold() for heading in headings}
    found: list[tuple[int, int]] = []
    heading_lines: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        if match := _HEADING.match(line):
            heading_lines.append((match.group(2).strip().casefold(), index))
    for index, (heading, start) in enumerate(heading_lines):
        if heading not in accepted:
            continue
        end = heading_lines[index + 1][1] if index + 1 < len(heading_lines) else len(lines)
        found.append((start + 1, end))
    for start, end in found:
        body = "\n".join(lines[start:end]).strip()
        without_comments = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
        normalized = " ".join(without_comments.casefold().split())
        if normalized and normalized not in _PLACEHOLDERS:
            return True
    return False


def _expand(
    root: Path,
    patterns: tuple[str, ...],
    findings: list[CurrencyFinding],
) -> tuple[Path, ...]:
    found: set[Path] = set()
    for pattern in patterns:
        for candidate in root.glob(pattern):
            if not candidate.is_file():
                continue
            resolved = _contained_candidate(root, candidate, findings)
            if resolved is None:
                continue
            found.add(resolved)
            if len(found) >= MAX_DOCUMENTS:
                findings.append(
                    _finding(
                        "currency.source-truncated",
                        ".",
                        1,
                        f"currency source scan stopped at {MAX_DOCUMENTS} documents",
                    )
                )
                return tuple(sorted(found))
    return tuple(sorted(found))


def _contained_path(
    root: Path,
    relative: str,
    findings: list[CurrencyFinding],
) -> Path | None:
    return _contained_candidate(root, root / relative, findings)


def _contained_candidate(
    root: Path,
    candidate: Path,
    findings: list[CurrencyFinding],
) -> Path | None:
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError:
            relative = "."
        findings.append(
            _finding(
                "currency.source-outside-root",
                relative,
                1,
                "configured documentation source resolves outside the project",
            )
        )
        return None
    return resolved


def _read(path: Path, root: Path, findings: list[CurrencyFinding]) -> str:
    data = path.read_bytes()
    if len(data) > MAX_DOCUMENT_BYTES:
        findings.append(
            _finding(
                "currency.source-truncated",
                path.relative_to(root).as_posix(),
                1,
                f"document was truncated at {MAX_DOCUMENT_BYTES} bytes",
            )
        )
        data = data[:MAX_DOCUMENT_BYTES]
    return data.decode("utf-8", errors="replace")


def _local_links(root: Path, index: Path, text: str) -> tuple[tuple[Path, int, str], ...]:
    lines = text.splitlines()
    found: list[tuple[Path, int, str]] = []
    for token in MARKDOWN.parse(text):
        if token.type != "inline":
            continue
        line = token.map[0] + 1 if token.map else 1
        source_line = lines[line - 1] if line <= len(lines) else ""
        for child in token.children or ():
            if child.type != "link_open":
                continue
            destination = child.attrGet("href")
            if not destination:
                continue
            split = urlsplit(destination)
            if split.scheme or not split.path:
                continue
            candidate = (index.parent / unquote(split.path)).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            found.append((candidate, line, source_line))
    return tuple(found)


def _finding(code: str, path: str, line: int, message: str) -> CurrencyFinding:
    severity, rationale, repair = _RULES[code]
    return CurrencyFinding(path, line, code, message, severity, rationale, repair)
