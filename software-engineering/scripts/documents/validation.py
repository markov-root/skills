"""Safe extraction and repository validation for adopted typed Markdown roles."""

from __future__ import annotations

import datetime as dt
import glob
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml
from markdown_it import MarkdownIt
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken

from ..policy.manifest import DocsCurrencyPolicy, DocsPolicy, DocumentRolePolicy
from .contracts import (
    DOCUMENT_SCHEMA_VERSION,
    GENERIC_ROLES,
    RECORD_ROLES,
    ROLE_CONTRACTS,
    DocumentContractRecord,
    core_metadata_validator,
    metadata_validator,
    validate_document_records,
)
from .currency import validate_currency
from .markdown import DocFinding, table_cells
from .markdown import validate_markdown as validate_markdown_structure
from .projection import MAX_SUMMARY_CHARACTERS, summary_is_valid

MAX_DOCUMENTS = 2_000
MAX_DOCUMENT_BYTES = 1_000_000
MAX_FRONTMATTER_BYTES = 65_536
MAX_FRONTMATTER_LINES = 512
MARKDOWN = MarkdownIt("commonmark").enable("table")
V2_CORE_KEYS = (
    "schema_version",
    "id",
    "uid",
    "title",
    "role",
    "status",
    "summary",
    "created",
    "updated",
)
ROLE_LABELS = {
    "adr": "ADR",
    "task": "Task",
    "lesson": "Lesson",
    "audit": "Audit",
    "research": "Research",
    "handoff": "Handoff",
    "specification": "Specification",
    "knowledge": "Knowledge",
    "reference": "Reference",
    "standard": "Standard",
    "guide": "Guide",
    "roadmap": "Roadmap",
    "changelog": "Changelog",
    "runbook": "Runbook",
    "index": "Index",
    "template": "Template",
}
_BODY_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_TOP_LEVEL_BULLET = re.compile(r"^ {0,3}[-+*]\s+(.+)$")
_CRITERION_PREFIX = re.compile(r"^(?:\[[ xX]\]\s*)?(?:\*\*)?(AC-[1-9][0-9]*)(?:\*\*)?\s*:\s*\S")
_SOURCE_REFERENCE = re.compile(r"\bsource:src-[A-Za-z0-9][A-Za-z0-9._-]{0,123}\b")


@dataclass(frozen=True)
class RoleFinding(DocFinding):
    severity: str
    rationale: str
    repair: str
    ci_blocking: bool = True

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["id"] = data.pop("code")
        data["provenance"] = {"path": data.pop("path"), "line": data.pop("line")}
        return data


@dataclass(frozen=True)
class ExtractedDocument:
    record: DocumentContractRecord
    core: Mapping[str, Any]
    record_role: bool
    summary: str
    status: str
    body: str
    body_line: int


@dataclass(frozen=True)
class DocumentSelection:
    source: str
    role: str
    include_patterns: tuple[str, ...]
    index: str
    registry_precedence: int
    contract_version: int


@dataclass(frozen=True)
class DocumentProjection:
    source: str
    summary: str
    status: str


@dataclass(frozen=True)
class DocumentScan:
    records: tuple[DocumentContractRecord, ...]
    selections: tuple[DocumentSelection, ...]
    projections: tuple[DocumentProjection, ...]
    findings: tuple[RoleFinding, ...]
    partial: bool


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


