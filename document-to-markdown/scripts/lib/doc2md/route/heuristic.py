"""A deterministic, media-type-driven router (RouterPort implementation)."""

from __future__ import annotations

from collections.abc import Sequence

from doc2md.core.models import (
    AdapterCapabilities,
    Attempt,
    AttemptStatus,
    ConversionPolicy,
    SourceDocument,
)

# Lower number = tried earlier when several adapters declare the same media type. Unlisted
# adapters default to a low preference so a purpose-built adapter always precedes a generic one.
_DEFAULT_PREFERENCE: dict[str, int] = {
    "pdf": 10,
    "html": 10,
    "docx": 10,
    "plaintext": 50,
}
_UNLISTED_PREFERENCE = 100


class HeuristicRouter:
    """Plan eligible adapters in a stable order and select the best successful attempt."""

    def __init__(self, preference: dict[str, int] | None = None) -> None:
        self._preference = preference if preference is not None else _DEFAULT_PREFERENCE

    def _rank(self, adapter_id: str) -> tuple[int, str]:
        return (self._preference.get(adapter_id, _UNLISTED_PREFERENCE), adapter_id)

    def plan(
        self,
        source: SourceDocument,
        capabilities: Sequence[AdapterCapabilities],
        policy: ConversionPolicy,
    ) -> tuple[str, ...]:
        eligible = [
            cap.adapter_id
            for cap in capabilities
            if source.media_type in cap.media_types
        ]
        eligible.sort(key=self._rank)
        return tuple(eligible[: policy.max_attempts])

    def select(self, attempts: Sequence[Attempt]) -> str | None:
        best: Attempt | None = None
        best_key: tuple[int, float] | None = None
        for attempt in attempts:
            if (
                attempt.status not in {AttemptStatus.OK, AttemptStatus.DEGRADED}
                or attempt.candidate is None
                or attempt.quality is None
            ):
                continue
            # Prefer OK over DEGRADED, then higher score. A missing score sorts as neutral 0.0.
            status_rank = 1 if attempt.status is AttemptStatus.OK else 0
            score = attempt.quality.score if attempt.quality.score is not None else 0.0
            key = (status_rank, score)
            if best_key is None or key > best_key:
                best, best_key = attempt, key
        return best.adapter_id if best is not None else None
