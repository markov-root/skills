"""Immutable core values shared by application ports."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from math import isfinite
from types import MappingProxyType
from typing import Protocol


class AttemptStatus(str, Enum):
    """Terminal state of one adapter attempt."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    POLICY_DENIED = "policy_denied"


class ConversionStatus(str, Enum):
    """Aggregate state returned by the application shell."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"
    PAUSED = "paused"


class ProvenanceTier(str, Enum):
    """How candidate content was produced."""

    DETERMINISTIC_EXTRACTION = "deterministic-extraction"
    OCR = "ocr"
    GENERATIVE_RECONSTRUCTION = "generative-reconstruction"
    HUMAN_AUTHORED = "human-authored"
    UNKNOWN = "unknown"


class QualitySeverity(str, Enum):
    """Severity of one deterministic quality finding."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


QualityMetric = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class QualityFlag:
    """One named quality finding with non-secret evidence."""

    code: str
    severity: QualitySeverity
    hard_failure: bool
    message: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            not self.code
            or self.code != self.code.lower()
            or not self.code.replace("_", "").isalnum()
        ):
            raise ValueError("quality flag code must be snake-like alphanumeric text")
        if not self.code[0].islower():
            raise ValueError("quality flag code must start with a lowercase letter")
        if not isinstance(self.severity, QualitySeverity):
            raise TypeError("quality severity must be a QualitySeverity")
        if type(self.hard_failure) is not bool:
            raise TypeError("quality hard_failure must be a boolean")
        if not self.message:
            raise ValueError("quality flag message must not be empty")
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


@dataclass(frozen=True, slots=True)
class TransformationRecord:
    """Versioned normalization or projection step applied to candidate evidence."""

    operation: str
    version: str
    lossy: bool
    affected_units: int | None = None

    def __post_init__(self) -> None:
        if not self.operation or not self.version:
            raise ValueError("transformation operation and version must not be empty")
        if type(self.lossy) is not bool:
            raise TypeError("transformation lossy declaration must be a boolean")
        if self.affected_units is not None and self.affected_units < 0:
            raise ValueError("affected_units must not be negative")


class CancellationSignal(Protocol):
    """Caller-owned cooperative cancellation signal."""

    @property
    def cancelled(self) -> bool:
        """Return whether work should stop."""