_RULES = {
    "document.frontmatter-missing": (
        "error",
        "an adopted typed role requires colocated versioned metadata",
        "add bounded YAML frontmatter using the role template",
    ),
    "document.frontmatter-unclosed": (
        "error",
        "unclosed frontmatter makes the metadata/body boundary ambiguous",
        "close the opening frontmatter with a standalone --- line",
    ),
    "document.frontmatter-too-large": (
        "error",
        "bounded parsing prevents resource-amplification through repository input",
        "reduce metadata below the documented byte and line limits",
    ),
    "document.frontmatter-unsafe": (
        "error",
        "aliases, anchors, and tags add expansion or construction behavior",
        "replace aliases, anchors, and tags with explicit scalar/list/map values",
    ),
    "document.frontmatter-invalid": (
        "error",
        "malformed or duplicate-key YAML cannot carry unambiguous authority",
        "repair the YAML and retain exactly one value for every key",
    ),
    "document.frontmatter-wrapper-invalid": (
        "error",
        "the fixed projection and namespace prevent unrelated frontmatter from becoming contract data",
        "use exactly summary, status, and the configured metadata wrapper key",
    ),
    "document.v2-core-missing": (
        "warning",
        "ADR 0002 requires one flat queryable core on every governed document",
        "add the missing top-level schema-version-2 core key from the role template",
    ),
    "document.v2-core-invalid": (
        "warning",
        "the new queryable-core surface is reporting migration drift before hard enforcement",
        "repair the top-level field against document-metadata-v2.schema.json",
    ),
    "document.v2-projection-mismatch": (
        "warning",
        "duplicated record identity and date projections must not drift during the compatibility window",
        "make the flat v2 core equal the corresponding engineering_document value",
    ),
    "document.v2-extension-required": (
        "warning",
        "record roles retain the engineering_document lifecycle extension during v2 migration",
        "add the preserved engineering_document mapping from the record-role template",
    ),
    "document.v2-extension-forbidden": (
        "warning",
        "living and meta roles use the generic flat-core path without record lifecycle state",
        "remove engineering_document from this living or meta document",
    ),
    "document.summary-invalid": (
        "error",
        "a bounded one-sentence summary enables cheap document discovery before body retrieval",
        "write one non-empty sentence of at most 150 characters ending in punctuation",
    ),
    "document.status-invalid": (
        "error",
        "the top-level status is a retrieval projection of the authoritative typed lifecycle state",
        "set status to exactly the engineering_document.state value",
    ),
    "document.source-encoding-invalid": (
        "error",
        "typed metadata and Markdown require deterministic UTF-8 decoding",
        "encode the document as valid UTF-8",
    ),
    "document.source-outside-root": (
        "error",
        "adopted document validation may not follow content outside the repository",
        "replace the escaping symlink or repair the adopted include pattern",
    ),
    "document.source-truncated": (
        "error",
        "partial reads cannot establish a complete metadata or body contract",
        "reduce the document/role scope below the bounded validation limits",
    ),
    "document.source-role-overlap": (
        "error",
        "one record cannot carry two adopted role authorities",
        "make contracted role include patterns disjoint or move the record",
    ),
    "document.role-mismatch": (
        "error",
        "metadata role must agree with the explicitly adopted registry entry",
        "change the metadata role or move the document into the correct adopted role",
    ),
    "document.filename-id-mismatch": (
        "error",
        "filename and metadata identity disagreement makes links and indexes ambiguous",
        "make the metadata ID equal the configured filename prefix",
    ),
    "document.title-mismatch": (
        "warning",
        "the machine title and primary human heading must identify the same record",
        "use the role template H1 with the metadata ID and title",
    ),
    "document.section-missing": (
        "warning",
        "role-specific sections keep the human review surface complete and predictable",
        "add the missing section using the role template",
    ),
    "document.index-state-mismatch": (
        "error",
        "metadata and the adopted currency index cannot claim different current states",
        "reconcile the metadata state and the single recognized index state",
    ),
    "document.version-unsupported": (
        "error",
        "consumers cannot safely interpret an unknown metadata contract version",
        "migrate to a supported version or upgrade the engineering CLI deliberately",
    ),
    "document.role-unsupported": (
        "error",
        "role semantics must be selected from the versioned built-in registry",
        "use an adopted v1 role or defer the extension to a versioned contract change",
    ),
    "document.metadata-invalid": (
        "error",
        "partial or unknown metadata cannot carry deterministic role authority",
        "repair the reported schema path using the role template and metadata-v1 schema",
    ),
    "document.duplicate-id": (
        "error",
        "duplicate role-local identities make relationships and indexes ambiguous",
        "assign one unique ID within the role and update reviewed references",
    ),
    "document.duplicate-uid": (
        "error",
        "duplicate machine identities make records indistinguishable across safe renumbering",
        "mint a new role-namespaced UID for the newer record and preserve the older UID",
    ),
    "document.criteria-mismatch": (
        "error",
        "task metadata must enumerate the exact acceptance criteria reviewed in the body",
        "make details.criteria match the ordered AC-N identifiers under Done when",
    ),
    "document.criterion-id-duplicate": (
        "error",
        "duplicate local criterion identifiers make evidence references ambiguous",
        "assign each Done when bullet one unique sequential AC-N identifier",
    ),
    "document.criterion-id-missing": (
        "error",
        "every acceptance bullet needs a stable local identity for traceable evidence",
        "prefix the Done when bullet with AC-N followed by a colon",
    ),
    "document.uid-invalid": (
        "error",
        "machine identity must remain collision-resistant, role-namespaced, and immutable",
        "mint the UID through the sanctioned allocator using the documented role-timestamp-random shape",
    ),
    "document.updated-stale": (
        "error",
        "a changed typed record must not retain an earlier update date",
        "review the change and set updated to the current UTC date",
    ),
    "document.relationship-target-missing": (
        "error",
        "local document relationships must resolve within the validated adopted record set",
        "add the target record or repair/remove the stale relationship",
    ),
    "document.relationship-duplicate": (
        "error",
        "duplicate edges create conflicting notes and inflated graph evidence",
        "retain one relationship for each type and target pair",
    ),
    "document.transition-history-invalid": (
        "error",
        "legacy-unknown history must not contain events that appear evidentiary",
        "remove invented events or replace the marker with reviewed complete history",
    ),
    "document.transition-history-incomplete": (
        "error",
        "complete history must explain how a record reached a non-initial state",
        "record the connected legal transitions or use reviewed legacy-unknown history",
    ),
    "document.transition-invalid": (
        "error",
        "an illegal lifecycle edge makes the declared state machine inconsistent",
        "use a legal transition for the role or correct the current state",
    ),
    "document.transition-disconnected": (
        "error",
        "transition history must form one causal path",
        "make each transition start at the preceding transition's target",
    ),
    "document.transition-initial-invalid": (
        "error",
        "complete history must begin in a legal initial state",
        "start the history at the role's documented initial state",
    ),
    "document.transition-final-state": (
        "error",
        "the transition path and declared current state must agree",
        "change the final transition or the declared state after review",
    ),
    "document.date-order-invalid": (
        "error",
        "created and updated dates must preserve causal order",
        "correct the reviewed dates so created is not later than updated",
    ),
    "document.transition-date-out-of-range": (
        "error",
        "transition evidence must fall within the record's maintained lifetime",
        "correct the transition or created/updated dates using source evidence",
    ),
    "document.transition-date-order-invalid": (
        "error",
        "transition dates must not move backward in a complete history",
        "order or correct transition dates without inventing events",
    ),
    "document.supersession-required": (
        "error",
        "a superseded record must identify one unambiguous successor",
        "add exactly one same-role superseded-by relationship",
    ),
    "document.supersession-role-mismatch": (
        "error",
        "a different role cannot replace this record's authority contract",
        "target a successor of the same role",
    ),
    "document.supersession-cycle": (
        "error",
        "cyclic successors leave no current authoritative continuation",
        "break the cycle and retain a directed acyclic supersession chain",
    ),
    "document.deliberation-link-direction": (
        "warning",
        "duplicated ADR/research links can drift and imply two owners",
        "keep one ADR derived-from research edge and remove the inverse research edge",
    ),
    "document.source-reference-missing": (
        "error",
        "decision-relevant research sources must be typed graph relationships",
        "add a derived-from relationship for each source:ID listed in the Sources section",
    ),
    "document.source-register-missing": (
        "error",
        "typed source relationships must reconcile with the research source register",
        "add the source:ID to the Sources section or remove the unsupported relationship",
    ),
}

