"""Deterministic maintenance fitness for the authored guidance corpus.

Strict corpus validation remains in :mod:`scripts.knowledge.corpus`.  This module keeps
mechanically provable failures separate from advisory freshness signals and heuristic review
candidates; it never grades prose truth or produces a universal quality score.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from .corpus import Finding, KnowledgeRecord, scan_corpus, scan_source_register, validate_corpus

Classification = Literal["blocking", "advisory", "candidate"]
REPORT_SCHEMA_VERSION = 1
MARKDOWN = MarkdownIt("commonmark").enable("table")
ABSOLUTE_LANGUAGE = re.compile(r"\b(?:must(?:\s+not)?|always|never)\b", re.IGNORECASE)
EPISTEMIC_SCOPE = re.compile(
    r"\b(?:standard/fact|project default|house preference|heuristic|example|legal note|"
    r"invariant|contract|applicable standard|explicit scope)\b",
    re.IGNORECASE,
)
NEGATIVE_NORMATIVE = re.compile(r"\b(?:must not|should not|do not|never|cannot)\b", re.IGNORECASE)
POSITIVE_NORMATIVE = re.compile(r"\b(?:must|should|always|need to)\b", re.IGNORECASE)
OWNERSHIP_HEADER = ("Topic", "Canonical owner")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
WORD = re.compile(r"[a-z][a-z0-9-]{2,}")
STOPWORDS = {
    "and",
    "are",
    "but",
    "can",
    "for",
    "from",
    "has",
    "have",
    "into",
    "its",
    "not",
    "only",
    "should",
    "that",
    "the",
    "their",
    "then",
    "this",
    "when",
    "where",
    "with",
    "must",
    "always",
    "never",
}


@dataclass(frozen=True)
class GuidanceFitnessPolicy:
    version: int = 1
    source_max_age_days: int = 365
    duplicate_min_characters: int = 160
    conflict_min_tokens: int = 8
    conflict_similarity: float = 0.82
    max_text_blocks: int = 4_096
    max_body_bytes: int = 2_000_000


DEFAULT_POLICY = GuidanceFitnessPolicy()


@dataclass(frozen=True)
class GuidanceFinding:
    code: str
    classification: Classification
    path: str
    line: int
    message: str
    evidence: str
    proof_limit: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GuidanceFitnessReport:
    schema_version: int
    as_of: str
    policy: GuidanceFitnessPolicy
    findings: tuple[GuidanceFinding, ...]

    @property
    def blocking(self) -> tuple[GuidanceFinding, ...]:
        return tuple(item for item in self.findings if item.classification == "blocking")

    @property
    def advisories(self) -> tuple[GuidanceFinding, ...]:
        return tuple(item for item in self.findings if item.classification == "advisory")

    @property
    def candidates(self) -> tuple[GuidanceFinding, ...]:
        return tuple(item for item in self.findings if item.classification == "candidate")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "as_of": self.as_of,
            "policy": asdict(self.policy),
            "findings": [item.to_dict() for item in self.findings],
            "counts": {
                "blocking": len(self.blocking),
                "advisory": len(self.advisories),
                "candidate": len(self.candidates),
            },
            "limitations": [
                "blocking findings establish only the named deterministic artifact contract",
                "advisories are maintenance triggers, not proof that a source or claim is stale",
                "candidates are lexical review prompts, not judgments of prose truth or conflict",
            ],
        }


@dataclass(frozen=True)
class _TextBlock:
    path: str
    line: int
    text: str


@dataclass(frozen=True)
class _Body:
    record: KnowledgeRecord
    path: Path
    text: str
    line_offset: int
    tokens: tuple[Any, ...]
    blocks: tuple[_TextBlock, ...]


def evaluate_guidance_fitness(
    root: Path,
    *,
    as_of: date,
    changed_ids: tuple[str, ...] = (),
    policy: GuidanceFitnessPolicy | None = None,
) -> GuidanceFitnessReport:
    """Evaluate bounded guidance-maintenance signals without changing corpus pass/fail semantics."""

    root = root.resolve()
    policy = policy or DEFAULT_POLICY
    _validate_policy(policy)
    records, _corpus_findings = scan_corpus(root)
    findings = [_strict_finding(item) for item in validate_corpus(root)]
    source_path = root / "references" / "SOURCES.md"
    if source_path.is_file():
        sources, _source_findings = scan_source_register(source_path, records)
    else:
        sources = ()

    loaded_bodies: list[_Body] = []
    for record in records:
        path = root / record.path
        try:
            size = path.stat().st_size
        except OSError as exc:
            findings.append(
                _finding(
                    "guidance.structure.body-unreadable",
                    "blocking",
                    record.path,
                    1,
                    f"knowledge body cannot be inspected: {exc}",
                    "filesystem read failed",
                    "This establishes inspection unavailability, not a prose defect.",
                )
            )
            continue
        if size > policy.max_body_bytes:
            findings.append(
                _finding(
                    "guidance.structure.body-too-large",
                    "blocking",
                    record.path,
                    1,
                    f"knowledge body is {size} bytes; limit is {policy.max_body_bytes}",
                    "configured bounded-read limit",
                    "This establishes incomplete inspection, not a prose defect.",
                )
            )
            continue
        try:
            loaded_bodies.append(_load_body(root, record))
        except UnicodeDecodeError:
            findings.append(
                _finding(
                    "guidance.structure.body-encoding",
                    "blocking",
                    record.path,
                    1,
                    "knowledge body is not valid UTF-8",
                    "full bounded body decode failed",
                    "This establishes an encoding failure, not a semantic prose defect.",
                )
            )
    bodies = tuple(loaded_bodies)
    for body in bodies:
        findings.extend(_structure_findings(root, body))
    findings.extend(_ownership_findings(root, records, bodies))
    findings.extend(_source_fitness(sources, as_of, set(changed_ids), policy))

    blocks = tuple(block for body in bodies for block in body.blocks)
    if len(blocks) > policy.max_text_blocks:
        findings.append(
            _finding(
                "guidance.analysis-truncated",
                "advisory",
                "knowledge",
                1,
                f"text-block analysis stopped at {policy.max_text_blocks} of {len(blocks)} blocks",
                "configured text-block bound was reached",
                "Unexamined blocks may contain additional candidates.",
            )
        )
        blocks = blocks[: policy.max_text_blocks]
    findings.extend(_normative_candidates(blocks))
    findings.extend(_duplication_candidates(blocks, policy))
    findings.extend(_conflict_candidates(blocks, policy))
    ordered = tuple(
        sorted(
            set(findings),
            key=lambda item: (
                {"blocking": 0, "advisory": 1, "candidate": 2}[item.classification],
                item.path,
                item.line,
                item.code,
                item.message,
            ),
        )
    )
    return GuidanceFitnessReport(REPORT_SCHEMA_VERSION, as_of.isoformat(), policy, ordered)


def _load_body(root: Path, record: KnowledgeRecord) -> _Body:
    path = root / record.path
    text = path.read_text(encoding="utf-8")
    closing = text.find("\n---\n", 4)
    body = text[closing + 5 :] if closing >= 0 else text
    offset = text[: closing + 5].count("\n") if closing >= 0 else 0
    tokens = tuple(MARKDOWN.parse(body))
    blocks: list[_TextBlock] = []
    for index, token in enumerate(tokens):
        if token.type != "inline" or token.map is None or index == 0:
            continue
        if tokens[index - 1].type != "paragraph_open":
            continue
        value = " ".join(
            child.content.strip()
            for child in token.children or ()
            if child.type in {"text", "softbreak", "hardbreak"} and child.content.strip()
        )
        if value:
            blocks.append(_TextBlock(record.path, offset + token.map[0] + 1, value))
    return _Body(record, path, body, offset, tokens, tuple(blocks))


def _structure_findings(root: Path, body: _Body) -> tuple[GuidanceFinding, ...]:
    findings: list[GuidanceFinding] = []
    headings = [
        token for token in body.tokens if token.type == "heading_open" and token.tag == "h1"
    ]
    if len(headings) != 1:
        findings.append(
            _finding(
                "guidance.structure.h1-count",
                "blocking",
                body.record.path,
                body.line_offset + 1,
                f"expected exactly one H1, found {len(headings)}",
                "Markdown heading tokens",
                "This checks heading cardinality, not whether the title is semantically good.",
            )
        )
    conventions = (
        ("guidance.structure.purpose-missing", r"^>\s+\*\*Purpose:\*\*", "Purpose"),
        (
            "guidance.structure.read-when-missing",
            r"^>\s+\*\*Read this when:\*\*",
            "Read this when",
        ),
        ("guidance.structure.meta-question-missing", r"^##\s+Meta-Question\s*$", "Meta-Question"),
    )
    for code, pattern, label in conventions:
        if not re.search(pattern, body.text, re.MULTILINE):
            findings.append(
                _finding(
                    code,
                    "advisory",
                    body.record.path,
                    body.line_offset + 1,
                    f"authoring convention {label!r} is absent",
                    f"no Markdown block matched {pattern!r}",
                    "The convention is advisory until the corpus adopts it without exceptions.",
                )
            )
    for token in body.tokens:
        if token.type != "inline":
            continue
        for child in token.children or ():
            if child.type != "link_open":
                continue
            destination = child.attrGet("href")
            if not destination:
                continue
            split = urlsplit(destination)
            if split.scheme or split.netloc or not split.path:
                continue
            target = (body.path.parent / unquote(split.path)).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                exists = False
            else:
                exists = target.is_file()
            if not exists:
                line = body.line_offset + (token.map[0] if token.map else 0) + 1
                findings.append(
                    _finding(
                        "guidance.structure.link-missing",
                        "blocking",
                        body.record.path,
                        line,
                        f"relative link target does not resolve: {destination}",
                        f"resolved target {target}",
                        "This checks repository containment and existence, not link meaning.",
                    )
                )
    return tuple(findings)


def _ownership_findings(
    root: Path, records: tuple[KnowledgeRecord, ...], bodies: tuple[_Body, ...]
) -> tuple[GuidanceFinding, ...]:
    selected = next((body for body in bodies if body.record.id == "epistemic-contract"), None)
    if selected is None:
        return (
            _finding(
                "guidance.ownership.catalog-missing",
                "blocking",
                "knowledge/epistemic-contract.md",
                1,
                "canonical topic ownership catalog is unavailable",
                "no epistemic-contract knowledge record was scanned",
                "This checks the adopted catalog location, not whether the ownership map is complete.",
            ),
        )
    lines = selected.text.splitlines()
    header = next((i for i, line in enumerate(lines) if _cells(line) == OWNERSHIP_HEADER), None)
    if header is None:
        return (
            _finding(
                "guidance.ownership.table-missing",
                "blocking",
                selected.record.path,
                selected.line_offset + 1,
                "canonical topic ownership table is missing",
                "no table with Topic and Canonical owner columns was found",
                "This checks table presence, not semantic completeness.",
            ),
        )
    known_paths = {record.path for record in records}
    observed: set[str] = set()
    findings: list[GuidanceFinding] = []
    for index, line in enumerate(lines[header + 2 :], header + 3):
        if not line.strip().startswith("|"):
            break
        cells = _cells(line)
        if len(cells) != 2 or not all(cells):
            findings.append(
                _finding(
                    "guidance.ownership.row-invalid",
                    "blocking",
                    selected.record.path,
                    selected.line_offset + index,
                    "ownership row must contain a topic and at least one canonical-owner link",
                    line.strip(),
                    "This checks row shape, not whether the chosen owner is correct.",
                )
            )
            continue
        topic, owner = cells
        normalized = re.sub(r"\s+", " ", topic).strip().casefold()
        if normalized in observed:
            findings.append(
                _finding(
                    "guidance.ownership.topic-duplicate",
                    "blocking",
                    selected.record.path,
                    selected.line_offset + index,
                    f"canonical topic appears more than once: {topic}",
                    normalized,
                    "Textual uniqueness does not prove that two differently named topics do not overlap.",
                )
            )
        observed.add(normalized)
        destinations = MARKDOWN_LINK.findall(owner)
        if not destinations:
            findings.append(
                _finding(
                    "guidance.ownership.owner-missing",
                    "blocking",
                    selected.record.path,
                    selected.line_offset + index,
                    f"canonical topic has no linked owner: {topic}",
                    owner,
                    "A link proves only an explicit target, not effective ownership.",
                )
            )
        for destination in destinations:
            split = urlsplit(destination)
            target = (selected.path.parent / unquote(split.path)).resolve()
            try:
                relative = target.relative_to(root).as_posix()
            except ValueError:
                relative = ""
            if relative not in known_paths:
                findings.append(
                    _finding(
                        "guidance.ownership.target-missing",
                        "blocking",
                        selected.record.path,
                        selected.line_offset + index,
                        f"canonical owner is not a routed knowledge record: {destination}",
                        relative or str(target),
                        "Target existence and routing do not prove the owner text is complete or correct.",
                    )
                )
    return tuple(findings)


def _source_fitness(sources, as_of: date, changed_ids: set[str], policy: GuidanceFitnessPolicy):
    findings: list[GuidanceFinding] = []
    for source in sources:
        try:
            accessed = date.fromisoformat(source.accessed)
        except ValueError:
            continue
        if accessed > as_of:
            findings.append(
                _finding(
                    "guidance.source.accessed-future",
                    "blocking",
                    "references/SOURCES.md",
                    source.line,
                    f"access date {source.accessed} is after evaluation date {as_of.isoformat()}",
                    source.url,
                    "This establishes inconsistent dates, not source truth.",
                )
            )
        age = (as_of - accessed).days
        if age > policy.source_max_age_days:
            findings.append(
                _finding(
                    "guidance.source.review-due",
                    "advisory",
                    "references/SOURCES.md",
                    source.line,
                    f"source review age {age} days exceeds policy {policy.source_max_age_days}",
                    f"{source.url} accessed {source.accessed}; trigger: {source.reverify_when}",
                    "Age is a review trigger, not proof that the source or synthesized claim changed.",
                )
            )
        if source.status != "verified":
            findings.append(
                _finding(
                    "guidance.source.status-limited",
                    "advisory",
                    "references/SOURCES.md",
                    source.line,
                    f"source status limits evidence: {source.status}",
                    f"{source.url}; informs {', '.join(source.informs)}",
                    "Status records review access, not whether any synthesized claim is correct.",
                )
            )
        changed = sorted(changed_ids.intersection(source.informs))
        if changed:
            findings.append(
                _finding(
                    "guidance.source.changed-owner-review",
                    "advisory",
                    "references/SOURCES.md",
                    source.line,
                    f"changed knowledge owner may activate source review: {', '.join(changed)}",
                    source.reverify_when,
                    "A changed owner is a prompt to inspect the event-based trigger, not proof review is due.",
                )
            )
    return tuple(findings)


def _normative_candidates(blocks: tuple[_TextBlock, ...]) -> tuple[GuidanceFinding, ...]:
    output = []
    for block in blocks:
        matched = ABSOLUTE_LANGUAGE.search(block.text)
        if matched is None or EPISTEMIC_SCOPE.search(block.text):
            continue
        output.append(
            _finding(
                "guidance.normative.scope-candidate",
                "candidate",
                block.path,
                block.line,
                "absolute normative language has no visible label or scope in the same block",
                matched.group(0),
                "Block-local lexical evidence cannot determine authority, applicability, or correctness.",
            )
        )
    return tuple(output)


def _duplication_candidates(
    blocks: tuple[_TextBlock, ...], policy: GuidanceFitnessPolicy
) -> tuple[GuidanceFinding, ...]:
    grouped: dict[str, list[_TextBlock]] = {}
    for block in blocks:
        normalized = _normalize(block.text)
        if len(normalized) >= policy.duplicate_min_characters:
            grouped.setdefault(normalized, []).append(block)
    output = []
    for normalized, matches in grouped.items():
        locations = sorted({(item.path, item.line) for item in matches})
        if len({path for path, _line in locations}) < 2:
            continue
        first = matches[0]
        output.append(
            _finding(
                "guidance.duplication.exact-candidate",
                "candidate",
                first.path,
                first.line,
                "substantive normalized block is duplicated across knowledge owners",
                "; ".join(f"{path}:{line}" for path, line in locations),
                "Exact text duplication does not prove duplicated authority or that reuse is harmful.",
            )
        )
    return tuple(output)


def _conflict_candidates(
    blocks: tuple[_TextBlock, ...], policy: GuidanceFitnessPolicy
) -> tuple[GuidanceFinding, ...]:
    scoped = []
    for block in blocks:
        negative = bool(NEGATIVE_NORMATIVE.search(block.text))
        positive = bool(POSITIVE_NORMATIVE.search(block.text)) and not negative
        tokens = _subject_tokens(block.text)
        if (negative or positive) and len(tokens) >= policy.conflict_min_tokens:
            scoped.append((block, negative, tokens))
    output = []
    for index, (left, left_negative, left_tokens) in enumerate(scoped):
        for right, right_negative, right_tokens in scoped[index + 1 :]:
            if left.path == right.path or left_negative == right_negative:
                continue
            similarity = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
            if similarity < policy.conflict_similarity:
                continue
            output.append(
                _finding(
                    "guidance.conflict.polarity-candidate",
                    "candidate",
                    left.path,
                    left.line,
                    "lexically similar normative blocks use opposite polarity",
                    f"{right.path}:{right.line}; token_jaccard={similarity:.3f}",
                    "Lexical similarity and polarity do not establish shared scope or a real contradiction.",
                )
            )
    return tuple(output)


def _normalize(text: str) -> str:
    text = re.sub(r"https?://\S+", "<url>", text.casefold())
    text = re.sub(r"[`*_~\[\](){}<>|#]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _subject_tokens(text: str) -> frozenset[str]:
    return frozenset(word for word in WORD.findall(_normalize(text)) if word not in STOPWORDS)


def _cells(line: str) -> tuple[str, ...]:
    return tuple(cell.strip() for cell in line.strip().strip("|").split("|"))


def _validate_policy(policy: GuidanceFitnessPolicy) -> None:
    if policy.version != 1:
        raise ValueError(f"unsupported guidance fitness policy version: {policy.version}")
    if (
        policy.source_max_age_days < 1
        or policy.duplicate_min_characters < 1
        or policy.conflict_min_tokens < 1
        or not 0 < policy.conflict_similarity <= 1
        or policy.max_text_blocks < 1
        or policy.max_body_bytes < 1
    ):
        raise ValueError("guidance fitness policy bounds must be positive and similarity <= 1")


def _strict_finding(finding: Finding) -> GuidanceFinding:
    match = re.search(r"\bline (\d+):", finding.message)
    return _finding(
        finding.code,
        "blocking",
        finding.path,
        int(match.group(1)) if match else 1,
        finding.message,
        "strict corpus/source validator finding",
        "This preserves the existing deterministic validator claim and does not grade prose truth.",
    )


def _finding(
    code: str,
    classification: Classification,
    path: str,
    line: int,
    message: str,
    evidence: str,
    proof_limit: str,
) -> GuidanceFinding:
    return GuidanceFinding(code, classification, path, line, message, evidence, proof_limit)
