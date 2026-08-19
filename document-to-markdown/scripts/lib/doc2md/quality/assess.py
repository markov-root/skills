"""Format-aware deterministic quality evidence for extracted candidates."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from doc2md.core import (
    Candidate,
    ProvenanceTier,
    QualityAssessment,
    QualityFlag,
    QualityMetric,
    QualitySeverity,
    SourceDocument,
)

_INVISIBLE_CODEPOINTS = (
    [chr(codepoint) for codepoint in range(0x200B, 0x2010)]
    + [chr(codepoint) for codepoint in range(0x202A, 0x202F)]
    + [chr(0x2060), chr(0xFEFF)]
)
_INVISIBLE_RE = re.compile("[" + re.escape("".join(_INVISIBLE_CODEPOINTS)) + "]")
_MOJIBAKE_RE = re.compile(
    "[\u00c2\u00c3\u00e2]"
    "[\u0080-\u00bf\u2013\u2014\u2019\u201c\u201d\u20ac\u2122]"
    "|\ufffd"
)
_MD_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\([^)]+\)")
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_HEADING_RE = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+\S", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^\s*```", re.MULTILINE)
_SPACED_CAPS_RE = re.compile(r"\b(?:[A-Z]\s){4,}[A-Z]\b")
_CHALLENGE_PHRASES = (
    "verify you are human",
    "checking your browser",
    "enable javascript and cookies to continue",
    "cloudflare ray id",
    "access denied",
    "sign in to continue",
    "log in to continue",
)
_STRONG_CHALLENGE_PHRASES = frozenset(
    {
        "verify you are human",
        "checking your browser",
        "enable javascript and cookies to continue",
        "cloudflare ray id",
        "sign in to continue",
        "log in to continue",
    }
)


@dataclass(frozen=True, slots=True)
class QualityProfile:
    """Named, reviewable usability policy over deterministic evidence."""

    profile_id: str = "general-extractive-v1"
    thin_character_hint: int | None = 200
    thin_is_hard_failure: bool = False
    minimum_printable_ratio: float = 0.95
    maximum_repeated_line_ratio: float = 0.30
    minimum_source_mapping_coverage: float | None = None
    minimum_ocr_coverage: float = 0.90
    minimum_ocr_confidence: float = 0.60

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("quality profile_id must not be empty")
        if self.thin_character_hint is not None and self.thin_character_hint <= 0:
            raise ValueError("thin_character_hint must be positive when present")
        for value in (
            self.minimum_printable_ratio,
            self.maximum_repeated_line_ratio,
            self.minimum_ocr_coverage,
            self.minimum_ocr_confidence,
        ):
            if not 0 <= value <= 1:
                raise ValueError("quality ratios must be between zero and one")
        if (
            self.minimum_source_mapping_coverage is not None
            and not 0 <= self.minimum_source_mapping_coverage <= 1
        ):
            raise ValueError(
                "minimum_source_mapping_coverage must be between zero and one"
            )


RESEARCH_DATABASE_COMPAT_PROFILE = QualityProfile(
    profile_id="research-database-compat-v1",
    thin_character_hint=800,
    thin_is_hard_failure=True,
)


@dataclass(frozen=True, slots=True)
class AssessmentContext:
    """Source- or acquisition-aware evidence unavailable from Markdown alone."""

    title: str | None = None
    expected_short_document: bool = False
    wrong_document: bool = False
    truncated: bool = False
    suspected_invention: bool = False
    policy_violation: bool = False
    malware_detected: bool = False
    expected_units: int | None = None
    covered_units: int | None = None
    source_mapping_coverage: float | None = None
    ocr_coverage: float | None = None
    ocr_confidence: float | None = None
    soft_score: float | None = None
    adapter_flags: tuple[QualityFlag, ...] = ()
    additional_metrics: Mapping[str, QualityMetric] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.expected_short_document) is not bool:
            raise TypeError("expected_short_document must be a boolean")
        for name, value in (
            ("wrong_document", self.wrong_document),
            ("truncated", self.truncated),
            ("suspected_invention", self.suspected_invention),
            ("policy_violation", self.policy_violation),
            ("malware_detected", self.malware_detected),
        ):
            if type(value) is not bool:
                raise TypeError(f"{name} must be a boolean")
        for name, integer_value in (
            ("expected_units", self.expected_units),
            ("covered_units", self.covered_units),
        ):
            if integer_value is not None and (
                type(integer_value) is not int or integer_value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer")
        for name, ratio_value in (
            ("source_mapping_coverage", self.source_mapping_coverage),
            ("ocr_coverage", self.ocr_coverage),
            ("ocr_confidence", self.ocr_confidence),
            ("soft_score", self.soft_score),
        ):
            if ratio_value is not None and not 0 <= ratio_value <= 1:
                raise ValueError(f"{name} must be between zero and one")
        if any(not isinstance(flag, QualityFlag) for flag in self.adapter_flags):
            raise TypeError("adapter_flags must contain QualityFlag values")
        object.__setattr__(
            self,
            "additional_metrics",
            MappingProxyType(dict(self.additional_metrics)),
        )


def _flag(
    code: str,
    message: str,
    *,
    severity: QualitySeverity = QualitySeverity.WARNING,
    hard_failure: bool = False,
    **evidence: object,
) -> QualityFlag:
    return QualityFlag(
        code=code,
        severity=severity,
        hard_failure=hard_failure,
        message=message,
        evidence=evidence,
    )


def _count_unescaped(text: str, character: str) -> int:
    return sum(
        1
        for index, value in enumerate(text)
        if value == character and (index == 0 or text[index - 1] != "\\")
    )


def _repeated_line_metrics(markdown: str) -> tuple[int, float]:
    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    if not lines:
        return 0, 0.0
    counts = Counter(lines)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated, repeated / len(lines)


def _challenge_phrases(markdown: str) -> tuple[str, ...]:
    folded = markdown.casefold()
    return tuple(phrase for phrase in _CHALLENGE_PHRASES if phrase in folded)


def _hard_context_flags(context: AssessmentContext) -> list[QualityFlag]:
    flags: list[QualityFlag] = []
    declarations = (
        (
            context.wrong_document,
            "wrong_document",
            "Acquired content is not the requested document.",
        ),
        (
            context.truncated,
            "truncated",
            "Source or candidate evidence indicates truncation.",
        ),
        (
            context.suspected_invention,
            "suspected_invention",
            "Candidate evidence may include content not grounded in the source.",
        ),
        (
            context.policy_violation,
            "policy_violation",
            "Candidate production violated the active conversion policy.",
        ),
        (
            context.malware_detected,
            "malware_detected",
            "Input safety evidence identifies malicious active content.",
        ),
    )
    for active, code, message in declarations:
        if active:
            flags.append(
                _flag(
                    code,
                    message,
                    severity=QualitySeverity.ERROR,
                    hard_failure=True,
                )
            )
    if (
        context.expected_units is not None
        and context.covered_units is not None
        and context.covered_units < context.expected_units
    ):
        flags.append(
            _flag(
                "missing_coverage",
                "Requested source units are missing from candidate coverage.",
                severity=QualitySeverity.ERROR,
                hard_failure=True,
                expected_units=context.expected_units,
                covered_units=context.covered_units,
            )
        )
    return flags


def assess_candidate(
    source: SourceDocument,
    candidate: Candidate,
    *,
    context: AssessmentContext | None = None,
    profile: QualityProfile | None = None,
) -> QualityAssessment:
    """Assess one retained candidate without mutating or normalizing it."""

    evidence = context if context is not None else AssessmentContext()
    policy = profile if profile is not None else QualityProfile()
    if candidate.source_sha256 != source.sha256:
        raise ValueError("candidate source identity does not match quality source")
    markdown = candidate.markdown
    stripped = markdown.strip()
    non_whitespace_characters = sum(
        1 for character in markdown if not character.isspace()
    )
    printable_characters = sum(
        1 for character in markdown if character.isprintable() or character.isspace()
    )
    printable_ratio = printable_characters / len(markdown) if markdown else 1.0
    control_characters = sum(
        1
        for character in markdown
        if not character.isprintable() and not character.isspace()
    )
    invisible_count = len(_INVISIBLE_RE.findall(markdown))
    replacement_character_count = markdown.count("\N{REPLACEMENT CHARACTER}")
    repeated_line_count, repeated_line_ratio = _repeated_line_metrics(markdown)
    display_delimiters = markdown.count("$$")
    inline_delimiters = _count_unescaped(markdown.replace("$$", ""), "$")
    challenge_phrases = _challenge_phrases(markdown)
    lossy_transformations = sum(
        1 for transformation in candidate.transformations if transformation.lossy
    )
    affected_units = sum(
        transformation.affected_units or 0
        for transformation in candidate.transformations
    )

    code_fence_count = len(_CODE_FENCE_RE.findall(markdown))
    metrics: dict[str, QualityMetric] = {
        "profile_id": policy.profile_id,
        "source_media_type": source.media_type,
        "source_bytes": len(source.data),
        "character_count": len(markdown),
        "non_whitespace_character_count": non_whitespace_characters,
        "word_count": len(stripped.split()),
        "line_count": len(markdown.splitlines()),
        "heading_count": len(_HEADING_RE.findall(markdown)),
        "link_count": len(_MD_LINK_RE.findall(markdown)),
        "image_count": len(_MD_IMAGE_RE.findall(markdown)),
        "list_item_count": len(_LIST_ITEM_RE.findall(markdown)),
        "table_row_count": len(_TABLE_ROW_RE.findall(markdown)),
        "code_fence_count": code_fence_count,
        "printable_ratio": round(printable_ratio, 6),
        "control_character_count": control_characters,
        "invisible_character_count": invisible_count,
        "replacement_character_count": replacement_character_count,
        "repeated_line_count": repeated_line_count,
        "repeated_line_ratio": round(repeated_line_ratio, 6),
        "lossy_transformation_count": lossy_transformations,
        "transformation_affected_units": affected_units,
        "provenance_tier": candidate.provenance_tier.value,
        "adapter_diagnostic_count": len(candidate.diagnostics),
        "expected_short_document": evidence.expected_short_document,
        "source_mapping_coverage": evidence.source_mapping_coverage,
        "ocr_coverage": evidence.ocr_coverage,
        "ocr_confidence": evidence.ocr_confidence,
        "title_present": bool(
            evidence.title and evidence.title.strip().casefold() not in {"", "untitled"}
        ),
    }
    collisions = set(metrics).intersection(evidence.additional_metrics)
    if collisions:
        raise ValueError(
            "additional quality metrics collide with shared metrics: "
            + ", ".join(sorted(collisions))
        )
    metrics.update(evidence.additional_metrics)

    flags = _hard_context_flags(evidence)
    if not stripped:
        flags.append(
            _flag(
                "structurally_empty",
                "Candidate contains no non-whitespace content.",
                severity=QualitySeverity.ERROR,
                hard_failure=True,
            )
        )
    if (
        policy.thin_character_hint is not None
        and non_whitespace_characters < policy.thin_character_hint
        and not evidence.expected_short_document
    ):
        flags.append(
            _flag(
                "thin",
                "Candidate is shorter than this quality profile's diagnostic hint.",
                severity=(
                    QualitySeverity.ERROR
                    if policy.thin_is_hard_failure
                    else QualitySeverity.WARNING
                ),
                hard_failure=policy.thin_is_hard_failure,
                observed=non_whitespace_characters,
                hint=policy.thin_character_hint,
            )
        )
    if evidence.title is None or evidence.title.strip().casefold() in {"", "untitled"}:
        flags.append(
            _flag(
                "no_title",
                "No meaningful title evidence is available.",
            )
        )
    if display_delimiters % 2 == 1:
        flags.append(
            _flag(
                "latex_unbalanced_display",
                "Display-math delimiters are unbalanced.",
                delimiters=display_delimiters,
            )
        )
    if inline_delimiters % 2 == 1:
        flags.append(
            _flag(
                "latex_unbalanced_inline",
                "Inline-math delimiters are unbalanced.",
                delimiters=inline_delimiters,
            )
        )
    if code_fence_count % 2 == 1:
        flags.append(
            _flag(
                "unbalanced_code_fence",
                "Markdown code-fence delimiters are unbalanced.",
                delimiters=code_fence_count,
            )
        )
    if _SPACED_CAPS_RE.search(markdown):
        flags.append(
            _flag(
                "spaced_caps",
                "Candidate contains a likely spaced-capitals PDF artifact.",
            )
        )
    if _MOJIBAKE_RE.search(markdown):
        flags.append(
            _flag(
                "mojibake",
                "Candidate contains likely character-decoding artifacts.",
            )
        )
    if invisible_count:
        flags.append(
            _flag(
                "invisible_chars",
                "Candidate contains invisible or bidirectional control characters.",
                count=invisible_count,
            )
        )
    if printable_ratio < policy.minimum_printable_ratio:
        flags.append(
            _flag(
                "low_printable_ratio",
                "Candidate contains an unusual proportion of control characters.",
                observed=round(printable_ratio, 6),
                minimum=policy.minimum_printable_ratio,
            )
        )
    if repeated_line_ratio > policy.maximum_repeated_line_ratio:
        flags.append(
            _flag(
                "repeated_line_noise",
                "Repeated lines suggest headers, footers, or extraction noise.",
                observed=round(repeated_line_ratio, 6),
                maximum=policy.maximum_repeated_line_ratio,
            )
        )
    challenge_is_hard = len(challenge_phrases) >= 2 or any(
        phrase in _STRONG_CHALLENGE_PHRASES for phrase in challenge_phrases
    )
    if challenge_is_hard:
        flags.append(
            _flag(
                "challenge_page",
                "Acquired content appears to be a challenge, denial, or login page.",
                severity=QualitySeverity.ERROR,
                hard_failure=True,
                phrases=challenge_phrases,
            )
        )
    elif challenge_phrases:
        flags.append(
            _flag(
                "challenge_indicator",
                "Candidate contains a challenge-like phrase without enough evidence to fail.",
                phrases=challenge_phrases,
            )
        )
    if (
        policy.minimum_source_mapping_coverage is not None
        and evidence.source_mapping_coverage is not None
        and evidence.source_mapping_coverage < policy.minimum_source_mapping_coverage
    ):
        flags.append(
            _flag(
                "low_source_mapping_coverage",
                "Candidate source mapping falls below this profile's requirement.",
                observed=evidence.source_mapping_coverage,
                minimum=policy.minimum_source_mapping_coverage,
            )
        )
    if candidate.provenance_tier is ProvenanceTier.OCR:
        if evidence.ocr_coverage is None or evidence.ocr_confidence is None:
            flags.append(
                _flag(
                    "ocr_evidence_missing",
                    "OCR candidate lacks coverage or confidence evidence.",
                )
            )
        else:
            if evidence.ocr_coverage < policy.minimum_ocr_coverage:
                flags.append(
                    _flag(
                        "low_ocr_coverage",
                        "OCR text coverage falls below this profile's diagnostic threshold.",
                        observed=evidence.ocr_coverage,
                        minimum=policy.minimum_ocr_coverage,
                    )
                )
            if evidence.ocr_confidence < policy.minimum_ocr_confidence:
                flags.append(
                    _flag(
                        "low_ocr_confidence",
                        "OCR confidence falls below this profile's diagnostic threshold.",
                        observed=evidence.ocr_confidence,
                        minimum=policy.minimum_ocr_confidence,
                    )
                )
    flags.extend(evidence.adapter_flags)

    hard_codes = [flag.code for flag in flags if flag.hard_failure]
    usable = not hard_codes
    if hard_codes:
        explanation = "failed: hard quality evidence: " + ", ".join(hard_codes)
    elif flags:
        explanation = "degraded: advisory quality evidence: " + ", ".join(
            flag.code for flag in flags
        )
    else:
        explanation = "ok: no quality flags were triggered by the active profile"
    return QualityAssessment(
        usable=usable,
        score=evidence.soft_score,
        warnings=tuple(flag.message for flag in flags),
        metrics=metrics,
        flags=tuple(flags),
        explanation=explanation,
    )


@dataclass(frozen=True, slots=True)
class DeterministicAssessor:
    """AssessorPort implementation for a fixed request context/profile."""

    context: AssessmentContext = AssessmentContext()
    profile: QualityProfile = QualityProfile()

    def assess(
        self,
        source: SourceDocument,
        candidate: Candidate,
    ) -> QualityAssessment:
        return assess_candidate(
            source,
            candidate,
            context=self.context,
            profile=self.profile,
        )


def quality_to_public(report: QualityAssessment) -> dict[str, object]:
    """Project an internal report to the accepted v1 quality schema."""

    return {
        "schema_version": 1,
        "usable": report.usable,
        "score": report.score,
        "metrics": dict(report.metrics),
        "flags": [
            {
                "code": flag.code,
                "severity": flag.severity.value,
                "hard_failure": flag.hard_failure,
                "message": flag.message,
                "evidence": dict(flag.evidence),
            }
            for flag in report.flags
        ],
        "explanation": report.explanation,
    }