_NONBLOCKING_CODES = {
    "document.v2-core-missing",
    "document.v2-core-invalid",
    "document.v2-projection-mismatch",
    "document.v2-extension-required",
    "document.v2-extension-forbidden",
}


def role_catalog(policy: DocsCurrencyPolicy | None) -> tuple[dict[str, Any], ...]:
    if policy is None:
        return ()
    rows = []
    for declaration in policy.roles:
        if declaration.contract is None:
            continue
        contract = ROLE_CONTRACTS[declaration.contract.role]
        rows.append(
            {
                "role": contract.role,
                "authority_kind": contract.authority_kind,
                "lifecycle": contract.lifecycle,
                "schema_version": DOCUMENT_SCHEMA_VERSION,
                "states": list(contract.states),
                "initial_states": list(contract.initial_states),
                "settled_states": list(contract.settled_states),
                "required_sections": list(contract.required_sections),
                "include": list(declaration.include),
                "index": declaration.index,
                "template": f"bundled:assets/templates/{contract.role}.md",
                "contract": asdict(declaration.contract),
            }
        )
    return tuple(rows)


def validate_typed_documents(
    root: Path,
    policy: DocsCurrencyPolicy | None,
    *,
    changed_paths: Sequence[str] = (),
    current_date: str | None = None,
) -> tuple[RoleFinding, ...]:
    return scan_typed_documents(
        root,
        policy,
        changed_paths=changed_paths,
        current_date=current_date,
    ).findings


def validate_adopted_documents(
    root: Path,
    policy: DocsCurrencyPolicy | None,
    *,
    changed_paths: Sequence[str] | None = None,
    current_date: str | None = None,
) -> tuple[DocFinding, ...]:
    """Apply currency and typed-record validation from one adopted policy input."""
    findings = (
        *validate_currency(root, policy),
        *validate_typed_documents(
            root,
            policy,
            changed_paths=changed_paths or (),
            current_date=current_date,
        ),
    )
    if changed_paths is None:
        return findings
    return _ratchet_findings(findings, changed_paths)


def validate_documents(
    root: Path,
    policy: DocsPolicy,
    paths: Sequence[str],
    *,
    changed_paths: Sequence[str] | None = None,
    current_date: str | None = None,
) -> tuple[DocFinding, ...]:
    """Apply the complete adopted Markdown and typed-document validation contract."""
    forbidden = (r"\]\(\s*file://",) if policy.forbid_legacy_links else ()
    return (
        *validate_markdown_structure(
            root,
            paths,
            required_headings=policy.required_headings,
            forbidden_patterns=forbidden,
        ),
        *validate_adopted_documents(
            root,
            policy.currency,
            changed_paths=changed_paths,
            current_date=current_date,
        ),
    )


def _ratchet_findings(
    findings: Sequence[DocFinding],
    changed_paths: Sequence[str],
) -> tuple[DocFinding, ...]:
    """Enforce changed documents while keeping an untouched migration backlog advisory."""
    changed = {
        path.removeprefix("./") for path in changed_paths if path and path.removeprefix("./")
    }
    ratcheted: list[DocFinding] = []
    for finding in findings:
        source = finding.path.removeprefix("./")
        affected = source in changed or any(
            finding.message.startswith(f"{path} ") for path in changed
        )
        if affected:
            ratcheted.append(replace(finding, severity="error", ci_blocking=True))
        else:
            ratcheted.append(replace(finding, severity="warning", ci_blocking=False))
    # Local git changes include staged, unstaged, and untracked files. A clean CI
    # checkout needs a future merge-base comparison to retain go-forward enforcement.
    return tuple(ratcheted)


def expand_markdown_paths(root: Path, patterns: Sequence[str]) -> tuple[str, ...]:
    """Expand adopted Markdown globs to contained, deterministic file paths."""

    resolved_root = root.resolve()
    found: set[str] = set()
    for pattern in patterns:
        for item in glob.glob(str(root / pattern), recursive=True):
            path = Path(item)
            if not path.is_file():
                continue
            try:
                found.add(path.resolve().relative_to(resolved_root).as_posix())
            except ValueError:
                continue
    return tuple(sorted(found))


