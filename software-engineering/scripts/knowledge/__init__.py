"""Deterministic routing metadata and generated-index contracts."""

from .corpus import (
    Finding,
    KnowledgeRecord,
    SourceRecord,
    build_index,
    read_selected,
    scan_corpus,
    scan_source_register,
    select_records,
    validate_corpus,
)
from .fitness import (
    GuidanceFinding,
    GuidanceFitnessPolicy,
    GuidanceFitnessReport,
    evaluate_guidance_fitness,
)

__all__ = [
    "Finding",
    "GuidanceFinding",
    "GuidanceFitnessPolicy",
    "GuidanceFitnessReport",
    "KnowledgeRecord",
    "SourceRecord",
    "build_index",
    "evaluate_guidance_fitness",
    "read_selected",
    "scan_corpus",
    "scan_source_register",
    "select_records",
    "validate_corpus",
]
