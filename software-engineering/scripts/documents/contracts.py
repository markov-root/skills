"""Versioned metadata and lifecycle contracts for explicitly adopted document roles."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jsonschema

from ..resources import schema_path

DOCUMENT_CONTRACT_VERSION = 1
DOCUMENT_SCHEMA_VERSION = 2
# Preserve the published v1 graph namespace order while serving as the single
# source of truth for roles that carry lifecycle/relationship extensions.
RECORD_ROLES = ("task", "adr", "audit", "research", "lesson", "handoff")
GENERIC_ROLES = (
    "specification",
    "knowledge",
    "reference",
    "standard",
    "guide",
    "roadmap",
    "changelog",
    "runbook",
    "index",
    "template",
)
DOCUMENT_ROLES = (*RECORD_ROLES, *GENERIC_ROLES)
RELATIONSHIP_TYPES = (
    "refined-by",
    "decided-by",
    "implemented-by",
    "verified-by",
    "evidenced-by",
    "validated-by",
    "superseded-by",
    "depends-on",
    "continues",
    "derived-from",
    "dispositions",
)
RELATIONSHIP_DETAIL_PROJECTIONS = {
    "task": (("depends_on", "depends-on"), ("evidence", "evidenced-by")),
    "audit": (("evidence", "evidenced-by"),),
    "research": (("sources", "derived-from"),),
    "lesson": (
        ("derived_from", "derived-from"),
        ("resulting_changes", "implemented-by"),
    ),
}


@dataclass(frozen=True)
class DocumentRoleContract:
    role: str
    authority_kind: str | None
    states: tuple[str, ...]
    initial_states: tuple[str, ...]
    settled_states: tuple[str, ...]
    transitions: frozenset[tuple[str, str]]
    required_sections: tuple[str, ...]
    lifecycle: bool = True


@dataclass(frozen=True)
class DocumentContractRecord:
    source: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True, order=True)
class DocumentContractFinding:
    source: str
    code: str
    message: str
    line: int = 1


def project_relationship_details(metadata: Mapping[str, Any]) -> dict[str, list[str]]:
    """Derive legacy role-detail reference views from the sole authored edge store."""
    relationships = metadata.get("relationships", ())
    return {
        field: [
            str(relationship["target"])
            for relationship in relationships
            if relationship.get("type") == relationship_type
        ]
        for field, relationship_type in RELATIONSHIP_DETAIL_PROJECTIONS.get(
            str(metadata.get("role")), ()
        )
    }


def _edges(*pairs: tuple[str, str]) -> frozenset[tuple[str, str]]:
    return frozenset(pairs)


ROLE_CONTRACTS = {
    "task": DocumentRoleContract(
        "task",
        "work-state",
        ("todo", "partial", "blocked", "done", "superseded"),
        ("todo",),
        ("done", "superseded"),
        _edges(
            ("todo", "partial"),
            ("todo", "blocked"),
            ("todo", "done"),
            ("todo", "superseded"),
            ("partial", "todo"),
            ("partial", "blocked"),
            ("partial", "done"),
            ("partial", "superseded"),
            ("blocked", "todo"),
            ("blocked", "partial"),
            ("blocked", "done"),
            ("blocked", "superseded"),
            ("done", "superseded"),
        ),
        ("Problem", "Scope", "Out of scope", "Done when", "Completion evidence"),
    ),
    "adr": DocumentRoleContract(
        "adr",
        "decision-record",
        ("proposed", "accepted", "rejected", "deprecated", "superseded"),
        ("proposed",),
        ("accepted", "rejected", "deprecated", "superseded"),
        _edges(
            ("proposed", "accepted"),
            ("proposed", "rejected"),
            ("proposed", "superseded"),
            ("accepted", "deprecated"),
            ("accepted", "superseded"),
        ),
        ("Context", "Decision", "Consequences", "Alternatives considered"),
    ),
    "audit": DocumentRoleContract(
        "audit",
        "point-in-time-evidence",
        ("draft", "final", "superseded"),
        ("draft",),
        ("final", "superseded"),
        _edges(("draft", "final"), ("draft", "superseded"), ("final", "superseded")),
        ("Scope", "Method", "Findings", "Limitations", "Disposition"),
    ),
    "research": DocumentRoleContract(
        "research",
        "research-record",
        ("planned", "active", "concluded", "inconclusive", "superseded"),
        ("planned",),
        ("concluded", "inconclusive", "superseded"),
        _edges(
            ("planned", "active"),
            ("planned", "superseded"),
            ("active", "concluded"),
            ("active", "inconclusive"),
            ("active", "superseded"),
            ("concluded", "superseded"),
            ("inconclusive", "superseded"),
        ),
        (
            "Question",
            "Method",
            "Sources",
            "Findings",
            "Uncertainty and limitations",
            "Conclusion",
        ),
    ),
    "lesson": DocumentRoleContract(
        "lesson",
        "reusable-inference",
        ("draft", "standing", "superseded"),
        ("draft",),
        ("standing", "superseded"),
        _edges(("draft", "standing"), ("draft", "superseded"), ("standing", "superseded")),
        ("Context", "Durable lesson", "Boundary", "Evidence", "Consequence"),
    ),
    "handoff": DocumentRoleContract(
        "handoff",
        "continuation-state",
        ("current", "superseded"),
        ("current",),
        ("superseded",),
        _edges(("current", "superseded")),
        ("Outcome", "Completed work", "Open work", "Blockers", "Resume"),
    ),
}

ROLE_CONTRACTS.update(
    {
        role: DocumentRoleContract(role, None, (), (), (), frozenset(), (), lifecycle=False)
        for role in GENERIC_ROLES
    }
)


@lru_cache(maxsize=1)
def metadata_validator() -> jsonschema.Draft202012Validator:
    path = schema_path("document-metadata-v1.schema.json")
    schema = json.loads(path.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )


@lru_cache(maxsize=1)
def core_metadata_validator() -> jsonschema.Draft202012Validator:
    path = schema_path("document-metadata-v2.schema.json")
    schema = json.loads(path.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )


def validate_document_records(
    records: Sequence[DocumentContractRecord],
) -> tuple[DocumentContractFinding, ...]:
    """Validate already-extracted metadata without scanning or changing repository files."""
    findings: list[DocumentContractFinding] = []
    valid_records: list[DocumentContractRecord] = []
    identities: dict[str, list[DocumentContractRecord]] = {}
    uids: dict[tuple[str, str], list[DocumentContractRecord]] = {}

    for record in records:
        role = str(record.metadata.get("role", ""))
        validator = metadata_validator() if role in RECORD_ROLES else core_metadata_validator()
        errors = sorted(validator.iter_errors(record.metadata), key=_error_key)
        if errors:
            for error in errors:
                code = _schema_code(error) if role in RECORD_ROLES else _core_schema_code(error)
                path = ".".join(str(part) for part in error.absolute_path) or "$"
                findings.append(
                    DocumentContractFinding(
                        record.source,
                        code,
                        f"{path}: {error.message}",
                    )
                )
            continue
        valid_records.append(record)
        identity = _identity(record.metadata)
        identities.setdefault(identity, []).append(record)
        uid_identity = (str(record.metadata["role"]), str(record.metadata["uid"]))
        uids.setdefault(uid_identity, []).append(record)
        if role in RECORD_ROLES:
            findings.extend(_validate_record_semantics(record))
        else:
            findings.extend(_validate_generic_semantics(record))

    for identity, matching_records in sorted(identities.items()):
        if len(matching_records) < 2:
            continue
        collision = ", ".join(record.source for record in matching_records)
        for record in matching_records:
            findings.append(
                DocumentContractFinding(
                    record.source,
                    "document.duplicate-id",
                    f"{identity} is declared by: {collision}",
                )
            )

    for (role, uid), matching_records in sorted(uids.items()):
        if len(matching_records) < 2:
            continue
        collision = ", ".join(record.source for record in matching_records)
        for record in matching_records:
            findings.append(
                DocumentContractFinding(
                    record.source,
                    "document.duplicate-uid",
                    f"{role} UID {uid!r} is declared by: {collision}",
                )
            )

    known = set(identities)
    for record in valid_records:
        source_identity = _identity(record.metadata)
        for relationship in record.metadata.get("relationships", ()):
            target = relationship["target"]
            if target not in known and target.split(":", 1)[0] in DOCUMENT_ROLES:
                findings.append(
                    DocumentContractFinding(
                        record.source,
                        "document.relationship-target-missing",
                        f"{source_identity} {relationship['type']} target {target} is not present",
                    )
                )
    findings.extend(_supersession_cycles(valid_records))
    return tuple(sorted(set(findings)))


def _validate_record_semantics(
    record: DocumentContractRecord,
) -> tuple[DocumentContractFinding, ...]:
    metadata = record.metadata
    role = str(metadata["role"])
    state = str(metadata["state"])
    contract = ROLE_CONTRACTS[role]
    findings: list[DocumentContractFinding] = []
    transitions = metadata["transitions"]
    history = metadata["transition_history"]

    findings.extend(_validate_dates(record))

    if history in {"legacy-unknown", "unverified"}:
        if transitions:
            findings.append(
                DocumentContractFinding(
                    record.source,
                    "document.transition-history-invalid",
                    f"{history} transition history must not contain asserted transitions",
                )
            )
        if history == "unverified" and state not in contract.initial_states:
            findings.append(
                DocumentContractFinding(
                    record.source,
                    "document.transition-history-incomplete",
                    f"unverified history for {role}:{metadata['id']} must remain in an initial state",
                )
            )
    elif not transitions:
        if state not in contract.initial_states:
            findings.append(
                DocumentContractFinding(
                    record.source,
                    "document.transition-history-incomplete",
                    f"complete history for {role}:{metadata['id']} cannot begin at state {state!r}",
                )
            )
    else:
        previous: str | None = None
        for index, transition in enumerate(transitions):
            edge = (transition["from"], transition["to"])
            if edge not in contract.transitions:
                findings.append(
                    DocumentContractFinding(
                        record.source,
                        "document.transition-invalid",
                        f"transitions[{index}] {edge[0]!r} -> {edge[1]!r} is illegal for {role}",
                    )
                )
            if previous is not None and transition["from"] != previous:
                findings.append(
                    DocumentContractFinding(
                        record.source,
                        "document.transition-disconnected",
                        f"transitions[{index}].from does not equal the preceding target {previous!r}",
                    )
                )
            previous = transition["to"]
        if transitions[0]["from"] not in contract.initial_states:
            findings.append(
                DocumentContractFinding(
                    record.source,
                    "document.transition-initial-invalid",
                    f"history begins at non-initial state {transitions[0]['from']!r}",
                )
            )
        if previous != state:
            findings.append(
                DocumentContractFinding(
                    record.source,
                    "document.transition-final-state",
                    f"history ends at {previous!r}, not declared state {state!r}",
                )
            )

    supersession = [
        relationship
        for relationship in metadata["relationships"]
        if relationship["type"] == "superseded-by"
    ]
    if state == "superseded" and len(supersession) != 1:
        findings.append(
            DocumentContractFinding(
                record.source,
                "document.supersession-required",
                "a superseded record must name exactly one superseded-by target",
            )
        )
    for relationship in supersession:
        target_role = relationship["target"].split(":", 1)[0]
        if target_role != role:
            findings.append(
                DocumentContractFinding(
                    record.source,
                    "document.supersession-role-mismatch",
                    f"{role} may only be superseded by another {role} record",
                )
            )

    seen_relationships: set[tuple[str, str]] = set()
    for relationship in metadata["relationships"]:
        identity = (relationship["type"], relationship["target"])
        if identity in seen_relationships:
            findings.append(
                DocumentContractFinding(
                    record.source,
                    "document.relationship-duplicate",
                    f"relationship {identity[0]} -> {identity[1]} is declared more than once",
                )
            )
        seen_relationships.add(identity)
    return tuple(findings)


def _validate_generic_semantics(
    record: DocumentContractRecord,
) -> tuple[DocumentContractFinding, ...]:
    metadata = record.metadata
    if str(metadata["created"]) <= str(metadata["updated"]):
        return ()
    return (
        DocumentContractFinding(
            record.source,
            "document.date-order-invalid",
            f"created date {metadata['created']} is later than updated date {metadata['updated']}",
        ),
    )


def _validate_dates(
    record: DocumentContractRecord,
) -> tuple[DocumentContractFinding, ...]:
    metadata = record.metadata
    created = metadata["created"]
    updated = metadata["updated"]
    findings: list[DocumentContractFinding] = []
    if created > updated:
        findings.append(
            DocumentContractFinding(
                record.source,
                "document.date-order-invalid",
                f"created date {created} is later than updated date {updated}",
            )
        )

    previous = created
    for index, transition in enumerate(metadata["transitions"]):
        at = transition["at"]
        if at < created or at > updated:
            findings.append(
                DocumentContractFinding(
                    record.source,
                    "document.transition-date-out-of-range",
                    f"transitions[{index}].at {at} is outside {created} through {updated}",
                )
            )
        if at < previous:
            findings.append(
                DocumentContractFinding(
                    record.source,
                    "document.transition-date-order-invalid",
                    f"transitions[{index}].at {at} precedes {previous}",
                )
            )
        previous = at
    return tuple(findings)


def _supersession_cycles(
    records: Sequence[DocumentContractRecord],
) -> tuple[DocumentContractFinding, ...]:
    edges: dict[str, str] = {}
    sources: dict[str, str] = {}
    for record in records:
        identity = _identity(record.metadata)
        sources[identity] = record.source
        supersession = [
            relationship["target"]
            for relationship in record.metadata.get("relationships", ())
            if relationship["type"] == "superseded-by"
        ]
        if len(supersession) == 1:
            edges[identity] = supersession[0]

    findings: list[DocumentContractFinding] = []
    visited: set[str] = set()
    for origin in sorted(edges):
        if origin in visited:
            continue
        order: list[str] = []
        positions: dict[str, int] = {}
        current = origin
        while current in edges:
            if current in positions:
                cycle = order[positions[current] :]
                first = min(range(len(cycle)), key=cycle.__getitem__)
                cycle = cycle[first:] + cycle[:first]
                cycle.append(cycle[0])
                findings.append(
                    DocumentContractFinding(
                        sources.get(cycle[0], "."),
                        "document.supersession-cycle",
                        "supersession cycle: " + " -> ".join(cycle),
                    )
                )
                break
            if current in visited:
                break
            positions[current] = len(order)
            order.append(current)
            current = edges[current]
        visited.update(order)
    return tuple(findings)


def _identity(metadata: Mapping[str, Any]) -> str:
    return f"{metadata['role']}:{metadata['id']}"


def _error_key(error: jsonschema.ValidationError) -> tuple[str, str]:
    return (".".join(str(part) for part in error.absolute_path), error.message)


def _schema_code(error: jsonschema.ValidationError) -> str:
    path = tuple(error.absolute_path)
    if path == ("version",):
        return "document.version-unsupported"
    if path == ("role",):
        return "document.role-unsupported"
    if path == ("uid",):
        return "document.uid-invalid"
    return "document.metadata-invalid"


def _core_schema_code(error: jsonschema.ValidationError) -> str:
    if error.validator == "required":
        return "document.v2-core-missing"
    return "document.v2-core-invalid"