def scan_typed_documents(
    root: Path,
    policy: DocsCurrencyPolicy | None,
    *,
    changed_paths: Sequence[str] = (),
    current_date: str | None = None,
) -> DocumentScan:
    if policy is None:
        return DocumentScan((), (), (), (), False)
    root = root.resolve()
    findings: list[RoleFinding] = []
    extracted: list[ExtractedDocument] = []
    selections: list[DocumentSelection] = []
    declarations: dict[str, DocumentRolePolicy] = {}
    declarations_by_source: dict[str, DocumentRolePolicy] = {}
    selected_sources: dict[str, str] = {}
    limit_reached = False

    for precedence, declaration in enumerate(policy.roles):
        if declaration.contract is None:
            continue
        declarations[declaration.name] = declaration
        for path, include_patterns in _expand_role(root, declaration, findings):
            source = path.relative_to(root).as_posix()
            if previous := selected_sources.get(source):
                findings.append(
                    _finding(
                        "document.source-role-overlap",
                        source,
                        1,
                        f"record is selected by both {previous!r} and {declaration.name!r}",
                    )
                )
                continue
            if len(selected_sources) >= MAX_DOCUMENTS:
                findings.append(
                    _finding(
                        "document.source-truncated",
                        ".",
                        1,
                        f"typed document scan stopped at {MAX_DOCUMENTS} documents",
                    )
                )
                limit_reached = True
                break
            selected_sources[source] = declaration.name
            item = _extract(root, path, declaration, findings)
            if item is not None:
                extracted.append(item)
                declarations_by_source[item.record.source] = declaration
                selections.append(
                    DocumentSelection(
                        item.record.source,
                        declaration.name,
                        include_patterns,
                        declaration.index,
                        precedence,
                        declaration.contract.version,
                    )
                )
        if limit_reached:
            break

    records = [item.record for item in extracted]
    for issue in validate_document_records(records):
        findings.append(_finding(issue.code, issue.source, issue.line, issue.message))

    by_source = {item.record.source: item for item in extracted}
    for item in extracted:
        _validate_body(root, item, declarations_by_source[item.record.source], findings)
    if current_date is not None:
        changed = set(changed_paths)
        for item in extracted:
            if (
                item.record.source in changed
                and _record_is_valid(item)
                and str(item.record.metadata["updated"]) < current_date
            ):
                findings.append(
                    _finding(
                        "document.updated-stale",
                        item.record.source,
                        2,
                        f"changed record still declares updated {item.record.metadata['updated']!r}; "
                        f"current UTC date is {current_date!r}",
                    )
                )
    _validate_index_states(root, declarations, by_source, findings)
    _validate_deliberation_direction(extracted, findings)
    normalized = tuple(
        sorted(
            set(findings),
            key=lambda item: (item.path, item.line, item.code, item.message),
        )
    )
    valid_sources = {item.record.source for item in extracted if _record_is_valid(item)}
    return DocumentScan(
        tuple(item.record for item in extracted if item.record.source in valid_sources),
        tuple(item for item in selections if item.source in valid_sources),
        tuple(
            DocumentProjection(item.record.source, item.summary, item.status)
            for item in extracted
            if item.record.source in valid_sources
        ),
        normalized,
        bool(normalized),
    )


def _expand_role(
    root: Path,
    declaration: DocumentRolePolicy,
    findings: list[RoleFinding],
) -> tuple[tuple[Path, tuple[str, ...]], ...]:
    found: dict[Path, list[str]] = {}
    index = (root / declaration.index).resolve()
    for pattern in declaration.include:
        for candidate in root.glob(pattern):
            if not candidate.is_file():
                continue
            try:
                resolved = candidate.resolve()
                resolved.relative_to(root)
            except (OSError, RuntimeError, ValueError):
                findings.append(
                    _finding(
                        "document.source-outside-root",
                        candidate.relative_to(root).as_posix(),
                        1,
                        "typed document source resolves outside the project",
                    )
                )
                continue
            if resolved == index:
                continue
            found.setdefault(resolved, []).append(pattern)
            if len(found) >= MAX_DOCUMENTS:
                findings.append(
                    _finding(
                        "document.source-truncated",
                        declaration.index,
                        1,
                        f"typed document scan stopped at {MAX_DOCUMENTS} documents",
                    )
                )
                return tuple((path, tuple(patterns)) for path, patterns in sorted(found.items()))
    return tuple((path, tuple(patterns)) for path, patterns in sorted(found.items()))


