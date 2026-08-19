"""Single projection code path for the queryable frontmatter and the public result contract.

Both the human/agent-facing ``document.md`` frontmatter and the authoritative ``result.json`` are
built here from the same inputs, so their overlapping fields cannot drift (Task 0023).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from doc2md.core.models import (
    Attempt,
    Candidate,
    ConversionResult,
    QualityAssessment,
    SourceDocument,
)
from doc2md.store.dates import normalize_dates
from doc2md.store.frontmatter import (
    body_content_sha256,
    heading_outline,
    outline_is_inline,
    text_metrics,
)

FRONTMATTER_SCHEMA_VERSION = 1
RESULT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class Acquisition:
    """Acquisition-stage facts the extraction seam does not carry, held by the orchestrator."""

    input: str
    source_url: str | None = None
    kind: str | None = None
    retrieved_at: str | None = None
    fetch_layer: str | None = None
    extra: Mapping[str, str] = field(default_factory=dict)


def _harvested_fields(metadata: Mapping[str, str], extractor: str) -> dict[str, object]:
    """Project harvested source metadata, tagging any harvested date with its provenance."""

    out: dict[str, object] = {}
    for key in ("title", "author", "sitename"):
        value = metadata.get(key)
        if value:
            out[key] = value
    dates, _ = normalize_dates(metadata, extractor)
    if dates:
        out["dates"] = dates
    hyperlinks = metadata.get("hyperlinks")
    if hyperlinks:
        out["hyperlinks"] = int(hyperlinks) if hyperlinks.isdigit() else hyperlinks
    pages = metadata.get("pages")
    if pages and pages.isdigit():
        out["pages"] = int(pages)
    coverage = metadata.get("text_coverage")
    if coverage:
        try:
            out["text_coverage"] = float(coverage)
        except ValueError:
            out["text_coverage"] = coverage
    return out


def _quality_block(quality: QualityAssessment | None) -> dict[str, object]:
    if quality is None:
        return {"usable": False, "score": None, "flags": []}
    return {
        "usable": quality.usable,
        "score": quality.score,
        "flags": [flag.code for flag in quality.flags],
    }


def project_frontmatter(
    *,
    source: SourceDocument,
    candidate: Candidate,
    quality: QualityAssessment | None,
    acquisition: Acquisition,
    run_id: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Build the ordered frontmatter mapping and the heading outline for a winning candidate."""

    body = candidate.markdown
    extractor = candidate.metadata.get("extractor", candidate.adapter_id)
    fields: dict[str, object] = {
        "schema_version": FRONTMATTER_SCHEMA_VERSION,
        "doc2md_run_id": run_id,
        "source": {
            "input": acquisition.input,
            "source_url": acquisition.source_url,
            "media_type": source.media_type,
            "kind": acquisition.kind,
            "raw_sha256": source.sha256,
            "content_sha256": body_content_sha256(body),
            "retrieved_at": acquisition.retrieved_at,
        },
        "extractor": extractor,
        "provenance_tier": candidate.provenance_tier.value,
        "fetch_layer": acquisition.fetch_layer,
        "quality": _quality_block(quality),
        "metrics": text_metrics(body),
    }
    fields.update(_harvested_fields(candidate.metadata, extractor))
    outline = heading_outline(body)
    if outline_is_inline(outline):
        fields["outline"] = outline
    else:
        fields["outline_path"] = f"{run_id}.outline.json"
    return fields, outline


def _attempt_public(attempt: Attempt) -> dict[str, object]:
    return {
        "adapter": attempt.adapter_id,
        "status": attempt.status.value,
        "usable": None if attempt.quality is None else attempt.quality.usable,
        "score": None if attempt.quality is None else attempt.quality.score,
        "diagnostics": list(attempt.diagnostics),
    }


def project_result(
    *,
    result: ConversionResult,
    source: SourceDocument,
    acquisition: Acquisition,
    run_id: str,
    bundle_path: str,
    markdown_path: str | None,
    doc2md_version: str,
) -> dict[str, object]:
    """Project the internal ConversionResult to the versioned public v1 result object."""

    winner = next(
        (a for a in result.attempts if a.adapter_id == result.winner_adapter_id),
        None,
    )
    winner_candidate = winner.candidate if winner is not None else None
    winner_quality = winner.quality if winner is not None else None
    content_sha = (
        body_content_sha256(winner_candidate.markdown)
        if winner_candidate is not None
        else None
    )
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "run_id": run_id,
        "status": result.status.value,
        "request": {
            "input": acquisition.input,
            "kind": acquisition.kind,
        },
        "source": {
            "input": acquisition.input,
            "canonical_url": acquisition.source_url,
            "media_type": source.media_type,
            "raw_sha256": source.sha256,
            "bytes": len(source.data),
            "retrieved_at": acquisition.retrieved_at,
        },
        "output": _output_block(
            winner_candidate, content_sha, markdown_path, bundle_path
        ),
        "route": {
            "winner": result.winner_adapter_id,
            "fetch_layer": acquisition.fetch_layer,
            "attempts": [_attempt_public(a) for a in result.attempts],
        },
        "quality": _quality_block(winner_quality),
        "provenance": {"doc2md_version": doc2md_version},
        "warnings": _collect_warnings(winner_candidate, winner_quality),
    }


def _output_block(
    candidate: Candidate | None,
    content_sha: str | None,
    markdown_path: str | None,
    bundle_path: str,
) -> dict[str, object]:
    return {
        "markdown_path": markdown_path if candidate is not None else None,
        "content_sha256": content_sha,
        "provenance_tier": None
        if candidate is None
        else candidate.provenance_tier.value,
        "bundle_path": bundle_path,
    }


def _collect_warnings(
    winner_candidate: Candidate | None,
    winner_quality: QualityAssessment | None,
) -> list[str]:
    warnings: list[str] = []
    if winner_quality is not None:
        warnings.extend(winner_quality.warnings)
    if winner_candidate is not None:
        extractor = winner_candidate.metadata.get(
            "extractor", winner_candidate.adapter_id
        )
        _, date_diagnostics = normalize_dates(winner_candidate.metadata, extractor)
        warnings.extend(date_diagnostics)
    return warnings
