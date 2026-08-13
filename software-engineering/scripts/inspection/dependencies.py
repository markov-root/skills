"""Bounded dependency-evidence imports and population-aware reconciliation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

MAX_IMPORTS = 16
MAX_IMPORT_BYTES = 1_000_000
MAX_SOURCE_ARTIFACTS = 100
MAX_ADVISORIES = 1_000
MAX_LIMITATIONS = 50
MAX_PACKAGE_COUNT = 1_000_000

POPULATIONS = ("local-production", "local-full", "provider")
_STATUSES = {"passed", "failed", "unavailable", "not_applicable"}
_APPLICABILITY = {"affected", "not_affected", "unknown"}
_SOURCE_KINDS = {"local-scanner-export", "provider-export"}
_IDENTIFIER_RE = re.compile(r"[^\x00-\x1f\x7f]{1,200}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PRIVATE_IPV4_RE = re.compile(
    r"(?<!\d)(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?!\d)"
)
_INTERNAL_HOST_RE = re.compile(
    r"(?<![A-Za-z0-9.-])(?:[A-Za-z0-9-]+\.)+(?:home\.lab|internal|lan|local)(?![A-Za-z0-9.-])",
    re.IGNORECASE,
)
_HOME_PATH_RE = re.compile(
    r"(?:/home/[A-Za-z0-9._-]+|/Users/[A-Za-z0-9._-]+|[A-Za-z]:\\Users\\[A-Za-z0-9._-]+)"
)


class DependencyEvidenceError(ValueError):
    """A dependency-evidence artifact violated the bounded import contract."""


@dataclass(frozen=True)
class DependencySource:
    kind: str
    name: str
    version: str | None
    captured_at: str
    expires_at: str | None


@dataclass(frozen=True)
class DependencyAdvisory:
    id: str
    ecosystem: str
    package: str
    version: str
    applicability: str
    direct: bool | None
    development: bool | None
    transitive: bool | None

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (
            self.ecosystem.casefold(),
            self.package.casefold(),
            self.version,
            self.id.casefold(),
        )


@dataclass(frozen=True)
class DependencyEvidence:
    population: str
    status: str
    required: bool
    truncated: bool
    package_count: int
    source: DependencySource
    source_artifacts: tuple[str, ...]
    advisories: tuple[DependencyAdvisory, ...]
    limitations: tuple[str, ...]
    import_artifact: str | None = None
    import_sha256: str | None = None

    @property
    def source_id(self) -> str:
        identity = "\0".join(
            (
                self.population,
                self.source.kind,
                self.source.name,
                self.source.version or "",
                self.source.captured_at,
                self.import_sha256 or "",
            )
        )
        suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        return f"{self.population}:{self.source.kind}:{self.source.name}:{suffix}"

    def to_dict(self, *, now: datetime | None = None) -> dict[str, Any]:
        value = asdict(self)
        value["stale"] = evidence_is_stale(self, now=now)
        return value


def _object(value: Any, *, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DependencyEvidenceError(f"{label} must be an object")
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown:
        raise DependencyEvidenceError(f"{label} has {len(unknown)} unknown fields")
    if missing:
        raise DependencyEvidenceError(f"{label} is missing fields: {missing}")
    return value


def _safe_identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise DependencyEvidenceError(f"{label} must be a bounded printable string")
    if (
        _EMAIL_RE.search(value)
        or _PRIVATE_IPV4_RE.search(value)
        or _INTERNAL_HOST_RE.search(value)
        or _HOME_PATH_RE.search(value)
    ):
        raise DependencyEvidenceError(f"{label} contains privacy-sensitive content")
    return value


def _optional_identifier(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    return _safe_identifier(value, label=label)


def _timestamp(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or len(value) > 64 or "T" not in value:
        raise DependencyEvidenceError(f"{label} must be a bounded RFC 3339 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DependencyEvidenceError(f"{label} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise DependencyEvidenceError(f"{label} must include a timezone")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_timestamp(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    return _timestamp(value, label=label)


def _safe_artifact(root: Path, value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not 0 < len(value) <= 500
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or "\\" in value
    ):
        raise DependencyEvidenceError(f"{label} must be a repository-relative path")
    pure = PurePosixPath(value.removeprefix("./"))
    if pure.is_absolute() or ".." in pure.parts:
        raise DependencyEvidenceError(f"{label} must remain within the repository")
    candidate = (root / Path(*pure.parts)).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DependencyEvidenceError(f"{label} escapes the repository") from exc
    safe = pure.as_posix()
    if (
        _EMAIL_RE.search(safe)
        or _PRIVATE_IPV4_RE.search(safe)
        or _INTERNAL_HOST_RE.search(safe)
        or _HOME_PATH_RE.search(safe)
    ):
        raise DependencyEvidenceError(f"{label} contains privacy-sensitive content")
    return safe


def _contained_import(root: Path, value: str | Path) -> tuple[Path, str]:
    path = Path(value)
    candidate = path if path.is_absolute() else root / path
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise DependencyEvidenceError(
            "dependency evidence path is missing or escapes the project"
        ) from exc
    if not resolved.is_file():
        raise DependencyEvidenceError("dependency evidence path is not a regular file")
    return resolved, relative.as_posix()


def _read_bounded(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            payload = handle.read(MAX_IMPORT_BYTES + 1)
    except OSError as exc:
        raise DependencyEvidenceError("dependency evidence artifact could not be read") from exc
    if len(payload) > MAX_IMPORT_BYTES:
        raise DependencyEvidenceError(
            f"dependency evidence artifact exceeds the {MAX_IMPORT_BYTES} byte bound"
        )
    return payload


def load_dependency_evidence(root: Path, value: str | Path) -> DependencyEvidence:
    """Load one strict, repository-contained dependency-evidence artifact."""
    root = root.resolve()
    path, import_artifact = _contained_import(root, value)
    raw = _read_bounded(path)
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DependencyEvidenceError("dependency evidence artifact is not valid JSON") from exc
    record = _object(
        payload,
        fields={
            "schema_version",
            "population",
            "status",
            "required",
            "truncated",
            "package_count",
            "source",
            "source_artifacts",
            "advisories",
            "limitations",
        },
        label="dependency evidence",
    )
    if (
        not isinstance(record["schema_version"], int)
        or isinstance(record["schema_version"], bool)
        or record["schema_version"] != 1
    ):
        raise DependencyEvidenceError("dependency evidence schema_version must be 1")
    population = record["population"]
    if population not in POPULATIONS:
        raise DependencyEvidenceError(
            f"dependency evidence population must be one of {POPULATIONS}"
        )
    status = record["status"]
    if status not in _STATUSES:
        raise DependencyEvidenceError("dependency evidence status is invalid")
    if not isinstance(record["required"], bool) or not isinstance(record["truncated"], bool):
        raise DependencyEvidenceError("required and truncated must be booleans")
    package_count = record["package_count"]
    if (
        not isinstance(package_count, int)
        or isinstance(package_count, bool)
        or not 0 <= package_count <= MAX_PACKAGE_COUNT
    ):
        raise DependencyEvidenceError("package_count is outside the supported bound")

    source_record = _object(
        record["source"],
        fields={"kind", "name", "version", "captured_at", "expires_at"},
        label="dependency evidence source",
    )
    kind = source_record["kind"]
    if kind not in _SOURCE_KINDS:
        raise DependencyEvidenceError(
            f"dependency evidence source kind must be one of {_SOURCE_KINDS}"
        )
    if population == "provider" and kind != "provider-export":
        raise DependencyEvidenceError("provider population requires provider-export source kind")
    if population != "provider" and kind != "local-scanner-export":
        raise DependencyEvidenceError("local populations require local-scanner-export source kind")
    source = DependencySource(
        kind,
        _safe_identifier(source_record["name"], label="source.name"),
        _optional_identifier(source_record["version"], label="source.version"),
        _timestamp(source_record["captured_at"], label="source.captured_at"),
        _optional_timestamp(source_record["expires_at"], label="source.expires_at"),
    )

    artifacts = record["source_artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) > MAX_SOURCE_ARTIFACTS:
        raise DependencyEvidenceError("source_artifacts must be a bounded list")
    source_artifacts = tuple(
        _safe_artifact(root, item, label="source_artifacts item") for item in artifacts
    )
    if len(set(source_artifacts)) != len(source_artifacts):
        raise DependencyEvidenceError("source_artifacts must be unique")

    advisory_values = record["advisories"]
    if not isinstance(advisory_values, list) or len(advisory_values) > MAX_ADVISORIES:
        raise DependencyEvidenceError("advisories must be a bounded list")
    advisories: list[DependencyAdvisory] = []
    for index, value_item in enumerate(advisory_values):
        item = _object(
            value_item,
            fields={
                "id",
                "ecosystem",
                "package",
                "version",
                "applicability",
                "direct",
                "development",
                "transitive",
            },
            label=f"advisories[{index}]",
        )
        applicability = item["applicability"]
        if applicability not in _APPLICABILITY:
            raise DependencyEvidenceError(f"advisories[{index}].applicability is invalid")
        flags = (item["direct"], item["development"], item["transitive"])
        if any(flag is not None and not isinstance(flag, bool) for flag in flags):
            raise DependencyEvidenceError(f"advisories[{index}] dependency flags are invalid")
        advisories.append(
            DependencyAdvisory(
                _safe_identifier(item["id"], label=f"advisories[{index}].id"),
                _safe_identifier(item["ecosystem"], label=f"advisories[{index}].ecosystem"),
                _safe_identifier(item["package"], label=f"advisories[{index}].package"),
                _safe_identifier(item["version"], label=f"advisories[{index}].version"),
                applicability,
                item["direct"],
                item["development"],
                item["transitive"],
            )
        )
    if len({item.identity for item in advisories}) != len(advisories):
        raise DependencyEvidenceError("one evidence source must not duplicate advisory identities")
    if status == "passed" and any(
        item.applicability in {"affected", "unknown"} for item in advisories
    ):
        raise DependencyEvidenceError("passed evidence cannot contain unresolved advisories")

    limitation_values = record["limitations"]
    if not isinstance(limitation_values, list) or len(limitation_values) > MAX_LIMITATIONS:
        raise DependencyEvidenceError("limitations must be a bounded list")
    limitations = tuple(
        _safe_identifier(item, label="limitations item") for item in limitation_values
    )

    return DependencyEvidence(
        population=population,
        status=status,
        required=record["required"],
        truncated=record["truncated"],
        package_count=package_count,
        source=source,
        source_artifacts=source_artifacts,
        advisories=tuple(advisories),
        limitations=limitations,
        import_artifact=import_artifact,
        import_sha256=hashlib.sha256(raw).hexdigest(),
    )


def evidence_is_stale(evidence: DependencyEvidence, *, now: datetime | None = None) -> bool:
    """Return whether imported evidence lacks current, usable freshness evidence."""
    if evidence.source.kind == "live-local-scanner":
        return False
    if evidence.source.expires_at is None:
        return True
    current = now or datetime.now(UTC)
    expires = datetime.fromisoformat(evidence.source.expires_at)
    captured = datetime.fromisoformat(evidence.source.captured_at)
    return expires < current or captured > current


def _risk(
    code: str,
    message: str,
    *,
    blocking: bool,
    populations: tuple[str, ...],
    sources: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "blocking": blocking,
        "populations": list(populations),
        "sources": list(sources),
    }


def reconcile_dependency_evidence(
    records: tuple[DependencyEvidence, ...],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reconcile evidence without broadening passes or erasing unmatched alerts."""
    current = now or datetime.now(UTC)
    risks: list[dict[str, Any]] = []
    populations: list[dict[str, Any]] = []
    grouped: dict[
        tuple[str, str, str, str], list[tuple[DependencyEvidence, DependencyAdvisory]]
    ] = {}
    for record in records:
        for advisory in record.advisories:
            grouped.setdefault(advisory.identity, []).append((record, advisory))

    for population in POPULATIONS:
        selected = tuple(item for item in records if item.population == population)
        if not selected:
            populations.append(
                {
                    "name": population,
                    "state": "absent",
                    "required": False,
                    "statuses": [],
                    "sources": [],
                    "reported_package_counts": [],
                    "unique_advisories": 0,
                    "stale": False,
                    "truncated": False,
                    "limitations": [],
                }
            )
            continue
        stale = tuple(item for item in selected if evidence_is_stale(item, now=current))
        truncated = tuple(item for item in selected if item.truncated)
        unavailable = tuple(item for item in selected if item.status == "unavailable")
        required_incomplete = tuple(
            item
            for item in selected
            if item.required
            and (
                item.status == "unavailable"
                or item.truncated
                or evidence_is_stale(item, now=current)
            )
        )
        if stale:
            risks.append(
                _risk(
                    "dependency.evidence-stale",
                    f"{population} evidence is stale or has no bounded freshness claim",
                    blocking=any(item.required for item in stale),
                    populations=(population,),
                    sources=tuple(item.source_id for item in stale),
                )
            )
        if truncated:
            risks.append(
                _risk(
                    "dependency.evidence-truncated",
                    f"{population} evidence exceeded its producer or import bound",
                    blocking=any(item.required for item in truncated),
                    populations=(population,),
                    sources=tuple(item.source_id for item in truncated),
                )
            )
        if unavailable:
            risks.append(
                _risk(
                    "dependency.scope-unavailable",
                    f"{population} evidence is unavailable",
                    blocking=any(item.required for item in unavailable),
                    populations=(population,),
                    sources=tuple(item.source_id for item in unavailable),
                )
            )
        if required_incomplete:
            risks.append(
                _risk(
                    "dependency.required-scope-incomplete",
                    f"required {population} evidence cannot support publication",
                    blocking=True,
                    populations=(population,),
                    sources=tuple(item.source_id for item in required_incomplete),
                )
            )
        population_advisories = {
            advisory.identity for item in selected for advisory in item.advisories
        }
        populations.append(
            {
                "name": population,
                "state": "present",
                "required": any(item.required for item in selected),
                "statuses": sorted({item.status for item in selected}),
                "sources": [item.source_id for item in selected],
                "reported_package_counts": [item.package_count for item in selected],
                "unique_advisories": len(population_advisories),
                "stale": bool(stale),
                "truncated": bool(truncated),
                "limitations": sorted(
                    {limitation for item in selected for limitation in item.limitations}
                ),
            }
        )

    local_statuses = {
        population: sorted({item.status for item in records if item.population == population})
        for population in ("local-production", "local-full")
    }
    if (
        all(local_statuses.values())
        and local_statuses["local-production"] != local_statuses["local-full"]
    ):
        risks.append(
            _risk(
                "dependency.population-disagreement",
                "local production and local full dependency populations disagree",
                blocking=any("failed" in statuses for statuses in local_statuses.values()),
                populations=("local-production", "local-full"),
                sources=tuple(
                    sorted(
                        {
                            item.source_id
                            for item in records
                            if item.population in {"local-production", "local-full"}
                        }
                    )
                ),
            )
        )

    local_full_ids = {
        advisory.identity
        for item in records
        if item.population == "local-full"
        for advisory in item.advisories
    }
    provider_ids = {
        advisory.identity
        for item in records
        if item.population == "provider"
        for advisory in item.advisories
    }
    if (
        any(item.population == "local-full" for item in records)
        and any(item.population == "provider" for item in records)
        and local_full_ids != provider_ids
    ):
        risks.append(
            _risk(
                "dependency.local-provider-disagreement",
                "local full and provider evidence report different advisory identities",
                blocking=bool(local_full_ids or provider_ids),
                populations=("local-full", "provider"),
                sources=tuple(
                    sorted(
                        {
                            item.source_id
                            for item in records
                            if item.population in {"local-full", "provider"}
                        }
                    )
                ),
            )
        )

    advisories: list[dict[str, Any]] = []
    for identity in sorted(grouped):
        entries = grouped[identity]
        applicability = sorted({item.applicability for _, item in entries})
        if len(applicability) > 1:
            risks.append(
                _risk(
                    "dependency.applicability-disagreement",
                    "sources disagree about one advisory's applicability",
                    blocking=True,
                    populations=tuple(sorted({record.population for record, _ in entries})),
                    sources=tuple(record.source_id for record, _ in entries),
                )
            )
        sample = entries[0][1]
        advisories.append(
            {
                "id": sample.id,
                "ecosystem": sample.ecosystem,
                "package": sample.package,
                "version": sample.version,
                "applicability": applicability,
                "populations": sorted({record.population for record, _ in entries}),
                "sources": sorted({record.source_id for record, _ in entries}),
                "direct": sorted({item.direct for _, item in entries if item.direct is not None}),
                "development": sorted(
                    {item.development for _, item in entries if item.development is not None}
                ),
                "transitive": sorted(
                    {item.transitive for _, item in entries if item.transitive is not None}
                ),
                "unresolved": any(
                    item.applicability in {"affected", "unknown"} for _, item in entries
                ),
            }
        )

    unresolved = [item for item in advisories if item["unresolved"]]
    if unresolved:
        risks.append(
            _risk(
                "dependency.unresolved-advisories",
                f"{len(unresolved)} reconciled advisory identities remain unresolved",
                blocking=True,
                populations=tuple(
                    sorted(
                        {population for item in unresolved for population in item["populations"]}
                    )
                ),
                sources=tuple(
                    sorted({source for item in unresolved for source in item["sources"]})
                ),
            )
        )

    failed = any(item.status == "failed" for item in records) or any(
        item["unresolved"] for item in advisories
    )
    unavailable = any(item["blocking"] and item["code"].endswith("incomplete") for item in risks)
    blocking_risk = any(item["blocking"] for item in risks)
    status = "unavailable" if unavailable else ("failed" if failed or blocking_risk else "passed")
    return {
        "schema_version": 1,
        "status": status,
        "populations": populations,
        "records": [item.to_dict(now=current) for item in records],
        "advisories": advisories,
        "release_risks": risks,
        "summary": {
            "records": len(records),
            "unique_advisories": len(advisories),
            "release_risks": len(risks),
            "blocking_release_risks": sum(item["blocking"] for item in risks),
        },
        "limitations": [
            "A pass applies only to the named dependency population, source artifacts, and capture time.",
            "Unmatched advisories are preserved; absence from one source is not a dismissal.",
            "Scanner/provider evidence does not establish reachability, exploitability, or ecosystem completeness.",
        ],
    }