def _extract(
    root: Path,
    path: Path,
    declaration: DocumentRolePolicy,
    findings: list[RoleFinding],
) -> ExtractedDocument | None:
    source = path.relative_to(root).as_posix()
    data = path.read_bytes()
    if len(data) > MAX_DOCUMENT_BYTES:
        findings.append(
            _finding(
                "document.source-truncated",
                source,
                1,
                f"document exceeds {MAX_DOCUMENT_BYTES} bytes",
            )
        )
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        findings.append(
            _finding(
                "document.source-encoding-invalid",
                source,
                1,
                "document is not valid UTF-8",
            )
        )
        return None
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        findings.append(
            _finding(
                "document.frontmatter-missing",
                source,
                1,
                "document does not begin with YAML frontmatter",
            )
        )
        return None
    closing = next(
        (
            index
            for index, line in enumerate(lines[1 : MAX_FRONTMATTER_LINES + 2], 1)
            if line.strip() == "---"
        ),
        None,
    )
    if closing is None:
        findings.append(
            _finding(
                "document.frontmatter-unclosed",
                source,
                1,
                "no bounded closing delimiter was found",
            )
        )
        return None
    raw = "".join(lines[1:closing])
    if len(raw.encode("utf-8")) > MAX_FRONTMATTER_BYTES or closing > MAX_FRONTMATTER_LINES:
        findings.append(
            _finding(
                "document.frontmatter-too-large",
                source,
                1,
                "frontmatter exceeds the bounded parser limit",
            )
        )
        return None
    try:
        if any(isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in yaml.scan(raw)):
            findings.append(
                _finding(
                    "document.frontmatter-unsafe",
                    source,
                    1,
                    "frontmatter contains a YAML alias, anchor, or tag",
                )
            )
            return None
        loaded = yaml.load(raw, Loader=_UniqueKeySafeLoader)
    except (ConstructorError, RecursionError, TypeError, yaml.YAMLError) as exc:
        findings.append(
            _finding(
                "document.frontmatter-invalid",
                source,
                1,
                f"frontmatter could not be loaded safely: {exc}",
            )
        )
        return None
    loaded = _normalize_dates(loaded)
    if not isinstance(loaded, dict) or not _json_compatible(loaded):
        findings.append(
            _finding(
                "document.frontmatter-invalid",
                source,
                1,
                "frontmatter contains a non-JSON key, value, or non-finite number",
            )
        )
        return None
    if loaded.get("schema_version") == DOCUMENT_SCHEMA_VERSION:
        return _extract_v2(
            source,
            path,
            declaration,
            loaded,
            raw,
            lines,
            closing,
            findings,
        )
    _report_v2_core_migration(source, loaded, raw, findings)
    return _extract_v1(source, path, declaration, loaded, lines, closing, findings)


def _extract_v1(
    source: str,
    path: Path,
    declaration: DocumentRolePolicy,
    loaded: Mapping[str, Any],
    lines: Sequence[str],
    closing: int,
    findings: list[RoleFinding],
) -> ExtractedDocument | None:
    role = declaration.contract.role
    if role not in RECORD_ROLES:
        findings.append(
            _finding(
                "document.v2-core-invalid",
                source,
                1,
                f"generic role {role!r} requires flat schema_version: 2 frontmatter",
            )
        )
        return None
    key = declaration.contract.metadata_key
    expected_keys = {"summary", "status", key}
    if set(loaded) != expected_keys or not isinstance(loaded.get(key), dict):
        findings.append(
            _finding(
                "document.frontmatter-wrapper-invalid",
                source,
                1,
                f"legacy frontmatter must contain exactly summary, status, and one mapping named {key!r}",
            )
        )
        return None
    metadata = loaded[key]
    summary = loaded["summary"]
    if not summary_is_valid(summary):
        findings.append(
            _finding(
                "document.summary-invalid",
                source,
                2,
                f"summary must be one sentence of 1-{MAX_SUMMARY_CHARACTERS} characters",
            )
        )
    status = loaded["status"]
    if not isinstance(status, str) or status != metadata.get("state"):
        findings.append(
            _finding(
                "document.status-invalid",
                source,
                3,
                f"status {status!r} must equal engineering_document.state {metadata.get('state')!r}",
            )
        )
    if metadata.get("role") != declaration.contract.role:
        findings.append(
            _finding(
                "document.role-mismatch",
                source,
                2,
                f"expected role {declaration.contract.role!r}, found {metadata.get('role')!r}",
            )
        )
    identifier = path.name[: declaration.id_prefix_digits]
    if str(metadata.get("id")) != identifier:
        findings.append(
            _finding(
                "document.filename-id-mismatch",
                source,
                2,
                f"metadata ID {metadata.get('id')!r} does not match filename prefix {identifier!r}",
            )
        )
    if list(metadata_validator().iter_errors(metadata)):
        # The shared validator emits the stable, field-specific findings after all extraction.
        pass
    core = {
        "schema_version": 1,
        "id": metadata.get("id"),
        "uid": metadata.get("uid"),
        "title": metadata.get("title"),
        "role": metadata.get("role"),
        "status": status,
        "summary": summary,
        "created": metadata.get("created"),
        "updated": metadata.get("updated"),
    }
    return ExtractedDocument(
        DocumentContractRecord(source, metadata),
        core,
        True,
        summary if isinstance(summary, str) else "",
        status if isinstance(status, str) else "",
        "".join(lines[closing + 1 :]),
        closing + 2,
    )


