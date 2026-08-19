"""Ports owned by the doc2md application core."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from doc2md.core.models import (
    AdapterCapabilities,
    ArtifactReceipt,
    Attempt,
    AttemptContext,
    Candidate,
    ConversionPolicy,
    QualityAssessment,
    SourceDocument,
)


class InputResolverPort(Protocol):
    """Resolve an input reference into policy-checked acquisition metadata."""

    def resolve(self, value: str) -> object:
        """Return an owned resolved-input value defined by Task 0005."""


class FetcherPort(Protocol):
    """Acquire bytes for an already resolved input."""

    def fetch(self, resolved: object, context: AttemptContext) -> SourceDocument:
        """Return source bytes without performing extraction."""


class ExtractorPort(Protocol):
    """Convert source bytes into a candidate without selecting it."""

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Return declared eligibility and safety facts."""

    def extract(self, source: SourceDocument, context: AttemptContext) -> Candidate:
        """Return one candidate or raise an explicit attempt control exception."""


class AssessorPort(Protocol):
    """Assess a candidate without routing or persistence side effects."""

    def assess(
        self,
        source: SourceDocument,
        candidate: Candidate,
    ) -> QualityAssessment:
        """Return evidence used by routing selection."""


class RouterPort(Protocol):
    """Plan adapter IDs and select from recorded attempts."""

    def plan(
        self,
        source: SourceDocument,
        capabilities: Sequence[AdapterCapabilities],
        policy: ConversionPolicy,
    ) -> tuple[str, ...]:
        """Return an ordered, bounded adapter plan."""

    def select(self, attempts: Sequence[Attempt]) -> str | None:
        """Return the winning attempt's adapter ID, or no winner."""


class ArtifactStorePort(Protocol):
    """Persist a selected result behind an owned artifact boundary."""

    def persist(
        self,
        source: SourceDocument,
        winner: Attempt,
        attempts: Sequence[Attempt],
    ) -> ArtifactReceipt:
        """Persist atomically and return an opaque receipt."""
