"""Application orchestration over owned ports."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from time import monotonic

from doc2md.core.conformance import (
    CertifiedExtractor,
    ConformanceError,
    validate_runtime_candidate,
)
from doc2md.core.models import (
    Attempt,
    AttemptCancelledError,
    AttemptContext,
    AttemptStatus,
    AttemptTimedOutError,
    CancellationSignal,
    ConversionPolicy,
    ConversionResult,
    ConversionStatus,
    NeverCancelled,
    SourceDocument,
)
from doc2md.core.ports import ArtifactStorePort, AssessorPort, RouterPort


class RoutingError(ValueError):
    """A router returned a plan or selection outside the owned contract."""


def _policy_denial(
    certified: CertifiedExtractor,
    policy: ConversionPolicy,
) -> str | None:
    capabilities = certified.adapter.capabilities
    checks = (
        (
            capabilities.requires_network and not policy.allow_network,
            "network permission required",
        ),
        (
            capabilities.external_processing and not policy.allow_external_processing,
            "external-processing permission required",
        ),
        (
            capabilities.paid and not policy.allow_paid,
            "paid-processing permission required",
        ),
        (
            capabilities.generative and not policy.allow_generative,
            "generative-processing permission required",
        ),
    )
    return next((message for denied, message in checks if denied), None)


class ConvertService:
    """Coordinate extraction, assessment, selection, and persistence."""

    def __init__(
        self,
        *,
        assessor: AssessorPort,
        router: RouterPort,
        artifacts: ArtifactStorePort,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._assessor = assessor
        self._router = router
        self._artifacts = artifacts
        self._clock = clock

    def convert(
        self,
        source: SourceDocument,
        extractors: Sequence[CertifiedExtractor],
        *,
        policy: ConversionPolicy,
        cancellation: CancellationSignal | None = None,
    ) -> ConversionResult:
        adapters = self._index_extractors(extractors)
        plan = self._router.plan(
            source,
            [item.adapter.capabilities for item in extractors],
            policy,
        )
        self._validate_plan(plan, adapters, policy.max_attempts)
        signal = cancellation if cancellation is not None else NeverCancelled()
        attempts = tuple(
            self._attempt(source, adapters[adapter_id], policy, signal)
            for adapter_id in plan
        )
        winner_id = self._router.select(attempts)
        winner = self._validate_selection(winner_id, attempts)
        if winner is None:
            paused = any(
                attempt.status in {AttemptStatus.CANCELLED, AttemptStatus.TIMED_OUT}
                for attempt in attempts
            )
            return ConversionResult(
                status=ConversionStatus.PAUSED if paused else ConversionStatus.FAILED,
                source_sha256=source.sha256,
                attempts=attempts,
                winner_adapter_id=None,
                artifact=None,
            )

        artifact = self._artifacts.persist(source, winner, attempts)
        status = (
            ConversionStatus.OK
            if winner.status is AttemptStatus.OK
            else ConversionStatus.DEGRADED
        )
        return ConversionResult(
            status=status,
            source_sha256=source.sha256,
            attempts=attempts,
            winner_adapter_id=winner.adapter_id,
            artifact=artifact,
        )

    @staticmethod
    def _index_extractors(
        extractors: Sequence[CertifiedExtractor],
    ) -> dict[str, CertifiedExtractor]:
        adapters: dict[str, CertifiedExtractor] = {}
        for certified in extractors:
            if not isinstance(certified, CertifiedExtractor):
                raise ConformanceError(
                    "production routing accepts only CertifiedExtractor instances"
                )
            if certified.adapter_id in adapters:
                raise ConformanceError(f"duplicate adapter_id: {certified.adapter_id}")
            adapters[certified.adapter_id] = certified
        return adapters

    @staticmethod
    def _validate_plan(
        plan: object,
        adapters: dict[str, CertifiedExtractor],
        max_attempts: int,
    ) -> None:
        if not isinstance(plan, tuple) or any(
            not isinstance(item, str) for item in plan
        ):
            raise RoutingError("router plan must be a tuple of adapter IDs")
        if len(plan) != len(set(plan)):
            raise RoutingError("router plan contains a duplicate adapter ID")
        if len(plan) > max_attempts:
            raise RoutingError(
                f"router plan exceeds the {max_attempts}-attempt policy budget"
            )
        unknown = set(plan).difference(adapters)
        if unknown:
            raise RoutingError(f"router planned unknown adapters: {sorted(unknown)}")

    def _attempt(
        self,
        source: SourceDocument,
        certified: CertifiedExtractor,
        policy: ConversionPolicy,
        cancellation: CancellationSignal,
    ) -> Attempt:
        denial = _policy_denial(certified, policy)
        if denial is not None:
            return Attempt(
                adapter_id=certified.adapter_id,
                status=AttemptStatus.POLICY_DENIED,
                diagnostics=(denial,),
            )
        if source.media_type not in certified.adapter.capabilities.media_types:
            return Attempt(
                adapter_id=certified.adapter_id,
                status=AttemptStatus.FAILED,
                diagnostics=("adapter does not declare the source media type",),
            )

        context = AttemptContext(
            deadline=self._clock() + policy.timeout_seconds,
            clock=self._clock,
            cancellation=cancellation,
        )
        try:
            context.raise_if_stopped()
            candidate = certified.adapter.extract(source, context)
            context.raise_if_stopped()
            candidate = validate_runtime_candidate(
                candidate,
                certified=certified,
                source=source,
            )
            quality = self._assessor.assess(source, candidate)
            context.raise_if_stopped()
        except AttemptCancelledError as error:
            return Attempt(
                adapter_id=certified.adapter_id,
                status=AttemptStatus.CANCELLED,
                diagnostics=(str(error),),
            )
        except AttemptTimedOutError as error:
            return Attempt(
                adapter_id=certified.adapter_id,
                status=AttemptStatus.TIMED_OUT,
                diagnostics=(str(error),),
            )
        except ConformanceError as error:
            return Attempt(
                adapter_id=certified.adapter_id,
                status=AttemptStatus.FAILED,
                diagnostics=(str(error),),
            )
        except Exception as error:
            return Attempt(
                adapter_id=certified.adapter_id,
                status=AttemptStatus.FAILED,
                diagnostics=(f"attempt boundary raised {type(error).__name__}",),
            )

        return Attempt(
            adapter_id=certified.adapter_id,
            status=AttemptStatus.OK if quality.usable else AttemptStatus.DEGRADED,
            candidate=candidate,
            quality=quality,
            diagnostics=candidate.diagnostics,
        )

    @staticmethod
    def _validate_selection(
        winner_id: str | None,
        attempts: Sequence[Attempt],
    ) -> Attempt | None:
        if winner_id is None:
            return None
        eligible = {
            attempt.adapter_id: attempt
            for attempt in attempts
            if attempt.status in {AttemptStatus.OK, AttemptStatus.DEGRADED}
            and attempt.candidate is not None
            and attempt.quality is not None
        }
        try:
            return eligible[winner_id]
        except KeyError as error:
            raise RoutingError(
                "router selected an absent, denied, failed, or interrupted attempt"
            ) from error