@dataclass(frozen=True, slots=True)
class NeverCancelled:
    """Default signal for callers that do not need cancellation."""

    @property
    def cancelled(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """Resolved source bytes at the extraction seam."""

    data: bytes
    media_type: str
    display_name: str
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes):
            raise TypeError("source data must be bytes")
        if "/" not in self.media_type:
            raise ValueError("media_type must be a MIME type")
        if not self.display_name:
            raise ValueError("display_name must not be empty")
        if self.sha256 != sha256(self.data).hexdigest():
            raise ValueError("source sha256 does not match source data")

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        media_type: str,
        display_name: str = "<bytes>",
    ) -> SourceDocument:
        if not isinstance(data, bytes):
            raise TypeError("source data must be bytes")
        if "/" not in media_type:
            raise ValueError("media_type must be a MIME type")
        if not display_name:
            raise ValueError("display_name must not be empty")
        return cls(
            data=data,
            media_type=media_type,
            display_name=display_name,
            sha256=sha256(data).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class AdapterCapabilities:
    """Safety and eligibility facts declared by an extractor adapter."""

    adapter_id: str
    version: str
    media_types: frozenset[str]
    requires_network: bool = False
    external_processing: bool = False
    paid: bool = False
    generative: bool = False

    def __post_init__(self) -> None:
        if not self.adapter_id or not self.version:
            raise ValueError("adapter_id and version must not be empty")
        if not self.media_types or any("/" not in item for item in self.media_types):
            raise ValueError("media_types must contain at least one MIME type")
        declarations = (
            self.requires_network,
            self.external_processing,
            self.paid,
            self.generative,
        )
        if any(type(item) is not bool for item in declarations):
            raise TypeError("capability declarations must be booleans")


@dataclass(frozen=True, slots=True)
class ConversionPolicy:
    """Explicit caller authority and per-attempt budget."""

    allow_network: bool = False
    allow_external_processing: bool = False
    allow_paid: bool = False
    allow_generative: bool = False
    timeout_seconds: float = 30.0
    max_attempts: int = 3

    def __post_init__(self) -> None:
        permissions = (
            self.allow_network,
            self.allow_external_processing,
            self.allow_paid,
            self.allow_generative,
        )
        if any(type(item) is not bool for item in permissions):
            raise TypeError("policy permissions must be booleans")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if type(self.max_attempts) is not int or self.max_attempts <= 0:
            raise ValueError("max_attempts must be a positive integer")


@dataclass(frozen=True, slots=True)
class AttemptContext:
    """Budget and cooperative cancellation state passed to an adapter."""

    deadline: float
    clock: Callable[[], float]
    cancellation: CancellationSignal = field(default_factory=NeverCancelled)

    def raise_if_stopped(self) -> None:
        if self.cancellation.cancelled:
            raise AttemptCancelledError("attempt cancelled")
        if self.clock() >= self.deadline:
            raise AttemptTimedOutError("attempt deadline exceeded")


class AttemptCancelledError(Exception):
    """An adapter honored cooperative cancellation."""


class AttemptTimedOutError(Exception):
    """An adapter honored its attempt deadline."""


@dataclass(frozen=True, slots=True)
class Candidate:
    """Technology-neutral candidate emitted by an extractor.

    ``metadata`` carries deterministically-harvested, non-secret source facts (for example
    ``title``, ``author``, ``date``, ``sitename``, ``extractor``) for the persistence layer to
    project into frontmatter. It is descriptive evidence, never a routing input, and holds only
    public string scalars.
    """

    adapter_id: str
    source_sha256: str
    markdown: str
    provenance_tier: ProvenanceTier
    diagnostics: tuple[str, ...] = ()
    native_artifacts: tuple[str, ...] = ()
    transformations: tuple[TransformationRecord, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in self.metadata.items():
            if not isinstance(name, str) or not name:
                raise TypeError("candidate metadata keys must be non-empty strings")
            if not isinstance(value, str):
                raise TypeError("candidate metadata values must be strings")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    """Deterministic report used by selection without discarding evidence."""

    usable: bool
    score: float | None
    warnings: tuple[str, ...] = ()
    metrics: Mapping[str, QualityMetric] = field(default_factory=dict)
    flags: tuple[QualityFlag, ...] = ()
    explanation: str = "No detailed quality explanation was supplied."

    def __post_init__(self) -> None:
        if self.score is not None and (
            not isfinite(self.score) or not 0 <= self.score <= 1
        ):
            raise ValueError("quality score must be finite and between 0 and 1")
        if any(not isinstance(item, QualityFlag) for item in self.flags):
            raise TypeError("quality flags must contain QualityFlag values")
        if any(flag.hard_failure for flag in self.flags) and self.usable:
            raise ValueError("hard quality failures cannot be marked usable")
        if not self.explanation:
            raise ValueError("quality explanation must not be empty")
        for name, value in self.metrics.items():
            if not isinstance(name, str) or not name:
                raise TypeError("quality metric names must be non-empty strings")
            if not isinstance(value, (str, int, float, bool, type(None))):
                raise TypeError("quality metric values must be public scalar values")
            if isinstance(value, float) and not isfinite(value):
                raise ValueError("quality metric floats must be finite")
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


@dataclass(frozen=True, slots=True)
class Attempt:
    """Recorded outcome of one eligible, denied, or interrupted route."""

    adapter_id: str
    status: AttemptStatus
    candidate: Candidate | None = None
    quality: QualityAssessment | None = None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArtifactReceipt:
    """Technology-neutral identity returned by an artifact-store port."""

    run_id: str
    bundle_path: str


@dataclass(frozen=True, slots=True)
class ConversionResult:
    """Internal orchestration result before public-schema projection."""

    status: ConversionStatus
    source_sha256: str
    attempts: tuple[Attempt, ...]
    winner_adapter_id: str | None
    artifact: ArtifactReceipt | None