def _extract_v2(
    source: str,
    path: Path,
    declaration: DocumentRolePolicy,
    loaded: Mapping[str, Any],
    raw: str,
    lines: Sequence[str],
    closing: int,
    findings: list[RoleFinding],
) -> ExtractedDocument | None:
    errors = sorted(core_metadata_validator().iter_errors(loaded), key=_schema_error_key)
    missing = set(V2_CORE_KEYS) - set(loaded)
    for key in V2_CORE_KEYS:
        if key in missing:
            findings.append(
                _finding(
                    "document.v2-core-missing",
                    source,
                    1,
                    f"required top-level v2 core key {key!r} is missing",
                )
            )
    for error in errors:
        if error.validator == "required":
            continue
        path_text = ".".join(str(part) for part in error.absolute_path) or "$"
        findings.append(
            _finding(
                "document.v2-core-invalid",
                source,
                _frontmatter_error_line(raw, error),
                f"{path_text}: {error.message}",
            )
        )
    configured_role = loaded.get("role")
    metadata_key = declaration.contract.metadata_key
    if configured_role in RECORD_ROLES and not isinstance(loaded.get(metadata_key), dict):
        findings.append(
            _finding(
                "document.v2-extension-required",
                source,
                1,
                f"record role {configured_role!r} requires one mapping named {metadata_key!r}",
            )
        )
    if configured_role in GENERIC_ROLES and metadata_key in loaded:
        findings.append(
            _finding(
                "document.v2-extension-forbidden",
                source,
                _top_level_key_line(raw, metadata_key),
                f"generic role {configured_role!r} must not carry {metadata_key}",
            )
        )
    if errors:
        return None

    role = declaration.contract.role
    if configured_role != role:
        findings.append(
            _finding(
                "document.v2-core-invalid",
                source,
                _top_level_key_line(raw, "role"),
                f"expected top-level role {role!r}, found {configured_role!r}",
            )
        )
    uid = str(loaded.get("uid", ""))
    if not uid.startswith(f"{configured_role}-"):
        findings.append(
            _finding(
                "document.v2-core-invalid",
                source,
                _top_level_key_line(raw, "uid"),
                f"UID {uid!r} must be namespaced by role {configured_role!r}",
            )
        )
    summary = loaded["summary"]
    status = loaded["status"]
    if role in GENERIC_ROLES:
        if not summary_is_valid(summary):
            findings.append(
                _finding(
                    "document.v2-core-invalid",
                    source,
                    _top_level_key_line(raw, "summary"),
                    f"summary must be one sentence of 1-{MAX_SUMMARY_CHARACTERS} characters",
                )
            )
        normalized = dict(loaded)
        normalized["state"] = status
        normalized["relationships"] = []
        return ExtractedDocument(
            DocumentContractRecord(source, normalized),
            loaded,
            False,
            str(summary),
            str(status),
            "".join(lines[closing + 1 :]),
            closing + 2,
        )

    key = declaration.contract.metadata_key
    metadata = loaded.get(key)
    if not isinstance(metadata, dict):
        findings.append(
            _finding(
                "document.v2-extension-required",
                source,
                1,
                f"record role {role!r} requires one mapping named {key!r}",
            )
        )
        return None
    if not summary_is_valid(summary):
        findings.append(
            _finding(
                "document.summary-invalid",
                source,
                _top_level_key_line(raw, "summary"),
                f"summary must be one sentence of 1-{MAX_SUMMARY_CHARACTERS} characters",
            )
        )
    if not isinstance(status, str) or status != metadata.get("state"):
        findings.append(
            _finding(
                "document.status-invalid",
                source,
                _top_level_key_line(raw, "status"),
                f"status {status!r} must equal engineering_document.state {metadata.get('state')!r}",
            )
        )
    if metadata.get("role") != role:
        findings.append(
            _finding(
                "document.role-mismatch",
                source,
                _top_level_key_line(raw, key),
                f"expected engineering_document.role {role!r}, found {metadata.get('role')!r}",
            )
        )
    for field in ("id", "uid", "title", "role", "created", "updated"):
        if loaded.get(field) != metadata.get(field):
            findings.append(
                _finding(
                    "document.v2-projection-mismatch",
                    source,
                    _top_level_key_line(raw, field),
                    f"top-level {field} {loaded.get(field)!r} must equal engineering_document.{field} {metadata.get(field)!r}",
                )
            )
    identifier = path.name[: declaration.id_prefix_digits]
    if str(loaded.get("id")) != identifier:
        findings.append(
            _finding(
                "document.filename-id-mismatch",
                source,
                _top_level_key_line(raw, "id"),
                f"metadata ID {loaded.get('id')!r} does not match filename prefix {identifier!r}",
            )
        )
    return ExtractedDocument(
        DocumentContractRecord(source, metadata),
        loaded,
        True,
        str(summary),
        str(status),
        "".join(lines[closing + 1 :]),
        closing + 2,
    )


def _report_v2_core_migration(
    source: str,
    loaded: Mapping[str, Any],
    raw: str,
    findings: list[RoleFinding],
) -> None:
    for key in V2_CORE_KEYS:
        if key not in loaded:
            findings.append(
                _finding(
                    "document.v2-core-missing",
                    source,
                    1,
                    f"required top-level v2 core key {key!r} is missing",
                )
            )
    if "schema_version" in loaded and loaded["schema_version"] != DOCUMENT_SCHEMA_VERSION:
        findings.append(
            _finding(
                "document.v2-core-invalid",
                source,
                _top_level_key_line(raw, "schema_version"),
                f"schema_version must equal {DOCUMENT_SCHEMA_VERSION}, found {loaded['schema_version']!r}",
            )
        )


def _schema_error_key(error: Any) -> tuple[str, str]:
    return (".".join(str(part) for part in error.absolute_path), error.message)


def _frontmatter_error_line(raw: str, error: Any) -> int:
    path = tuple(error.absolute_path)
    return _top_level_key_line(raw, str(path[0])) if path else 1


def _top_level_key_line(raw: str, key: str) -> int:
    pattern = re.compile(rf"^{re.escape(key)}\s*:", re.MULTILINE)
    match = pattern.search(raw)
    return raw.count("\n", 0, match.start()) + 2 if match else 1


