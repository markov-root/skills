"""Deterministic, extractive candidate producers (adapters) and shared text normalization.

Each adapter implements :class:`doc2md.core.ports.ExtractorPort`: given resolved source
bytes it returns exactly one :class:`doc2md.core.models.Candidate` without selecting it,
persisting it, or reaching the network. Adapters honor the cooperative cancellation and
deadline carried on the :class:`doc2md.core.models.AttemptContext` and never fabricate
content: a source that cannot be extracted deterministically raises rather than inventing
Markdown (see ``docs/adr/0004`` and ``docs/context/fetch-and-conversion-ladders.md``).
"""

from doc2md.extract.plaintext import PlaintextExtractor
from doc2md.extract.textnorm import (
    TEXTNORM_VERSION,
    dehyphenate,
    normalize_for_search,
    strip_invisibles,
)

__all__ = [
    "TEXTNORM_VERSION",
    "PlaintextExtractor",
    "dehyphenate",
    "normalize_for_search",
    "strip_invisibles",
]
