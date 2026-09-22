"""Cached cross-role document index and structured body projections."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..policy.document_paths import DocumentContainment, DocumentContainmentError
from ..policy.manifest import DocsCurrencyPolicy
from .contracts import DOCUMENT_ROLES, DocumentContractRecord
from .validation import (
    DocumentProjection,
    DocumentScan,
    DocumentSelection,
    RoleFinding,
    scan_typed_documents,
)

INDEX_SCHEMA_VERSION = 1
INDEX_CACHE = ".engineering/document-index-v1.json"
INPUT_FINGERPRINT_VERSION = "document-index-inputs-v2"
SOURCE_REGISTER_CANDIDATES = ("source-register.md", "../../references/SOURCES.md")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FRONTMATTER_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", re.MULTILINE)


@dataclass(frozen=True)
class DocumentIndex:
    scan: DocumentScan
    entries: tuple[dict[str, Any], ...]
    cache: dict[str, Any]


def load_document_index(
    root: Path,
    policy: DocsCurrencyPolicy | None,
    *,
    docs_root: Path | None = None,
    workspace_root: Path | None = None,
    project_id: str | None = None,
) -> DocumentIndex:
    """Load a fresh cached scan, regenerating when role policy or sources changed."""

    root = root.resolve()
    containment = _index_containment(root, docs_root, workspace_root, project_id)
    fingerprint = _policy_fingerprint(policy, project_id=project_id)
    sources = _source_fingerprints(root, policy, containment=containment)
    cache_path = _index_cache_path(root, containment)
    cache_relative = cache_path.relative_to(root).as_posix()
    cached = _read_cache(cache_path)
    status = "missing"
    reason = "cache file is absent"
    if cached is not None:
        status, reason = _cache_status(
            cached,
            fingerprint,
            sources,
            project_id=project_id,
        )
        if status == "hit" and containment is not None:
            status, reason = _cached_scope_status(cached, policy, containment)
        if status == "hit":
            scan = _scan_from_cache(cached)
            return DocumentIndex(
                scan,
                tuple(cached.get("entries", ())),
                _cache_report(root, cache_relative, "hit", False, reason, sources),
            )

    scan = scan_typed_documents(root, policy, containment=containment)
    entries = _entries(root, scan, containment=containment)
    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "policy_fingerprint": fingerprint,
        "sources": list(sources),
        "scan": _scan_to_cache(scan),
        "entries": list(entries),
    }
    if project_id is not None:
        payload["project_id"] = project_id
    write_status = "regenerated"
    write_reason = reason if status != "missing" else "cache file was absent"
    try:
        _write_cache(cache_path, payload, containment=containment)
    except OSError as exc:
        write_status = "unavailable"
        write_reason = f"cache could not be written: {exc}"
    return DocumentIndex(
        scan,
        entries,
        _cache_report(
            root,
            cache_relative,
            write_status,
            status != "hit",
            write_reason,
            sources,
        ),
    )


def list_documents(
    index: DocumentIndex,
    *,
    role: str | None = None,
    state: str | None = None,
    state_not: str | None = None,
) -> dict[str, Any]:
    if role is not None and role not in DOCUMENT_ROLES:
        raise ValueError(f"unsupported document role: {role}")
    if state is not None and state_not is not None:
        raise ValueError("--state and --state-not are mutually exclusive")
    rows = [
        item
        for item in index.entries
        if (role is None or item["role"] == role)
        and (state is None or item["state"] == state)
        and (state_not is None or item["state"] != state_not)
    ]
    return {
        "count": len(rows),
        "filters": {"role": role, "state": state, "state_not": state_not},
        "documents": rows,
        "cache": index.cache,
        "limitations": [
            "Summaries are authored retrieval projections, not acceptance, decision, or evidence authority.",
            "List output is selected from adopted typed roles only.",
        ],
    }


def show_document(
    index: DocumentIndex,
    root: Path,
    identifier: str,
    *,
    docs_root: Path | None = None,
) -> dict[str, Any]:
    matches = _matches(index.entries, identifier)
    if not matches:
        raise KeyError(f"unknown document identifier: {identifier}")
    if len(matches) > 1:
        choices = ", ".join(item["id"] for item in matches)
        raise ValueError(f"ambiguous document identifier {identifier!r}: {choices}")
    entry = matches[0]
    containment = (
        None if docs_root is None else DocumentContainment.for_project_docs(root, docs_root)
    )
    return {
        "document": entry,
        "body": _structured_body(
            root,
            entry["provenance"]["path"],
            containment=containment,
        ),
        "cache": index.cache,
        "limitations": [
            "Body sections preserve Markdown for summarization but do not validate prose truth.",
            "Only explicit headings define sections; prose links are not promoted to relationships.",
        ],
    }


def _policy_fingerprint(
    policy: DocsCurrencyPolicy | None,
    *,
    project_id: str | None = None,
) -> str:
    data = asdict(policy) if policy is not None else None
    if project_id is not None:
        data = {"project_id": project_id, "policy": data}
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_fingerprints(
    root: Path,
    policy: DocsCurrencyPolicy | None,
    *,
    containment: DocumentContainment | None = None,
) -> tuple[dict[str, Any], ...]:
    if policy is None:
        return ()
    if containment is not None:
        return _contained_source_fingerprints(root, policy, containment)
    selected: dict[str, dict[str, Any]] = {}
    for declaration in policy.roles:
        if declaration.contract is None:
            continue
        index = (root / declaration.index).resolve()
        _add_source_fingerprint(
            selected,
            root,
            index,
            role=declaration.name,
            kind="role-index",
        )
        if declaration.contract.role == "research":
            for register in _source_register_candidates(root, declaration):
                _add_source_fingerprint(
                    selected,
                    root,
                    register,
                    role=declaration.name,
                    kind="source-register",
                )
        for pattern in declaration.include:
            for candidate in root.glob(pattern):
                if not candidate.is_file():
                    continue
                try:
                    resolved = candidate.resolve()
                except (OSError, RuntimeError, ValueError):
                    continue
                if resolved == index:
                    continue
                _add_source_fingerprint(
                    selected,
                    root,
                    resolved,
                    role=declaration.name,
                    kind="document",
                )
    return tuple(selected[key] for key in sorted(selected))


def _index_containment(
    root: Path,
    docs_root: Path | None,
    workspace_root: Path | None,
    project_id: str | None,
) -> DocumentContainment | None:
    if docs_root is None and workspace_root is None and project_id is None:
        return None
    if docs_root is None or workspace_root is None or project_id is None:
        raise ValueError("docs_root, workspace_root, and project_id must be supplied together")
    return DocumentContainment.for_project_roots(
        root,
        workspace_root,
        docs_root,
        project_id=project_id,
    )


def _index_cache_path(root: Path, containment: DocumentContainment | None) -> Path:
    if containment is None:
        return root / INDEX_CACHE
    return containment.require_project_cache_path(
        "document-index-v1.json",
        purpose="document index cache",
        must_exist=False,
    )


def _contained_source_fingerprints(
    root: Path,
    policy: DocsCurrencyPolicy,
    containment: DocumentContainment,
) -> tuple[dict[str, Any], ...]:
    selected: dict[str, dict[str, Any]] = {}
    for declaration in policy.roles:
        if declaration.contract is None:
            continue
        index = containment.require_project_path(
            declaration.index,
            purpose=f"{declaration.name} role index fingerprint",
            must_exist=False,
        )
        _add_source_fingerprint(
            selected,
            root,
            index,
            role=declaration.name,
            kind="role-index",
        )
        if declaration.contract.role == "research":
            for register in _source_register_candidates(root, declaration):
                try:
                    bounded_register = containment.require_workspace_path(
                        register,
                        purpose="research source register fingerprint",
                    )
                except DocumentContainmentError:
                    continue
                _add_source_fingerprint(
                    selected,
                    root,
                    bounded_register,
                    role=declaration.name,
                    kind="source-register",
                )
        for pattern in declaration.include:
            for candidate in containment.expand_project_glob(
                pattern,
                purpose=f"{declaration.name} document fingerprint",
            ):
                if candidate == index:
                    continue
                _add_source_fingerprint(
                    selected,
                    root,
                    candidate,
                    role=declaration.name,
                    kind="document",
                )
    return tuple(selected[key] for key in sorted(selected))


def _source_register_candidates(root: Path, declaration: Any) -> tuple[Path, ...]:
    index_parent = (root / declaration.index).parent
    return tuple((index_parent / candidate).resolve() for candidate in SOURCE_REGISTER_CANDIDATES)


def _add_source_fingerprint(
    selected: dict[str, dict[str, Any]],
    root: Path,
    path: Path,
    *,
    role: str,
    kind: str,
) -> None:
    try:
        resolved = path.resolve()
        relative = resolved.relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError):
        return
    if not resolved.is_file():
        return
    try:
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except OSError:
        return
    selected[relative] = {
        "path": relative,
        "role": role,
        "kind": kind,
        "digest": digest,
        "contract_version": INPUT_FINGERPRINT_VERSION,
    }


def _read_cache(path: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _cache_status(
    cached: dict[str, Any],
    fingerprint: str,
    sources: tuple[dict[str, Any], ...],
    *,
    project_id: str | None = None,
) -> tuple[str, str]:
    if cached.get("schema_version") != INDEX_SCHEMA_VERSION:
        return "stale", "cache schema version changed"
    if cached.get("policy_fingerprint") != fingerprint:
        return "stale", "adopted role policy changed"
    if project_id is not None and cached.get("project_id") != project_id:
        return "stale", "selected document project changed"
    if cached.get("sources") != list(sources):
        return "stale", "selected document sources changed"
    return "hit", "policy and selected source digests match"


def _cached_scope_status(
    cached: dict[str, Any],
    policy: DocsCurrencyPolicy | None,
    containment: DocumentContainment,
) -> tuple[str, str]:
    allowed_roles = {
        declaration.name
        for declaration in (() if policy is None else policy.roles)
        if declaration.contract is not None
    }
    scan = cached.get("scan")
    entries = cached.get("entries")
    if not isinstance(scan, dict) or not isinstance(entries, list):
        return "stale", "cached document scope data is malformed"
    scoped_rows = (
        (scan.get("records"), True),
        (scan.get("selections"), True),
        (scan.get("projections"), False),
        (entries, True),
    )
    try:
        for rows, require_role in scoped_rows:
            if not isinstance(rows, list):
                return "stale", "cached document scope data is malformed"
            for row in rows:
                if not isinstance(row, dict):
                    return "stale", "cached document scope data is malformed"
                for source in _cached_sources(row):
                    containment.require_project_path(
                        source,
                        purpose="cached document source",
                    )
                if require_role:
                    role = _cached_role(row)
                    if role not in allowed_roles:
                        return "stale", "cached document role is outside selected project policy"
    except (DocumentContainmentError, KeyError, TypeError, ValueError):
        return "stale", "cached document path is outside selected project docs_root"
    return "hit", "policy, selected source digests, and project scope match"


def _cached_sources(row: dict[str, Any]) -> tuple[str, ...]:
    sources: list[Any] = []
    if "source" in row:
        sources.append(row["source"])
    if "index" in row:
        sources.append(row["index"])
    for key in ("provenance", "summary_provenance"):
        provenance = row.get(key)
        if provenance is not None:
            if not isinstance(provenance, dict):
                raise TypeError("cached entry provenance must be an object")
            sources.append(provenance.get("path"))
    freshness = row.get("freshness")
    if freshness is not None:
        if not isinstance(freshness, dict):
            raise TypeError("cached freshness must be an object")
        provenance = freshness.get("provenance")
        if not isinstance(provenance, dict):
            raise TypeError("cached freshness provenance must be an object")
        sources.append(provenance.get("path"))
    selection = row.get("selection")
    if selection is not None:
        if not isinstance(selection, dict):
            raise TypeError("cached selection must be an object")
        sources.extend((selection.get("source"), selection.get("index")))
    if not sources or any(not isinstance(source, str) for source in sources):
        raise TypeError("cached document source must be a string")
    return tuple(sources)


def _cached_role(row: dict[str, Any]) -> str:
    role = row.get("role")
    if role is None:
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            raise TypeError("cached record metadata must be an object")
        role = metadata.get("role")
    if not isinstance(role, str):
        raise TypeError("cached document role must be a string")
    return role


def _write_cache(
    path: Path,
    payload: dict[str, Any],
    *,
    containment: DocumentContainment | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if containment is not None:
        path = containment.require_project_cache_path(
            path.name,
            purpose="document index cache",
            must_exist=False,
        )
    temporary = path.with_name(f".{path.name}.tmp")
    if containment is not None:
        temporary = containment.require_project_cache_path(
            temporary.name,
            purpose="document index temporary cache",
            must_exist=False,
        )
    temporary.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _cache_report(
    root: Path,
    path: str,
    status: str,
    stale: bool,
    reason: str,
    sources: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    return {
        "path": path,
        "status": status,
        "stale": stale,
        "reason": reason,
        "source_count": len(sources),
        "root": str(root),
    }


def _scan_to_cache(scan: DocumentScan) -> dict[str, Any]:
    return {
        "records": [asdict(item) for item in scan.records],
        "selections": [asdict(item) for item in scan.selections],
        "projections": [asdict(item) for item in scan.projections],
        "findings": [asdict(item) for item in scan.findings],
        "partial": scan.partial,
    }


def _scan_from_cache(payload: dict[str, Any]) -> DocumentScan:
    scan = payload.get("scan", {})
    return DocumentScan(
        tuple(DocumentContractRecord(**item) for item in scan.get("records", ())),
        tuple(DocumentSelection(**item) for item in scan.get("selections", ())),
        tuple(DocumentProjection(**item) for item in scan.get("projections", ())),
        tuple(RoleFinding(**item) for item in scan.get("findings", ())),
        bool(scan.get("partial", False)),
    )


def _entries(
    root: Path,
    scan: DocumentScan,
    *,
    containment: DocumentContainment | None = None,
) -> tuple[dict[str, Any], ...]:
    selections = {item.source: item for item in scan.selections}
    projections = {item.source: item for item in scan.projections}
    rows = []
    for record in scan.records:
        metadata = record.metadata
        projection = projections.get(record.source)
        rows.append(
            {
                "id": f"{metadata['role']}:{metadata['id']}",
                "document_id": str(metadata["id"]),
                "uid": str(metadata["uid"]),
                "role": str(metadata["role"]),
                "title": str(metadata["title"]),
                "state": str(metadata.get("state", metadata.get("status", ""))),
                "summary": projection.summary if projection else metadata.get("summary"),
                "summary_provenance": {
                    "path": record.source,
                    "line": _frontmatter_line(
                        root,
                        record.source,
                        "summary",
                        containment=containment,
                    ),
                    "field": "summary",
                },
                "freshness": {
                    "created": metadata.get("created"),
                    "updated": metadata.get("updated"),
                    "freshness": metadata.get("freshness"),
                    "provenance": {
                        "path": record.source,
                        "line": _frontmatter_line(
                            root,
                            record.source,
                            "updated",
                            containment=containment,
                        ),
                    },
                },
                "provenance": {"path": record.source, "line": 1},
                "selection": asdict(selections[record.source])
                if record.source in selections
                else None,
                "relationships": list(metadata.get("relationships", ())),
            }
        )
    return tuple(sorted(rows, key=lambda item: (item["role"], item["document_id"], item["id"])))


def _frontmatter_line(
    root: Path,
    source: str,
    key: str,
    *,
    containment: DocumentContainment | None = None,
) -> int:
    try:
        path = (
            root / source
            if containment is None
            else containment.require_project_path(
                source,
                purpose="document index frontmatter source",
            )
        )
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 1
    if not text.startswith("---"):
        return 1
    closing = text.find("\n---", 4)
    raw = text[4:closing] if closing >= 0 else text
    for match in _FRONTMATTER_KEY.finditer(raw):
        if match.group(1) == key:
            return raw.count("\n", 0, match.start()) + 2
    return 1


def _matches(entries: tuple[dict[str, Any], ...], identifier: str) -> list[dict[str, Any]]:
    if ":" in identifier:
        return [item for item in entries if item["id"] == identifier]
    return [
        item for item in entries if item["document_id"] == identifier or item["uid"] == identifier
    ]


def _structured_body(
    root: Path,
    source: str,
    *,
    containment: DocumentContainment | None = None,
) -> dict[str, Any]:
    path = (
        root / source
        if containment is None
        else containment.require_project_path(
            source,
            purpose="document show source",
        )
    )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"document body is unavailable: {source}") from exc
    lines = text.splitlines()
    body_start = 0
    if lines and lines[0].strip() == "---":
        try:
            body_start = lines.index("---", 1) + 1
        except ValueError:
            body_start = 0
    headings: list[dict[str, Any]] = []
    for index, line in enumerate(lines[body_start:], start=body_start):
        if match := _HEADING.match(line):
            headings.append(
                {
                    "level": len(match.group(1)),
                    "heading": match.group(2).strip(),
                    "line": index + 1,
                    "index": index,
                }
            )
    sections = []
    for position, heading in enumerate(headings):
        end = headings[position + 1]["index"] if position + 1 < len(headings) else len(lines)
        content = "\n".join(lines[heading["index"] + 1 : end]).strip()
        sections.append(
            {
                "heading": heading["heading"],
                "level": heading["level"],
                "content": content,
                "provenance": {"path": source, "line": heading["line"]},
            }
        )
    return {
        "format": "work-packet-v1",
        "primary_heading": sections[0] if sections else None,
        "sections": sections,
        "provenance": {"path": source, "line": body_start + 1},
    }