def _normalize_dates(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _normalize_dates(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_dates(item) for item in value]
    return value


def _json_compatible(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_compatible(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_compatible(item) for key, item in value.items())
    return False


def _record_is_valid(item: ExtractedDocument) -> bool:
    validator = metadata_validator() if item.record_role else core_metadata_validator()
    return not list(validator.iter_errors(item.record.metadata))


def _validate_body(
    root: Path,
    item: ExtractedDocument,
    declaration: DocumentRolePolicy,
    findings: list[RoleFinding],
) -> None:
    if not item.record_role:
        return
    metadata = item.record.metadata
    if list(metadata_validator().iter_errors(metadata)):
        return
    headings: list[tuple[int, int, str]] = []
    tokens = MARKDOWN.parse(item.body)
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or index + 1 >= len(tokens):
            continue
        level = int(token.tag.removeprefix("h"))
        text = tokens[index + 1].content.strip()
        line = item.body_line + (token.map[0] if token.map else 0)
        headings.append((level, line, text))
    expected_title = (
        f"{ROLE_LABELS[declaration.contract.role]} {metadata['id']}: {metadata['title']}"
    )
    primary = next((heading for heading in headings if heading[0] == 1), None)
    if primary is None or primary[2] != expected_title:
        findings.append(
            _finding(
                "document.title-mismatch",
                item.record.source,
                primary[1] if primary else item.body_line,
                f"expected primary heading {expected_title!r}",
            )
        )
    present = {text.casefold() for level, _line, text in headings if level >= 2}
    for required in ROLE_CONTRACTS[declaration.contract.role].required_sections:
        if required.casefold() not in present:
            findings.append(
                _finding(
                    "document.section-missing",
                    item.record.source,
                    item.body_line,
                    f"required section {required!r} is missing",
                )
            )
    if declaration.contract.role == "task":
        _validate_task_criteria(item, findings)
    if declaration.contract.role == "research":
        _validate_research_sources(root, item, declaration, headings, findings)


def _validate_task_criteria(
    item: ExtractedDocument,
    findings: list[RoleFinding],
) -> None:
    lines = item.body.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        if match := _BODY_HEADING.match(line):
            headings.append((index, len(match.group(1)), match.group(2).strip().casefold()))
    selected = next((entry for entry in headings if entry[2] == "done when"), None)
    if selected is None:
        return
    start, level, _heading = selected
    end = next(
        (index for index, next_level, _ in headings if index > start and next_level <= level),
        len(lines),
    )
    body_ids: list[str] = []
    seen: set[str] = set()
    for index in range(start + 1, end):
        bullet = _TOP_LEVEL_BULLET.match(lines[index])
        if bullet is None:
            continue
        criterion = _CRITERION_PREFIX.match(bullet.group(1))
        line = item.body_line + index
        if criterion is None:
            findings.append(
                _finding(
                    "document.criterion-id-missing",
                    item.record.source,
                    line,
                    "Done when bullet has no leading AC-N identifier",
                )
            )
            continue
        identifier = criterion.group(1)
        body_ids.append(identifier)
        if identifier in seen:
            findings.append(
                _finding(
                    "document.criterion-id-duplicate",
                    item.record.source,
                    line,
                    f"Done when identifier {identifier!r} is repeated",
                )
            )
        seen.add(identifier)

    metadata_ids = [
        value.removeprefix("criterion:") for value in item.record.metadata["details"]["criteria"]
    ]
    if body_ids != metadata_ids:
        findings.append(
            _finding(
                "document.criteria-mismatch",
                item.record.source,
                item.body_line + start,
                f"Done when IDs {body_ids!r} do not match details.criteria {metadata_ids!r}",
            )
        )


@dataclass(frozen=True)
class ResearchSourceRegister:
    path: str
    line: int
    sources: frozenset[str]


def _validate_research_sources(
    root: Path,
    item: ExtractedDocument,
    declaration: DocumentRolePolicy,
    headings: Sequence[tuple[int, int, str]],
    findings: list[RoleFinding],
) -> None:
    selected = _research_sources_section(item, headings)
    local_sources = selected[2] if selected is not None else set()
    register = _central_research_source_register(root, item, declaration)
    source_line = (
        register.line if register is not None else (selected[1] if selected else item.body_line)
    )
    source_path = register.path if register is not None else item.record.source
    prose_sources = set(register.sources) if register is not None else local_sources
    typed_sources = {
        relationship["target"]
        for relationship in item.record.metadata.get("relationships", ())
        if relationship.get("type") == "derived-from"
        and isinstance(relationship.get("target"), str)
        and relationship["target"].startswith("source:src-")
    }
    for target in sorted(prose_sources - typed_sources):
        findings.append(
            _finding(
                "document.source-reference-missing",
                source_path,
                source_line,
                f"research source register lists {target} without a typed relationship",
            )
        )
    for target in sorted(typed_sources - prose_sources):
        findings.append(
            _finding(
                "document.source-register-missing",
                source_path,
                source_line,
                f"typed relationship {target} is absent from the research source register",
            )
        )


def _research_sources_section(
    item: ExtractedDocument,
    headings: Sequence[tuple[int, int, str]],
) -> tuple[int, int, set[str]] | None:
    selected = next(
        (entry for entry in headings if entry[2].casefold() == "sources"),
        None,
    )
    if selected is None:
        return None
    level, line, _heading = selected
    lines = item.body.splitlines()
    start = max(line - item.body_line + 1, 0)
    end = len(lines)
    for next_level, next_line, _text in headings:
        if next_line > line and next_level <= level:
            end = next_line - item.body_line
            break
    return level, line, set(_SOURCE_REFERENCE.findall("\n".join(lines[start:end])))


def _central_research_source_register(
    root: Path,
    item: ExtractedDocument,
    declaration: DocumentRolePolicy,
) -> ResearchSourceRegister | None:
    identifier = str(item.record.metadata.get("id", ""))
    if not identifier:
        return None
    fallback: ResearchSourceRegister | None = None
    for path in _research_source_register_candidates(root, declaration):
        try:
            resolved = path.resolve()
            relative = resolved.relative_to(root).as_posix()
        except (OSError, RuntimeError, ValueError):
            continue
        if not resolved.is_file():
            continue
        fallback = fallback or ResearchSourceRegister(relative, 1, frozenset())
        try:
            data = resolved.read_bytes()
        except OSError:
            continue
        if len(data) > MAX_DOCUMENT_BYTES:
            return ResearchSourceRegister(relative, 1, frozenset())
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return ResearchSourceRegister(relative, 1, frozenset())
        parsed = _registered_sources_for_research(text, identifier)
        if parsed is not None:
            line, sources = parsed
            return ResearchSourceRegister(relative, line, frozenset(sources))
    return fallback


def _research_source_register_candidates(
    root: Path,
    declaration: DocumentRolePolicy,
) -> tuple[Path, ...]:
    index_parent = (root / declaration.index).parent
    return (
        (index_parent / "source-register.md").resolve(),
        (index_parent / "../../references/SOURCES.md").resolve(),
    )


def _registered_sources_for_research(text: str, identifier: str) -> tuple[int, set[str]] | None:
    research_label = re.compile(rf"\bResearch\s+{re.escape(identifier)}\b", re.IGNORECASE)
    research_id = re.compile(rf"\bresearch:{re.escape(identifier)}\b", re.IGNORECASE)
    lines = text.splitlines()
    block: list[str] = []
    start = 1
    for index, line in enumerate((*lines, ""), 1):
        if line.strip():
            if not block:
                start = index
            block.append(line)
            continue
        if not block:
            continue
        joined = "\n".join(block)
        if research_label.search(joined) or research_id.search(joined):
            return start, set(_SOURCE_REFERENCE.findall(joined))
        block = []
    return None


def _validate_index_states(
    root: Path,
    declarations: Mapping[str, DocumentRolePolicy],
    by_source: Mapping[str, ExtractedDocument],
    findings: list[RoleFinding],
) -> None:
    for declaration in declarations.values():
        if not declaration.states:
            continue
        candidate = root / declaration.index
        try:
            index = candidate.resolve()
            index.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            findings.append(
                _finding(
                    "document.source-outside-root",
                    declaration.index,
                    1,
                    "typed role index resolves outside the project",
                )
            )
            continue
        if not index.is_file():
            continue
        data = index.read_bytes()
        if len(data) > MAX_DOCUMENT_BYTES:
            findings.append(
                _finding(
                    "document.source-truncated",
                    declaration.index,
                    1,
                    f"typed role index exceeds {MAX_DOCUMENT_BYTES} bytes",
                )
            )
            continue
        try:
            lines = data.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            findings.append(
                _finding(
                    "document.source-encoding-invalid",
                    declaration.index,
                    1,
                    "typed role index is not valid UTF-8",
                )
            )
            continue
        for token in MARKDOWN.parse("\n".join(lines)):
            if token.type != "inline":
                continue
            line = token.map[0] + 1 if token.map else 1
            source_line = lines[line - 1] if line <= len(lines) else ""
            cells = {cell.strip() for cell in table_cells(source_line)}
            states = [state for state in declaration.states if state in cells]
            if len(states) != 1:
                continue
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
                    source = candidate.relative_to(root).as_posix()
                except ValueError:
                    continue
                item = by_source.get(source)
                if item is not None and item.record.metadata.get("state") != states[0]:
                    findings.append(
                        _finding(
                            "document.index-state-mismatch",
                            declaration.index,
                            line,
                            f"{source} metadata state {item.record.metadata.get('state')!r} "
                            f"does not equal index state {states[0]!r}",
                        )
                    )


def _validate_deliberation_direction(
    documents: Sequence[ExtractedDocument],
    findings: list[RoleFinding],
) -> None:
    for item in documents:
        metadata = item.record.metadata
        for relationship in metadata.get("relationships", ()):
            role = metadata.get("role")
            target = str(relationship.get("target", ""))
            valid = (
                role == "adr"
                and target.startswith("research:")
                and relationship.get("type") == "derived-from"
            )
            cross_role = (role == "adr" and target.startswith("research:")) or (
                role == "research" and target.startswith("adr:")
            )
            if cross_role and not valid:
                findings.append(
                    _finding(
                        "document.deliberation-link-direction",
                        item.record.source,
                        1,
                        "ADR/research deliberation links are recorded once as ADR derived-from research",
                    )
                )


def _finding(code: str, path: str, line: int, message: str) -> RoleFinding:
    severity, rationale, repair = _RULES.get(
        code,
        (
            "error",
            "typed document metadata must satisfy its adopted schema and lifecycle",
            "repair the field using the role contract and template",
        ),
    )
    return RoleFinding(
        path,
        line,
        code,
        message,
        severity,
        rationale,
        repair,
        code not in _NONBLOCKING_CODES,
    )
