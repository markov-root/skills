"""Extractor conformance checks required before application routing."""

from __future__ import annotations

from dataclasses import dataclass

from doc2md.core.models import (
    AdapterCapabilities,
    AttemptCancelledError,
    AttemptContext,
    AttemptTimedOutError,
    Candidate,
    ConversionPolicy,
    NeverCancelled,
    ProvenanceTier,
    SourceDocument,
    TransformationRecord,
)
from doc2md.core.ports import ExtractorPort


class ConformanceError(ValueError):
    """An adapter does not satisfy the owned extractor contract."""


_CERTIFICATION_TOKEN = object()


@dataclass(frozen=True, slots=True)
class _Cancelled:
    @property
    def cancelled(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class CertifiedExtractor:
    """Extractor plus deterministic evidence that its core seam conforms."""

    adapter: ExtractorPort
    adapter_id: str
    version: str
    checks: tuple[str, ...]
    _token: object

    def __post_init__(self) -> None:
        if self._token is not _CERTIFICATION_TOKEN:
            raise ConformanceError(
                "CertifiedExtractor instances must come from certify_extractor()"
            )


def _validate_candidate(
    candidate: object,
    capabilities: AdapterCapabilities,
    source: SourceDocument,
) -> Candidate:
    if not isinstance(candidate, Candidate):
        raise ConformanceError("extract() must return Candidate")
    if candidate.adapter_id != capabilities.adapter_id:
        raise ConformanceError("candidate adapter_id does not match capabilities")
    if candidate.source_sha256 != source.sha256:
        raise ConformanceError("candidate source_sha256 does not match input bytes")
    if not isinstance(candidate.markdown, str):
        raise ConformanceError("candidate markdown must be a string")
    if not isinstance(candidate.provenance_tier, ProvenanceTier):
        raise ConformanceError("candidate provenance_tier must be a ProvenanceTier")
    if not isinstance(candidate.diagnostics, tuple) or any(
        not isinstance(item, str) for item in candidate.diagnostics
    ):
        raise ConformanceError("candidate diagnostics must be a tuple of strings")
    if not isinstance(candidate.native_artifacts, tuple) or any(
        not isinstance(item, str) for item in candidate.native_artifacts
    ):
        raise ConformanceError("candidate native_artifacts must be a tuple of strings")
    if not isinstance(candidate.transformations, tuple) or any(
        not isinstance(item, TransformationRecord) for item in candidate.transformations
    ):
        raise ConformanceError(
            "candidate transformations must be TransformationRecord values"
        )
    if any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in candidate.metadata.items()
    ):
        raise ConformanceError("candidate metadata must map strings to strings")
    if (
        capabilities.generative
        and candidate.provenance_tier is not ProvenanceTier.GENERATIVE_RECONSTRUCTION
    ):
        raise ConformanceError(
            "generative adapters must label candidate provenance explicitly"
        )
    return candidate


def certify_extractor(
    adapter: ExtractorPort,
    *,
    fixture: SourceDocument,
    policy: ConversionPolicy | None = None,
) -> CertifiedExtractor:
    """Exercise the local bytes-in, cancellation, timeout, and result seam."""

    try:
        capabilities = adapter.capabilities
    except Exception as error:
        raise ConformanceError("adapter capabilities are unavailable") from error
    if not isinstance(capabilities, AdapterCapabilities):
        raise ConformanceError("capabilities must be AdapterCapabilities")
    if fixture.media_type not in capabilities.media_types:
        raise ConformanceError("fixture media type is not declared by the adapter")
    authority = policy if policy is not None else ConversionPolicy()
    permission_checks = (
        (capabilities.requires_network, authority.allow_network, "network"),
        (
            capabilities.external_processing,
            authority.allow_external_processing,
            "external processing",
        ),
        (capabilities.paid, authority.allow_paid, "paid processing"),
        (capabilities.generative, authority.allow_generative, "generative processing"),
    )
    missing_permissions = [
        label
        for required, allowed, label in permission_checks
        if required and not allowed
    ]
    if missing_permissions:
        raise ConformanceError(
            "certification requires explicit permission for: "
            + ", ".join(missing_permissions)
        )

    normal_context = AttemptContext(
        deadline=1.0,
        clock=lambda: 0.0,
        cancellation=NeverCancelled(),
    )
    candidate = adapter.extract(fixture, normal_context)
    _validate_candidate(candidate, capabilities, fixture)

    cancelled_context = AttemptContext(
        deadline=1.0,
        clock=lambda: 0.0,
        cancellation=_Cancelled(),
    )
    try:
        adapter.extract(fixture, cancelled_context)
    except AttemptCancelledError:
        pass
    else:
        raise ConformanceError("adapter did not honor a pre-cancelled context")

    timed_out_context = AttemptContext(
        deadline=0.0,
        clock=lambda: 0.0,
        cancellation=NeverCancelled(),
    )
    try:
        adapter.extract(fixture, timed_out_context)
    except AttemptTimedOutError:
        pass
    else:
        raise ConformanceError("adapter did not honor an expired deadline")

    return CertifiedExtractor(
        adapter=adapter,
        adapter_id=capabilities.adapter_id,
        version=capabilities.version,
        checks=(
            "capability-declarations",
            "bytes-in-result",
            "source-identity",
            "cancellation",
            "timeout",
        ),
        _token=_CERTIFICATION_TOKEN,
    )


def validate_runtime_candidate(
    candidate: object,
    *,
    certified: CertifiedExtractor,
    source: SourceDocument,
) -> Candidate:
    """Recheck candidate identity at the production invocation boundary."""

    return _validate_candidate(candidate, certified.adapter.capabilities, source)
