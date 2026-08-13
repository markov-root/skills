"""Resolve, hash, and atomically persist one immutable execution contract.

The module is deliberately below CLI, engine, and provider adapters.  Those application layers
load and validate authored inputs, then pass JSON-compatible resolved values here exactly once.
After that boundary, cost, plan, execution, provenance, and resume use the same
``ResolvedRunPlan``.  No provider SDK or mutable project loader is imported here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_ID = "debate.resolved-run-plan"
SCHEMA_VERSION = "1.0.0"
PLAN_FILENAME = "resolved-run-plan.json"

_IDENTITY_QUALITIES = frozenset({"resolved", "legacy_unverified"})
_OBSERVATION_STATES = frozenset({"known", "unknown", "failed"})
_SECRET_KEY = re.compile(
    r"(?:^|_)(?:api_key|secret|password|credential|access_token|private_key)(?:$|_)", re.I
)
_CAPABILITY_KEYS = frozenset(
    {
        "information",
        "tools",
        "filesystem",
        "network",
        "effects",
        "max_cost_usd",
        "max_tokens",
    }
)


class ResolutionError(ValueError):
    """A resolved plan is incomplete, mutable, unsafe, or has lost its identity."""


class FrozenDict(Mapping[str, Any]):
    """A recursively immutable, deterministically ordered JSON object."""

    __slots__ = ("_items",)

    def __init__(self, value: Mapping[str, Any]):
        if any(not isinstance(key, str) for key in value):
            raise ResolutionError("resolved JSON object keys must be strings")
        self._items = tuple(sorted((key, _freeze(item)) for key, item in value.items()))

    def __getitem__(self, key: str) -> Any:
        for candidate, value in self._items:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"FrozenDict({dict(self._items)!r})"

    def __hash__(self) -> int:
        return hash(self._items)


def _freeze(value: Any) -> Any:
    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, Mapping):
        return FrozenDict(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not (-float("inf") < value < float("inf")):
            raise ResolutionError("resolved values must not contain NaN or infinity")
        return value
    raise ResolutionError(f"resolved values must be JSON-compatible, got {type(value).__name__}")


def _thaw(value: Any) -> Any:
    if isinstance(value, FrozenDict):
        return {key: _thaw(item) for key, item in value._items}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """RFC-8259-compatible canonical bytes for hashing and persistence.

    JSON object ordering and incidental whitespace never affect either plan hash.
    """

    return json.dumps(
        _thaw(_freeze(value)),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def resolved_artifact(name: str, content: Any, *, version: str = "1.0.0") -> dict[str, Any]:
    """Return one content-addressed prompt, schema, or deterministic operation artifact."""

    frozen = _thaw(_freeze(content))
    return {"name": name, "version": version, "sha256": _digest(frozen), "content": frozen}


def _pointer_escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def _leaf_paths(value: Any, prefix: str = "") -> Iterator[str]:
    if isinstance(value, Mapping):
        for key in sorted(value):
            child = f"{prefix}/{_pointer_escape(str(key))}"
            yield from _leaf_paths(value[key], child)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _leaf_paths(item, f"{prefix}/{index}")
        return
    yield prefix or "/"


def _provenance_for(
    execution: Mapping[str, Any], rules: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    if "/" not in rules:
        raise ResolutionError("provenance rules need a '/' resolver-derived fallback")
    normalized = {
        str(path).rstrip("/") or "/": _thaw(_freeze(record))
        for path, record in rules.items()
    }
    entries: list[dict[str, Any]] = []
    for path in _leaf_paths(execution):
        matches = [
            prefix
            for prefix in normalized
            if prefix == "/" or path == prefix or path.startswith(prefix + "/")
        ]
        source = normalized[max(matches, key=len)]
        entries.append({"path": path, **source})
    return entries


def _validate_observation(value: Mapping[str, Any], *, path: str) -> None:
    allowed = {"state", "value", "detail"}
    unknown = set(value) - allowed
    if unknown:
        raise ResolutionError(f"{path}: unknown observation field(s): {sorted(unknown)}")
    state = value.get("state")
    if state not in _OBSERVATION_STATES:
        raise ResolutionError(f"{path}.state must be one of {sorted(_OBSERVATION_STATES)}")
    if state == "known" and value.get("value") is None:
        raise ResolutionError(f"{path}: a known observation needs a value")
    if state != "known" and value.get("value") is not None:
        raise ResolutionError(f"{path}: {state} must not invent a value")
    if state in {"unknown", "failed"} and not value.get("detail"):
        raise ResolutionError(f"{path}: {state} needs a diagnostic detail")


def _validate_capability_envelope(value: Mapping[str, Any], *, path: str) -> None:
    unknown = set(value) - _CAPABILITY_KEYS
    missing = _CAPABILITY_KEYS - set(value)
    if unknown or missing:
        raise ResolutionError(
            f"{path}: capability keys missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    for key in ("information", "tools", "filesystem", "network", "effects"):
        items = value[key]
        if not isinstance(items, (list, tuple)) or any(not isinstance(item, str) for item in items):
            raise ResolutionError(f"{path}.{key} must be a list of strings")
        if len(items) != len(set(items)):
            raise ResolutionError(f"{path}.{key} contains duplicate capabilities")
    for key in ("max_cost_usd", "max_tokens"):
        limit = value[key]
        if limit is not None and (not isinstance(limit, (int, float)) or limit < 0):
            raise ResolutionError(f"{path}.{key} must be a non-negative number or null")


def _validate_child_capabilities(
    parent: Mapping[str, Any], child: Mapping[str, Any], *, path: str
) -> None:
    _validate_capability_envelope(child, path=path)
    for key in ("information", "tools", "filesystem", "network", "effects"):
        extra = set(child[key]) - set(parent[key])
        if extra:
            raise ResolutionError(f"{path}.{key} exceeds parent authority: {sorted(extra)}")
    for key in ("max_cost_usd", "max_tokens"):
        parent_limit, child_limit = parent[key], child[key]
        if parent_limit is not None and (child_limit is None or child_limit > parent_limit):
            raise ResolutionError(f"{path}.{key} exceeds parent limit {parent_limit}")


def _validate_compatibility(value: Mapping[str, Any], *, path: str) -> None:
    expected = {
        "adapter_version",
        "protocol_version",
        "harness_version",
        "entitlement_class",
        "selected_model",
        "selected_provider",
        "resolved_capabilities",
    }
    if set(value) != expected:
        raise ResolutionError(
            f"{path}: compatibility tuple missing={sorted(expected - set(value))} "
            f"unknown={sorted(set(value) - expected)}"
        )
    for key in expected:
        _validate_observation(value[key], path=f"{path}.{key}")


def _validate_no_secret_material(value: Any, *, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            if _SECRET_KEY.search(str(key)) and item not in (None, False, "", "absent"):
                raise ResolutionError(
                    f"{child}: secret material is forbidden; use secrets[] "
                    "presence/reference metadata"
                )
            _validate_no_secret_material(item, path=child)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_no_secret_material(item, path=f"{path}[{index}]")


def _protocol_projection(document: Mapping[str, Any]) -> dict[str, Any]:
    policies = document["policies"]
    return {
        "schema_version": document["schema_version"],
        "task": document["task"],
        "profile": document["profile"],
        "phases": document["phases"],
        "prompts": document["prompts"],
        "schemas": document["schemas"],
        "failure_policy": policies["failure"],
        "evidence_policy": policies["evidence"],
        "aggregator": document["aggregator"],
        "parent_capabilities": document["parent_capabilities"],
    }


def _execution_projection(document: Mapping[str, Any]) -> dict[str, Any]:
    excluded = {
        "protocol_hash",
        "execution_hash",
        "run_id",
        "parent_run_id",
    }
    return {key: value for key, value in document.items() if key not in excluded}


@dataclass(frozen=True)
class ResolvedRunPlan:
    """One deeply immutable, fully expanded run contract."""

    schema_id: str
    schema_version: str
    run_id: str
    parent_run_id: str | None
    identity_quality: str
    task: FrozenDict
    profile: FrozenDict
    phases: tuple[FrozenDict, ...]
    prompts: tuple[FrozenDict, ...]
    schemas: tuple[FrozenDict, ...]
    role_bindings: tuple[FrozenDict, ...]
    policies: FrozenDict
    budgets: FrozenDict
    seeds: FrozenDict
    aggregator: FrozenDict
    parent_capabilities: FrozenDict
    source_hashes: tuple[FrozenDict, ...]
    operation_versions: tuple[FrozenDict, ...]
    secrets: tuple[FrozenDict, ...]
    pricing: tuple[FrozenDict, ...]
    provenance: tuple[FrozenDict, ...]
    protocol_hash: str
    execution_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "identity_quality": self.identity_quality,
            "task": _thaw(self.task),
            "profile": _thaw(self.profile),
            "phases": _thaw(self.phases),
            "prompts": _thaw(self.prompts),
            "schemas": _thaw(self.schemas),
            "role_bindings": _thaw(self.role_bindings),
            "policies": _thaw(self.policies),
            "budgets": _thaw(self.budgets),
            "seeds": _thaw(self.seeds),
            "aggregator": _thaw(self.aggregator),
            "parent_capabilities": _thaw(self.parent_capabilities),
            "source_hashes": _thaw(self.source_hashes),
            "operation_versions": _thaw(self.operation_versions),
            "secrets": _thaw(self.secrets),
            "pricing": _thaw(self.pricing),
            "provenance": _thaw(self.provenance),
            "protocol_hash": self.protocol_hash,
            "execution_hash": self.execution_hash,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> ResolvedRunPlan:
        return _validated_plan(document)


_PLAN_KEYS = frozenset(ResolvedRunPlan.__dataclass_fields__)


def _validated_plan(raw: Mapping[str, Any]) -> ResolvedRunPlan:
    document = _thaw(_freeze(raw))
    missing, unknown = _PLAN_KEYS - set(document), set(document) - _PLAN_KEYS
    if missing or unknown:
        raise ResolutionError(
            f"resolved plan fields missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    if document["schema_id"] != SCHEMA_ID or document["schema_version"] != SCHEMA_VERSION:
        raise ResolutionError(
            f"unsupported resolved plan contract {document['schema_id']!r} "
            f"{document['schema_version']!r}"
        )
    if not isinstance(document["run_id"], str) or not document["run_id"].strip():
        raise ResolutionError("run_id must be a non-empty string")
    if document["identity_quality"] not in _IDENTITY_QUALITIES:
        raise ResolutionError(f"identity_quality must be one of {sorted(_IDENTITY_QUALITIES)}")
    if set(document["policies"]) != {"call", "failure", "evidence", "cache"}:
        raise ResolutionError("policies must contain exactly call, failure, evidence, and cache")

    parent = document["parent_capabilities"]
    _validate_capability_envelope(parent, path="parent_capabilities")
    role_ids: set[str] = set()
    for index, role in enumerate(document["role_bindings"]):
        expected = {"role_id", "role_pool", "voice", "compatibility", "effective_capabilities"}
        if set(role) != expected:
            raise ResolutionError(f"role_bindings[{index}] must contain exactly {sorted(expected)}")
        if role["role_id"] in role_ids:
            raise ResolutionError(f"duplicate resolved role id {role['role_id']!r}")
        role_ids.add(role["role_id"])
        _validate_compatibility(role["compatibility"], path=f"role_bindings[{index}].compatibility")
        _validate_child_capabilities(
            parent,
            role["effective_capabilities"],
            path=f"role_bindings[{index}].effective_capabilities",
        )

    for index, secret in enumerate(document["secrets"]):
        expected = {"name", "present", "reference", "source"}
        if set(secret) != expected or not isinstance(secret.get("present"), bool):
            raise ResolutionError(f"secrets[{index}] must be presence/reference metadata only")
    secret_free = {key: value for key, value in document.items() if key != "secrets"}
    _validate_no_secret_material(secret_free)

    expected_protocol = _digest(_protocol_projection(document))
    expected_execution = _digest(_execution_projection(document))
    if document["protocol_hash"] != expected_protocol:
        raise ResolutionError("protocol_hash does not match the canonical protocol projection")
    if document["execution_hash"] != expected_execution:
        raise ResolutionError("execution_hash does not match the canonical execution projection")

    kwargs = {key: _freeze(value) for key, value in document.items()}
    return ResolvedRunPlan(**kwargs)


def resolve_run_plan(
    *,
    run_id: str,
    task: Mapping[str, Any],
    profile: Mapping[str, Any],
    phases: Sequence[Mapping[str, Any]],
    prompts: Sequence[Mapping[str, Any]],
    schemas: Sequence[Mapping[str, Any]],
    role_bindings: Sequence[Mapping[str, Any]],
    policies: Mapping[str, Any],
    budgets: Mapping[str, Any],
    seeds: Mapping[str, Any],
    aggregator: Mapping[str, Any],
    parent_capabilities: Mapping[str, Any],
    source_hashes: Sequence[Mapping[str, Any]],
    operation_versions: Sequence[Mapping[str, Any]],
    secrets: Sequence[Mapping[str, Any]],
    pricing: Sequence[Mapping[str, Any]],
    provenance_rules: Mapping[str, Mapping[str, Any]],
    parent_run_id: str | None = None,
    identity_quality: str = "resolved",
) -> ResolvedRunPlan:
    """Resolve all inherited/defaulted inputs into one canonical immutable value.

    ``provenance_rules`` maps JSON-pointer prefixes to source records.  The longest matching prefix
    owns each resolved leaf, and a mandatory ``/`` rule covers resolver-derived defaults.  This
    produces a complete field-level provenance map without copying secret values.
    """

    base: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "parent_run_id": parent_run_id,
        "identity_quality": identity_quality,
        "task": task,
        "profile": profile,
        "phases": list(phases),
        "prompts": list(prompts),
        "schemas": list(schemas),
        "role_bindings": list(role_bindings),
        "policies": policies,
        "budgets": budgets,
        "seeds": seeds,
        "aggregator": aggregator,
        "parent_capabilities": parent_capabilities,
        "source_hashes": list(source_hashes),
        "operation_versions": list(operation_versions),
        "secrets": list(secrets),
        "pricing": list(pricing),
    }
    execution_without_provenance = _execution_projection(base)
    base["provenance"] = _provenance_for(execution_without_provenance, provenance_rules)
    base["protocol_hash"] = _digest(_protocol_projection(base))
    base["execution_hash"] = _digest(_execution_projection(base))
    return _validated_plan(base)


def load_resolved_run_plan(path: Path | str) -> ResolvedRunPlan:
    candidate = Path(path)
    if candidate.is_dir() or candidate.suffix == "":
        candidate = candidate / PLAN_FILENAME
    try:
        document = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError(f"cannot read resolved run plan {candidate}: {exc}") from exc
    if not isinstance(document, dict):
        raise ResolutionError(f"resolved run plan {candidate} must be a JSON object")
    return ResolvedRunPlan.from_dict(document)


def write_resolved_run_plan(plan: ResolvedRunPlan, run_dir: Path | str) -> Path:
    """Atomically create the immutable plan, refusing a changed plan for an existing run."""

    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / PLAN_FILENAME
    if target.exists():
        existing = load_resolved_run_plan(target)
        if existing.run_id != plan.run_id or existing.execution_hash != plan.execution_hash:
            raise ResolutionError(
                f"run {directory} already has a different immutable plan; create an explicit fork"
            )
        return target

    fd, temporary_name = tempfile.mkstemp(prefix=f".{PLAN_FILENAME}.", dir=directory)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        payload = (json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            # Same-directory hard-link creation is atomic and refuses to replace a concurrently
            # published plan.  A plain os.replace() would let the last racing writer win.
            os.link(temporary, target)
        except FileExistsError:
            existing = load_resolved_run_plan(target)
            if existing.run_id != plan.run_id or existing.execution_hash != plan.execution_hash:
                raise ResolutionError(
                    f"run {directory} concurrently received a different immutable plan; "
                    "create an explicit fork"
                ) from None
        finally:
            temporary.unlink(missing_ok=True)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target
