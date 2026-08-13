"""Strict, versioned contracts for every user-authored Debate YAML input.

The models in this module are the source of truth for generated JSON Schemas.  Loaders accept the
unversioned alpha files that shipped before ADR-0024, migrate them in memory, and then validate the
same strict current model.  New writers always emit ``schema_id`` + ``schema_version``.

This boundary is intentionally independent of execution.  Parsing these models performs no
filesystem writes, network requests, subprocess creation, or model calls.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal
from urllib.parse import urlparse

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = "1.0.0"

_IDENTIFIER_PATTERN = r"^[a-z0-9](?:[a-z0-9._-]{0,62})$"
_EXTENSION_PATTERN = re.compile(r"^(?:x-[a-z0-9](?:[a-z0-9.-]{0,62})|[a-z0-9]+(?:\.[a-z0-9-]+)+)$")
_HASH_PATTERN = r"^[a-fA-F0-9]{64}$"

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=63,
        pattern=_IDENTIFIER_PATTERN,
    ),
]


def _safe_path_text(value: str) -> str:
    if not value.strip():
        raise ValueError("path cannot be blank")
    if "\x00" in value:
        raise ValueError("path cannot contain NUL")
    if "\\" in value:
        raise ValueError("paths must use portable forward-slash separators")
    return value


OwnedPath = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=4096,
        pattern=r"^[^\\\x00]*\S[^\\\x00]*$",
    ),
    AfterValidator(_safe_path_text),
]
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]
Backend = Literal["openrouter", "claude_code", "codex_cli"]
MaterialsMode = Literal["context", "disk", "search"]
Protocol = Literal["delphi", "idea"]
AggregatorId = Literal["arbitrator_select", "statistical", "vote"]


class InputContractError(ValueError):
    """Stable input-boundary error used by all YAML compatibility loaders."""

    def __init__(self, code: str, message: str, *, source: str | Path | None = None):
        self.code = code
        self.source = str(source) if source is not None else None
        prefix = f"{self.source}: " if self.source else ""
        super().__init__(f"{prefix}{code}: {message}")


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        validate_default=True,
    )


class _ExtensibleModel(_StrictModel):
    extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("extensions")
    @classmethod
    def _namespaced_extensions(cls, value: dict[str, Any]) -> dict[str, Any]:
        bad = sorted(k for k in value if not _EXTENSION_PATTERN.fullmatch(k))
        if bad:
            raise ValueError(
                f"extension keys must be namespaced (reverse-DNS or x-*); invalid: {bad}"
            )
        # Make extension values data-only.  It also catches values that generated JSON Schema
        # could not describe or a YAML object constructor somehow smuggled through.
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("extension values must be finite JSON data") from exc
        return value


class _VersionedDocument(_ExtensibleModel):
    CONTRACT_ID: ClassVar[str]
    CONTRACT_VERSION: ClassVar[str] = SCHEMA_VERSION

    schema_id: str
    schema_version: str

    @model_validator(mode="after")
    def _current_contract(self):
        if self.schema_id != self.CONTRACT_ID:
            raise ValueError(f"schema_id must be {self.CONTRACT_ID!r}")
        if self.schema_version != self.CONTRACT_VERSION:
            raise ValueError(f"schema_version must be {self.CONTRACT_VERSION!r}")
        return self


class CallPolicyInput(_StrictModel):
    """Per-voice call knobs that the current backends actually enforce."""

    CONTRACT_ID: ClassVar[str] = "debate.call-policy"
    CONTRACT_VERSION: ClassVar[str] = SCHEMA_VERSION

    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    timeout_s: float | None = Field(default=None, gt=0.0, le=86_400.0)
    reasoning_effort: ReasoningEffort | None = None


class AffordancePolicyInput(_StrictModel):
    """Declared tool access.

    Non-default values are rejected by ``VoiceInput`` until task 0059 supplies the runtime.  The
    model exists now so capability negotiation has one stable vocabulary and unsupported claims
    cannot masquerade as active behavior.
    """

    CONTRACT_ID: ClassVar[str] = "debate.affordance-policy"
    CONTRACT_VERSION: ClassVar[str] = SCHEMA_VERSION

    web_search: bool = False
    filesystem: Literal["none", "project_read"] = "none"


class VoiceInput(_ExtensibleModel):
    CONTRACT_ID: ClassVar[str] = "debate.voice"
    CONTRACT_VERSION: ClassVar[str] = SCHEMA_VERSION

    id: Identifier
    backend: Backend
    model: str | None = Field(default=None, min_length=1, max_length=512, pattern=r"\S")
    persona: str | None = Field(default=None, min_length=1, max_length=100_000, pattern=r"\S")
    call_policy: CallPolicyInput = Field(default_factory=CallPolicyInput)
    affordances: AffordancePolicyInput = Field(default_factory=AffordancePolicyInput)

    @field_validator("model", "persona")
    @classmethod
    def _nonblank_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("value cannot be blank")
        return value

    @model_validator(mode="after")
    def _backend_contract(self):
        policy = self.call_policy
        affordances = self.affordances
        if self.backend == "openrouter" and not self.model:
            raise ValueError("backend 'openrouter' requires a non-empty model slug")
        if self.backend == "openrouter":
            unsupported = [
                name
                for name, value in (
                    ("timeout_s", policy.timeout_s),
                    ("reasoning_effort", policy.reasoning_effort),
                )
                if value is not None
            ]
        elif self.backend == "claude_code":
            unsupported = [
                name
                for name, value in (
                    ("temperature", policy.temperature),
                    ("reasoning_effort", policy.reasoning_effort),
                )
                if value is not None
            ]
        else:  # codex_cli
            unsupported = ["temperature"] if policy.temperature is not None else []
        if unsupported:
            raise ValueError(
                f"backend {self.backend!r} does not enforce call-policy field(s) {unsupported}"
            )
        if affordances.web_search or affordances.filesystem != "none":
            raise ValueError(
                "per-voice affordances are reserved until the affordance runtime lands "
                "(task-0059); use project materials_mode for current evidence access"
            )
        return self

    def to_runtime(self) -> dict[str, Any]:
        """Translate the canonical nested policy into the existing backend-construction shape."""
        out: dict[str, Any] = {"id": self.id, "backend": self.backend}
        if self.model is not None:
            out["model"] = self.model
        if self.persona is not None:
            out["persona"] = self.persona
        if self.call_policy.temperature is not None:
            out["temperature"] = self.call_policy.temperature
        if self.call_policy.timeout_s is not None:
            out["timeout"] = self.call_policy.timeout_s
        if self.call_policy.reasoning_effort is not None:
            out["reasoning_effort"] = self.call_policy.reasoning_effort
        if self.extensions:
            out["extensions"] = copy.deepcopy(self.extensions)
        return out


class PassInput(_StrictModel):
    pass_name: Literal["floor", "adversarial", "escalation"] = Field(alias="pass")
    dynamic: bool | None = None


PlanStage = Literal["propose", "critique", "revise", "redteam", "respond"]


class RefereePolicyInput(_StrictModel):
    before_revise: list[Identifier] | None = None
    before_respond: list[Identifier] | None = None


class RoundsInput(_StrictModel):
    min_phases: int = Field(default=3, alias="min", ge=3, le=10_000)
    max_phases: int = Field(default=5, alias="max", ge=3, le=10_000)
    plan: list[PlanStage | PassInput] | None = Field(default=None, min_length=1, max_length=10_000)
    token_budget: int | None = Field(default=None, ge=1)
    referees: RefereePolicyInput | None = None

    @model_validator(mode="after")
    def _bounds_and_passes(self):
        if self.min_phases > self.max_phases:
            raise ValueError("rounds.min cannot exceed rounds.max")
        for index, item in enumerate(self.plan or []):
            if isinstance(item, PassInput):
                if item.pass_name == "escalation" and item.dynamic is not True:
                    raise ValueError(f"rounds.plan[{index}] escalation must declare dynamic: true")
                if item.pass_name != "escalation" and item.dynamic is not None:
                    raise ValueError(
                        f"rounds.plan[{index}] dynamic is only valid for an escalation pass"
                    )
        return self

    def to_runtime(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class ProjectInput(_VersionedDocument):
    CONTRACT_ID: ClassVar[str] = "debate.project"

    schema_id: Literal["debate.project"]
    schema_version: Literal["1.0.0"]
    id: Identifier
    protocol: Protocol = "delphi"
    question: str = Field(min_length=1, max_length=500_000, pattern=r"\S")
    criteria: str = Field(default="", max_length=500_000)
    item: OwnedPath = "items/v0.1.0.md"
    materials: OwnedPath = "materials"
    materials_mode: MaterialsMode = "context"
    context: str = Field(default="", max_length=2_000_000)
    rounds: RoundsInput | None = None
    aggregator: AggregatorId | None = None

    @field_validator("question")
    @classmethod
    def _question_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question cannot be blank")
        return value

    @field_validator("rounds", mode="before")
    @classmethod
    def _rounds_mapping(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, Mapping):
            raise ValueError("`rounds:` must be a mapping (min/max/plan/referees/token_budget)")
        return value

    @field_validator("aggregator", mode="before")
    @classmethod
    def _aggregator_string(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, str):
            raise ValueError(f"`aggregator` must be a string, got {value!r}")
        return value

    @model_validator(mode="after")
    def _task_aggregator_pair(self):
        allowed = {
            "delphi": {"arbitrator_select"},
            "idea": {"statistical"},
        }[self.protocol]
        if self.aggregator is not None and self.aggregator not in allowed:
            raise ValueError(
                f"aggregator {self.aggregator!r} is incompatible with protocol "
                f"{self.protocol!r}; allowed: {sorted(allowed)}"
            )
        return self

    def to_runtime(self) -> dict[str, Any]:
        out = self.model_dump(
            by_alias=True,
            exclude={"schema_id", "schema_version", "extensions"},
            exclude_none=True,
        )
        if self.rounds is not None:
            out["rounds"] = self.rounds.to_runtime()
        return out


class CastInput(_VersionedDocument):
    CONTRACT_ID: ClassVar[str] = "debate.cast"

    schema_id: Literal["debate.cast"]
    schema_version: Literal["1.0.0"]
    panel: Identifier | None = None
    protocol: Protocol | None = None
    proposers: list[VoiceInput] = Field(min_length=1, max_length=256)
    redteam: VoiceInput | None = None
    arbitrator: VoiceInput
    reviewers: list[VoiceInput] | None = Field(default=None, min_length=1, max_length=256)
    adversaries: list[VoiceInput] | None = Field(default=None, max_length=256)
    aggregators: list[VoiceInput] | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def _unique_voice_ids(self):
        voices = [
            *self.proposers,
            *([] if self.redteam is None else [self.redteam]),
            self.arbitrator,
            *(self.reviewers or []),
            *(self.adversaries or []),
            *(self.aggregators or []),
        ]
        counts: dict[str, int] = {}
        for voice in voices:
            counts[voice.id] = counts.get(voice.id, 0) + 1
        duplicates = sorted(identifier for identifier, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"voice ids must be unique across the authored cast: {duplicates}")
        return self

    def to_runtime(self) -> dict[str, Any]:
        return {
            "panel": self.panel,
            "debaters": [voice.to_runtime() for voice in self.proposers],
            "redteam": self.redteam.to_runtime() if self.redteam else None,
            "arbitrator": self.arbitrator.to_runtime(),
            "reviewers": (
                [voice.to_runtime() for voice in self.reviewers]
                if self.reviewers is not None
                else None
            ),
            "adversaries": (
                [voice.to_runtime() for voice in self.adversaries]
                if self.adversaries is not None
                else None
            ),
            "aggregators": (
                [voice.to_runtime() for voice in self.aggregators]
                if self.aggregators is not None
                else None
            ),
        }


class PanelInput(_ExtensibleModel):
    description: str = Field(default="", max_length=100_000)
    self_exclude: Literal["by_vendor"] | None = None
    proposers: list[VoiceInput] = Field(min_length=1, max_length=256)
    redteam: VoiceInput | None = None
    arbitrator: VoiceInput

    @model_validator(mode="after")
    def _unique_voice_ids(self):
        voices = [
            *self.proposers,
            *([] if self.redteam is None else [self.redteam]),
            self.arbitrator,
        ]
        identifiers = [voice.id for voice in voices]
        duplicates = sorted(
            {identifier for identifier in identifiers if identifiers.count(identifier) > 1}
        )
        if duplicates:
            raise ValueError(f"voice ids must be unique within a panel: {duplicates}")
        return self

    def to_runtime(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "description": self.description,
            "proposers": [voice.to_runtime() for voice in self.proposers],
            "arbitrator": self.arbitrator.to_runtime(),
        }
        if self.self_exclude is not None:
            out["self_exclude"] = self.self_exclude
        if self.redteam is not None:
            out["redteam"] = self.redteam.to_runtime()
        return out


class PanelRegistryInput(_VersionedDocument):
    CONTRACT_ID: ClassVar[str] = "debate.panel-registry"

    schema_id: Literal["debate.panel-registry"]
    schema_version: Literal["1.0.0"]
    panels: dict[Identifier, PanelInput] = Field(min_length=1, max_length=1_000)

    def to_runtime(self) -> dict[str, dict[str, Any]]:
        return {name: panel.to_runtime() for name, panel in self.panels.items()}


class RunSpecInput(_VersionedDocument):
    CONTRACT_ID: ClassVar[str] = "debate.run-spec"

    schema_id: Literal["debate.run-spec"]
    schema_version: Literal["1.0.0"]
    id: Identifier
    protocol: Protocol = "delphi"
    question: str = Field(min_length=1, max_length=500_000, pattern=r"\S")
    context: str = Field(default="", max_length=2_000_000)
    criteria: str = Field(default="", max_length=500_000)
    rounds: RoundsInput | None = None
    aggregator: AggregatorId | None = None

    @field_validator("question")
    @classmethod
    def _question_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question cannot be blank")
        return value

    @field_validator("rounds", mode="before")
    @classmethod
    def _rounds_mapping(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, Mapping):
            raise ValueError("`rounds:` must be a mapping (min/max/plan/referees/token_budget)")
        return value

    @field_validator("aggregator", mode="before")
    @classmethod
    def _aggregator_string(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, str):
            raise ValueError(f"`aggregator` must be a string, got {value!r}")
        return value

    @model_validator(mode="after")
    def _task_aggregator_pair(self):
        allowed = {"delphi": {"arbitrator_select"}, "idea": {"statistical"}}[self.protocol]
        if self.aggregator is not None and self.aggregator not in allowed:
            raise ValueError(
                f"aggregator {self.aggregator!r} is incompatible with protocol "
                f"{self.protocol!r}; allowed: {sorted(allowed)}"
            )
        return self

    def to_runtime(self) -> dict[str, Any]:
        out = self.model_dump(
            by_alias=True,
            exclude={"schema_id", "schema_version", "extensions"},
            exclude_none=True,
        )
        if self.rounds is not None:
            out["rounds"] = self.rounds.to_runtime()
        return out


class TaskFamilyInput(_VersionedDocument):
    """Portable task-family ask independent of project layout and cast selection."""

    CONTRACT_ID: ClassVar[str] = "debate.task-family-input"

    schema_id: Literal["debate.task-family-input"]
    schema_version: Literal["1.0.0"]
    protocol: Protocol
    question: str = Field(min_length=1, max_length=500_000, pattern=r"\S")
    context: str = Field(default="", max_length=2_000_000)
    criteria: str = Field(default="", max_length=500_000)
    aggregator: AggregatorId | None = None

    @model_validator(mode="after")
    def _task_aggregator_pair(self):
        allowed = {"delphi": {"arbitrator_select"}, "idea": {"statistical"}}[self.protocol]
        if self.aggregator is not None and self.aggregator not in allowed:
            raise ValueError(
                f"aggregator {self.aggregator!r} is incompatible with protocol "
                f"{self.protocol!r}; allowed: {sorted(allowed)}"
            )
        return self


class ProfileInput(_VersionedDocument):
    """Versioned profile preset contract; execution wiring remains task 0051."""

    CONTRACT_ID: ClassVar[str] = "debate.profile"

    schema_id: Literal["debate.profile"]
    schema_version: Literal["1.0.0"]
    name: Identifier
    protocol: Protocol
    n_proposers: int = Field(ge=1, le=256)
    has_adversary: bool
    aggregator: AggregatorId
    description: str = Field(default="", max_length=100_000)

    @model_validator(mode="after")
    def _task_aggregator_pair(self):
        expected = "arbitrator_select" if self.protocol == "delphi" else "statistical"
        if self.aggregator != expected:
            raise ValueError(f"profile protocol {self.protocol!r} requires aggregator {expected!r}")
        return self


class MaterialSourceInput(_ExtensibleModel):
    id: Identifier | None = None
    title: str | None = Field(default=None, min_length=1, max_length=10_000)
    url: str | None = Field(default=None, min_length=1, max_length=100_000)
    path: OwnedPath | None = None
    raw: OwnedPath | None = None
    media_type: str | None = Field(default=None, min_length=1, max_length=256)
    sha256: str | None = Field(default=None, pattern=_HASH_PATTERN)
    content_sha256: str | None = Field(default=None, pattern=_HASH_PATTERN)
    retrieved: str | None = Field(default=None, min_length=1, max_length=128)
    fetched_at: str | None = Field(default=None, min_length=1, max_length=128)
    fetch_layer: str | None = Field(default=None, min_length=1, max_length=128)
    provenance: Literal["P1", "P2", "P3"] | None = None
    date: dict[str, Any] | None = None
    summary: str | None = Field(default=None, max_length=1_000_000)
    status: Literal["include", "exclude"] = "include"
    reason: str | None = Field(default=None, max_length=100_000)

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute http(s) URL")
        return value

    @model_validator(mode="after")
    def _source_identity(self):
        if not any((self.id, self.path, self.url)):
            raise ValueError("a material source needs at least one of id, path, or url")
        return self


class MaterialsManifestInput(_VersionedDocument):
    CONTRACT_ID: ClassVar[str] = "debate.materials-manifest"

    schema_id: Literal["debate.materials-manifest"]
    schema_version: Literal["1.0.0"]
    corpus_version: str | None = Field(default=None, min_length=1, max_length=512)
    provider: str | None = Field(default=None, min_length=1, max_length=512)
    sources: list[MaterialSourceInput] = Field(default_factory=list, max_length=100_000)

    @model_validator(mode="after")
    def _unique_source_ids_and_paths(self):
        for field_name in ("id", "path"):
            values = [
                getattr(source, field_name)
                for source in self.sources
                if getattr(source, field_name) is not None
            ]
            duplicates = sorted({value for value in values if values.count(value) > 1})
            if duplicates:
                raise ValueError(f"material source {field_name}s must be unique: {duplicates}")
        return self

    def to_runtime(self) -> dict[str, Any]:
        return self.model_dump(
            exclude={"schema_id", "schema_version", "extensions"},
            exclude_none=True,
        )


def validate_identifier(value: str, *, kind: str = "identifier") -> str:
    """Validate one identifier without constructing a larger contract model."""
    if not isinstance(value, str) or not re.fullmatch(_IDENTIFIER_PATTERN, value):
        raise InputContractError(
            "invalid_identifier",
            f"{kind} must match {_IDENTIFIER_PATTERN!r}, be at most 63 characters; got {value!r}",
        )
    return value


def resolve_owned_path(
    root: Path | str,
    value: Path | str,
    *,
    kind: str = "path",
    allow_external: bool = False,
) -> Path:
    """Canonicalize a user path and enforce containment under its declared owner root.

    ``allow_external`` is reserved for an explicit interface whose contract says external paths
    are permitted (currently the CLI's ``--item`` override).  It is never inferred from an
    absolute path.
    """
    owner = Path(root).expanduser().resolve()
    supplied = Path(value).expanduser()
    candidate = supplied.resolve() if supplied.is_absolute() else (owner / supplied).resolve()
    if not allow_external:
        try:
            candidate.relative_to(owner)
        except ValueError as exc:
            raise InputContractError(
                "path_escape",
                f"{kind} {str(value)!r} resolves outside owner root {str(owner)!r}",
            ) from exc
    return candidate


LegacyMigration = Callable[[dict[str, Any]], dict[str, Any]]


def _load_document(
    model: type[_VersionedDocument],
    raw: Any,
    *,
    source: str | Path,
    migrate_legacy: LegacyMigration,
) -> _VersionedDocument:
    if not isinstance(raw, Mapping):
        raise InputContractError("invalid_shape", "YAML document must be a mapping", source=source)
    data = copy.deepcopy(dict(raw))
    allowed = {field.alias or name for name, field in model.model_fields.items()}
    unknown = sorted((key for key in data if key not in allowed), key=str)
    if unknown:
        raise InputContractError(
            "unknown_fields",
            f"unknown top-level key(s): {unknown}; allowed: {sorted(allowed)}",
            source=source,
        )
    has_id = "schema_id" in data
    has_version = "schema_version" in data
    if has_id != has_version:
        raise InputContractError(
            "incomplete_contract_metadata",
            "schema_id and schema_version must be supplied together",
            source=source,
        )
    if not has_id:
        try:
            data = migrate_legacy(data)
        except InputContractError:
            raise
        except (TypeError, ValueError) as exc:
            raise InputContractError("migration_failed", str(exc), source=source) from exc
    else:
        if data["schema_id"] != model.CONTRACT_ID:
            raise InputContractError(
                "wrong_schema",
                f"expected schema_id {model.CONTRACT_ID!r}, got {data['schema_id']!r}",
                source=source,
            )
        if data["schema_version"] != model.CONTRACT_VERSION:
            raise InputContractError(
                "unsupported_schema_version",
                f"{model.CONTRACT_ID!r} supports {model.CONTRACT_VERSION!r}, "
                f"got {data['schema_version']!r}",
                source=source,
            )
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise InputContractError("validation_failed", str(exc), source=source) from exc


def _metadata(contract_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"schema_id": contract_id, "schema_version": SCHEMA_VERSION, **data}


def _migrate_voice(raw: Any) -> Any:
    if not isinstance(raw, Mapping):
        return raw
    voice = copy.deepcopy(dict(raw))
    call_policy = copy.deepcopy(voice.get("call_policy") or {})
    for old, new in (
        ("temperature", "temperature"),
        ("timeout", "timeout_s"),
        ("reasoning_effort", "reasoning_effort"),
    ):
        if old not in voice:
            continue
        if new in call_policy:
            raise ValueError(f"legacy voice cannot specify both {old!r} and call_policy.{new}")
        call_policy[new] = voice.pop(old)
    if call_policy:
        voice["call_policy"] = call_policy
    # workspace/web were internal runtime mutations, never stable authored fields.  A legacy file
    # containing them gets an explicit error from the strict model rather than silent execution.
    return voice


def _migrate_panel(raw: Any) -> Any:
    if not isinstance(raw, Mapping):
        return raw
    panel = copy.deepcopy(dict(raw))
    for key in ("proposers",):
        panel[key] = [_migrate_voice(voice) for voice in panel.get(key, [])]
    for key in ("redteam", "arbitrator"):
        if panel.get(key) is not None:
            panel[key] = _migrate_voice(panel[key])
    return panel


def load_project_input(
    raw: Any, *, source: str | Path, default_id: str | None = None
) -> ProjectInput:
    def migrate(data: dict[str, Any]) -> dict[str, Any]:
        if not data.get("id") and default_id is not None:
            data["id"] = default_id
        return _metadata(ProjectInput.CONTRACT_ID, data)

    return _load_document(ProjectInput, raw, source=source, migrate_legacy=migrate)  # type: ignore[return-value]


def load_cast_input(raw: Any, *, source: str | Path) -> CastInput:
    def migrate(data: dict[str, Any]) -> dict[str, Any]:
        arbitrator = data.get("arbitrator")
        if isinstance(arbitrator, list):
            data["arbitrator"] = arbitrator[0] if len(arbitrator) == 1 else arbitrator
        for key in ("proposers", "reviewers", "adversaries", "aggregators"):
            if key in data and data[key] is not None:
                data[key] = [_migrate_voice(voice) for voice in data[key]]
        if data.get("redteam") is not None:
            data["redteam"] = _migrate_voice(data["redteam"])
        if data.get("arbitrator") is not None:
            data["arbitrator"] = _migrate_voice(data["arbitrator"])
        return _metadata(CastInput.CONTRACT_ID, data)

    return _load_document(CastInput, raw, source=source, migrate_legacy=migrate)  # type: ignore[return-value]


def load_panel_registry_input(raw: Any, *, source: str | Path) -> PanelRegistryInput:
    def migrate(data: dict[str, Any]) -> dict[str, Any]:
        data["panels"] = {
            name: _migrate_panel(panel) for name, panel in (data.get("panels") or {}).items()
        }
        return _metadata(PanelRegistryInput.CONTRACT_ID, data)

    return _load_document(PanelRegistryInput, raw, source=source, migrate_legacy=migrate)  # type: ignore[return-value]


def load_runspec_input(raw: Any, *, source: str | Path) -> RunSpecInput:
    return _load_document(
        RunSpecInput,
        raw,
        source=source,
        migrate_legacy=lambda data: _metadata(RunSpecInput.CONTRACT_ID, data),
    )  # type: ignore[return-value]


def load_profile_input(raw: Any, *, source: str | Path) -> ProfileInput:
    return _load_document(
        ProfileInput,
        raw,
        source=source,
        migrate_legacy=lambda data: _metadata(ProfileInput.CONTRACT_ID, data),
    )  # type: ignore[return-value]


def load_task_family_input(raw: Any, *, source: str | Path) -> TaskFamilyInput:
    return _load_document(
        TaskFamilyInput,
        raw,
        source=source,
        migrate_legacy=lambda data: _metadata(TaskFamilyInput.CONTRACT_ID, data),
    )  # type: ignore[return-value]


def load_materials_manifest_input(raw: Any, *, source: str | Path) -> MaterialsManifestInput:
    def migrate(data: dict[str, Any]) -> dict[str, Any]:
        if data.get("corpus_version") is not None and not isinstance(data["corpus_version"], str):
            data["corpus_version"] = str(data["corpus_version"])
        for item in data.get("sources") or []:
            if isinstance(item, dict):
                for key in ("retrieved", "fetched_at"):
                    if item.get(key) is not None and not isinstance(item[key], str):
                        item[key] = str(item[key])
        return _metadata(MaterialsManifestInput.CONTRACT_ID, data)

    return _load_document(MaterialsManifestInput, raw, source=source, migrate_legacy=migrate)  # type: ignore[return-value]


CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "affordance-policy": AffordancePolicyInput,
    "call-policy": CallPolicyInput,
    "cast": CastInput,
    "materials-manifest": MaterialsManifestInput,
    "panel-registry": PanelRegistryInput,
    "profile": ProfileInput,
    "project": ProjectInput,
    "run-spec": RunSpecInput,
    "task-family-input": TaskFamilyInput,
    "voice": VoiceInput,
}


def generated_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return the deterministic Draft 2020-12 schema for one canonical input model."""
    schema = model.model_json_schema(by_alias=True, mode="validation")
    contract_id = model.CONTRACT_ID
    contract_version = model.CONTRACT_VERSION
    if model is VoiceInput:
        schema["allOf"] = [
            {
                "if": {"properties": {"backend": {"const": "openrouter"}}},
                "then": {
                    "required": ["model"],
                    "properties": {
                        "model": {"type": "string", "minLength": 1},
                        "call_policy": {
                            "properties": {
                                "timeout_s": {"type": "null"},
                                "reasoning_effort": {"type": "null"},
                            }
                        },
                    },
                },
            },
            {
                "if": {"properties": {"backend": {"const": "claude_code"}}},
                "then": {
                    "properties": {
                        "call_policy": {
                            "properties": {
                                "temperature": {"type": "null"},
                                "reasoning_effort": {"type": "null"},
                            }
                        }
                    }
                },
            },
            {
                "if": {"properties": {"backend": {"const": "codex_cli"}}},
                "then": {
                    "properties": {"call_policy": {"properties": {"temperature": {"type": "null"}}}}
                },
            },
            {
                "properties": {
                    "affordances": {
                        "properties": {
                            "web_search": {"const": False},
                            "filesystem": {"const": "none"},
                        }
                    }
                }
            },
        ]
    if model in {ProjectInput, RunSpecInput, TaskFamilyInput}:
        schema["allOf"] = [
            {
                "if": {
                    "anyOf": [
                        {"not": {"required": ["protocol"]}},
                        {
                            "required": ["protocol"],
                            "properties": {"protocol": {"const": "delphi"}},
                        },
                    ]
                },
                "then": {
                    "properties": {
                        "aggregator": {
                            "enum": ["arbitrator_select", None],
                        }
                    }
                },
            },
            {
                "if": {
                    "required": ["protocol"],
                    "properties": {"protocol": {"const": "idea"}},
                },
                "then": {
                    "properties": {
                        "aggregator": {
                            "enum": ["statistical", None],
                        }
                    }
                },
            },
        ]
    if model is ProfileInput:
        schema["allOf"] = [
            {
                "if": {
                    "required": ["protocol"],
                    "properties": {"protocol": {"const": "delphi"}},
                },
                "then": {"properties": {"aggregator": {"const": "arbitrator_select"}}},
            },
            {
                "if": {
                    "required": ["protocol"],
                    "properties": {"protocol": {"const": "idea"}},
                },
                "then": {"properties": {"aggregator": {"const": "statistical"}}},
            },
        ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://cesia.org/schemas/{contract_id}/{contract_version}",
        "x-schema-id": contract_id,
        "x-schema-version": contract_version,
        **schema,
    }
