#!/usr/bin/env python3
"""Heuristic syntactic-hedge and nominalization screen.

This deterministic, stdlib-only tool reports three independent measurements:

* passive-voice ratio: prose sentences containing a ``be``/``get`` form followed
  by a likely past participle, divided by prose sentences;
* hedge density: maintained hedge/weasel phrases per 1,000 prose words; and
* nominalization rate: likely ``-tion/-ment/-ness/-ity/-ance/-ence`` nouns per
  1,000 prose words.

The measurements are review signals, never assertions about writing quality and
never an aggregate score. With ``--baseline FILE``, the tool reports the signed
divergence from the author's accepted-prose rates; it invents no thresholds.

Baseline JSON may be either a prior ``--json`` result from this script or a flat
object containing exactly these numeric rate keys::

    {
      "passive_voice_ratio": 0.12,
      "hedge_density_per_1000_words": 8.5,
      "nominalization_rate_per_1000_words": 21.0
    }

Markdown exclusions are deliberately conservative: fenced code, inline code,
ATX headings, blockquote lines, and text inside matched straight or curly double
quotes are omitted. Single-quoted text is retained because apostrophes make a
reliable context-free distinction impossible.

Known limitations
-----------------
The passive pattern can mistake adjectival/stative complements (``was tired``)
for passives and can miss distant auxiliaries, unlisted irregular participles,
or elliptical constructions. Hedge phrases are context-blind (``rather`` and
``fairly`` are not always hedges). Suffix matching cannot determine whether a
noun is abstract or whether a nominalization is harmful; a small exception list
only reduces common false positives. The tokenizer is Latin-script oriented.

Exit 0 means the screen completed, regardless of the rates. Exit 2 means an
input or baseline could not be read or parsed. Reads a path, or stdin when the
path is omitted or ``-``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from typing import Any

FORMAT_VERSION = 1
TYPE = "syntactic_hedge_screen"

METRIC_ORDER = (
    "passive_voice_ratio",
    "hedge_density_per_1000_words",
    "nominalization_rate_per_1000_words",
)

# Longest-first matching makes multiword phrases atomic and prevents an
# incidental shorter entry from double-counting part of the same span.
HEDGE_PHRASES = (
    "it could be argued",
    "in some sense",
    "to some extent",
    "apparently",
    "arguably",
    "generally",
    "relatively",
    "seemingly",
    "somewhat",
    "typically",
    "appeared",
    "appearing",
    "appears",
    "broadly",
    "fairly",
    "largely",
    "possibly",
    "probably",
    "reportedly",
    "perhaps",
    "likely",
    "maybe",
    "mostly",
    "rather",
    "seemed",
    "seems",
    "seem",
)
HEDGE_TOKEN_SEQUENCES = tuple(
    sorted(
        (tuple(phrase.split()) for phrase in HEDGE_PHRASES),
        key=lambda parts: (-len(parts), parts),
    )
)

BE_GET_FORMS = {
    "am",
    "are",
    "be",
    "been",
    "being",
    "get",
    "gets",
    "getting",
    "got",
    "gotten",
    "is",
    "was",
    "were",
}

# This cannot be exhaustive without a parser/lexicon. It covers common strong
# forms while the suffix fallback handles regular participles.
IRREGULAR_PARTICIPLES = {
    "bought",
    "broken",
    "brought",
    "built",
    "caught",
    "chosen",
    "cut",
    "done",
    "drawn",
    "driven",
    "found",
    "given",
    "grown",
    "heard",
    "held",
    "kept",
    "known",
    "left",
    "lost",
    "made",
    "paid",
    "put",
    "read",
    "said",
    "seen",
    "sent",
    "set",
    "shown",
    "spoken",
    "taken",
    "taught",
    "thought",
    "thrown",
    "told",
    "torn",
    "worn",
    "written",
}

INTERVENING_MODIFIERS = {
    "also",
    "already",
    "apparently",
    "broadly",
    "carefully",
    "commonly",
    "deliberately",
    "even",
    "fully",
    "generally",
    "indeed",
    "just",
    "largely",
    "never",
    "not",
    "often",
    "partially",
    "partly",
    "reportedly",
    "seemingly",
    "sometimes",
    "still",
    "typically",
    "usually",
    "very",
    "widely",
}

# These suffix matches are common concrete/function words rather than useful
# zombie-noun candidates. The list reduces, but cannot eliminate, false positives.
NOMINALIZATION_EXCEPTIONS = {
    "agreement",
    "agreements",
    "apartment",
    "apartments",
    "argument",
    "arguments",
    "attention",
    "basement",
    "basements",
    "business",
    "chance",
    "chances",
    "city",
    "comment",
    "comments",
    "dance",
    "dances",
    "department",
    "departments",
    "development",
    "developments",
    "direction",
    "directions",
    "document",
    "documents",
    "education",
    "educations",
    "element",
    "elements",
    "entrance",
    "entrances",
    "fence",
    "fences",
    "fragment",
    "fragments",
    "france",
    "garment",
    "garments",
    "government",
    "governments",
    "hence",
    "information",
    "instrument",
    "instruments",
    "mention",
    "mentions",
    "moment",
    "moments",
    "monument",
    "monuments",
    "movement",
    "movements",
    "nation",
    "nations",
    "population",
    "populations",
    "position",
    "positions",
    "question",
    "questions",
    "science",
    "sciences",
    "section",
    "sections",
    "sentence",
    "sentences",
    "statement",
    "statements",
    "station",
    "stations",
    "witness",
}

EXCLUSIONS = (
    "fenced code blocks (backticks or tildes)",
    "inline code spans",
    "ATX headings and Markdown blockquote lines",
    "matched straight or curly double-quoted spans",
)

LIMITATIONS = (
    "Passive matching is lexical: adjectival or stative complements such as "
    "'was tired' can be false positives, while distant auxiliaries, unlisted "
    "irregular participles, and elliptical passives can be missed.",
    "Hedge phrase matching is context-blind: words such as 'rather' and "
    "'fairly' are not hedges in every use, and hedges outside the maintained "
    "list are missed.",
    "Nominalization matching uses suffixes plus a small exception list; it "
    "cannot reliably distinguish abstract from concrete nouns or judge whether "
    "a nominalization is useful.",
    "The word tokenizer is Latin-script oriented, so non-Latin prose is under-counted.",
)

WORD_RE = re.compile(r"[A-Za-z]+(?:[\N{RIGHT SINGLE QUOTATION MARK}'-][A-Za-z]+)*")
INITIALISM_RE = re.compile(r"(?:[A-Za-z]\.){2,}")
FENCE_OPEN_RE = re.compile(r"^\s{0,3}(?P<marker>`{3,}|~{3,})")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:\s+|$)")
BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>")
INLINE_CODE_RE = re.compile(r"`+[^`\n]*`+")
STRAIGHT_QUOTE_RE = re.compile(r'"[^"\n]*"')
CURLY_QUOTE_RE = re.compile(
    r"\N{LEFT DOUBLE QUOTATION MARK}[^\N{RIGHT DOUBLE QUOTATION MARK}\n]*\N{RIGHT DOUBLE QUOTATION MARK}"
)
LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\([^\s)]+(?:\s+[^)]*)?\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
NOMINALIZATION_RE = re.compile(r"(?:tion|ment|ness|ity|ance|ence)s?$")


def read_text(path: str | None) -> str:
    """Read UTF-8 text from ``path`` or stdin, normalizing I/O failures."""
    if path is None or path == "-":
        try:
            return sys.stdin.read()
        except OSError as exc:
            raise ValueError(f"cannot read stdin: {exc}") from exc
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read '{path}': {exc}") from exc


def extract_prose(text: str) -> tuple[str, list[str]]:
    """Return analyzable prose after documented Markdown/quotation exclusions."""
    kept: list[str] = []
    fence_char: str | None = None
    fence_length = 0

    for line in text.splitlines():
        if fence_char is not None:
            close_re = re.compile(
                rf"^\s{{0,3}}{re.escape(fence_char)}{{{fence_length},}}\s*$"
            )
            if close_re.match(line):
                fence_char = None
                fence_length = 0
            kept.append("")
            continue

        fence = FENCE_OPEN_RE.match(line)
        if fence:
            marker = fence.group("marker")
            fence_char = marker[0]
            fence_length = len(marker)
            kept.append("")
            continue
        if HEADING_RE.match(line) or BLOCKQUOTE_RE.match(line):
            kept.append("")
            continue
        kept.append(line)

    prose = "\n".join(kept)
    prose = IMAGE_RE.sub(" ", prose)
    prose = LINK_RE.sub(r"\1", prose)
    prose = INLINE_CODE_RE.sub(" ", prose)
    prose = CURLY_QUOTE_RE.sub(" ", prose)
    prose = STRAIGHT_QUOTE_RE.sub(" ", prose)

    warnings = []
    if fence_char is not None:
        warnings.append(
            "unterminated fenced code block at EOF; the remainder was excluded"
        )
    return prose, warnings


def tokens_in(text: str) -> list[str]:
    """Return normalized Latin-script word tokens."""
    normalized = INITIALISM_RE.sub(lambda match: match.group().replace(".", ""), text)
    return [token.lower() for token in WORD_RE.findall(normalized)]


def sentences_in(text: str) -> list[str]:
    """Split prose into punctuation-delimited sentences within paragraphs."""
    sentences: list[str] = []
    for paragraph in re.split(r"\n\s*\n+", text):
        paragraph = INITIALISM_RE.sub(
            lambda match: match.group().replace(".", ""), paragraph
        )
        for candidate in re.split(r"(?<=[.!?])\s+", paragraph):
            candidate = candidate.strip()
            if tokens_in(candidate):
                sentences.append(candidate)
    return sentences


def _is_modifier(token: str) -> bool:
    return token in INTERVENING_MODIFIERS or token.endswith("ly")


def _is_participle(token: str) -> bool:
    if token in IRREGULAR_PARTICIPLES:
        return True
    return len(token) > 4 and (token.endswith("ed") or token.endswith("en"))


def passive_matches(sentence: str) -> list[str]:
    """Return lexical passive-like spans found in one sentence."""
    tokens = tokens_in(sentence)
    matches: list[str] = []
    for index, token in enumerate(tokens):
        if token not in BE_GET_FORMS:
            continue
        cursor = index + 1
        while cursor < len(tokens) and _is_modifier(tokens[cursor]):
            cursor += 1
        if cursor < len(tokens) and _is_participle(tokens[cursor]):
            matches.append(" ".join(tokens[index : cursor + 1]))
    return matches


def hedge_matches(tokens: list[str]) -> list[str]:
    """Return non-overlapping maintained hedge phrases with token boundaries."""
    matches: list[str] = []
    index = 0
    while index < len(tokens):
        for phrase in HEDGE_TOKEN_SEQUENCES:
            width = len(phrase)
            if tuple(tokens[index : index + width]) == phrase:
                matches.append(" ".join(phrase))
                index += width
                break
        else:
            index += 1
    return matches


def nominalization_matches(tokens: list[str]) -> list[str]:
    """Return suffix-based nominalization candidates.

    A hyphenated compound is split on ``-`` and checked base-by-base so that a
    compound resolves to its (already-excepted) base: ``cross-section`` behaves
    like ``section`` and is not flagged, while ``implementation`` still is.
    """
    candidates: list[str] = []
    for token in tokens:
        parts = token.split("-")
        if any(
            part not in NOMINALIZATION_EXCEPTIONS and NOMINALIZATION_RE.search(part)
            for part in parts
        ):
            candidates.append(token)
    return candidates


def _per_1000(count: int, words: int) -> float:
    return round((count / words) * 1000.0, 4)


def analyze(text: str) -> dict[str, Any]:
    """Analyze text and return the raw, separate metric record."""
    prose, warnings = extract_prose(text)
    tokens = tokens_in(prose)
    sentences = sentences_in(prose)
    if not tokens:
        raise ValueError("input contains no prose words after exclusions")

    passive_by_sentence = [passive_matches(sentence) for sentence in sentences]
    passive_spans = [span for matches in passive_by_sentence for span in matches]
    passive_sentence_count = sum(bool(matches) for matches in passive_by_sentence)
    hedges = hedge_matches(tokens)
    nominalizations = nominalization_matches(tokens)

    metrics = {
        "passive_voice_ratio": {
            "count": passive_sentence_count,
            "match_count": len(passive_spans),
            "denominator_sentences": len(sentences),
            "rate": round(passive_sentence_count / len(sentences), 4),
            "unit": "proportion_of_sentences",
        },
        "hedge_density_per_1000_words": {
            "count": len(hedges),
            "denominator_words": len(tokens),
            "rate": _per_1000(len(hedges), len(tokens)),
            "unit": "matches_per_1000_words",
        },
        "nominalization_rate_per_1000_words": {
            "count": len(nominalizations),
            "denominator_words": len(tokens),
            "rate": _per_1000(len(nominalizations), len(tokens)),
            "unit": "candidates_per_1000_words",
        },
    }

    return {
        "counts": {"words": len(tokens), "sentences": len(sentences)},
        "metrics": metrics,
        "matches": {
            "passive_voice": passive_spans,
            "hedges": hedges,
            "nominalizations": nominalizations,
        },
        "warnings": warnings,
    }


def _rate_value(name: str, value: Any) -> float:
    """Validate one baseline rate without accepting bools or non-finite values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"baseline rate {name!r} must be numeric")
    rate = float(value)
    if not math.isfinite(rate):
        raise ValueError(f"baseline rate {name!r} must be finite")
    if rate < 0:
        raise ValueError(f"baseline rate {name!r} must not be negative")
    if name == "passive_voice_ratio" and rate > 1:
        raise ValueError("baseline passive_voice_ratio must be between 0 and 1")
    return rate


def baseline_rates(data: Any) -> dict[str, float]:
    """Extract and validate rates from a flat baseline or prior JSON result."""
    if not isinstance(data, dict):
        raise ValueError("baseline JSON must be an object")

    if "metrics" in data:
        metrics = data["metrics"]
        if not isinstance(metrics, dict):
            raise ValueError("baseline 'metrics' must be an object")
        unknown = sorted(set(metrics) - set(METRIC_ORDER))
        missing = sorted(set(METRIC_ORDER) - set(metrics))
        if unknown:
            raise ValueError(f"baseline has unknown metric(s): {', '.join(unknown)}")
        if missing:
            raise ValueError(f"baseline is missing metric(s): {', '.join(missing)}")
        rates: dict[str, float] = {}
        for name in METRIC_ORDER:
            entry = metrics[name]
            if not isinstance(entry, dict) or "rate" not in entry:
                raise ValueError(f"baseline metric {name!r} must contain a rate")
            rates[name] = _rate_value(name, entry["rate"])
        return rates

    unknown = sorted(set(data) - set(METRIC_ORDER))
    missing = sorted(set(METRIC_ORDER) - set(data))
    if unknown:
        raise ValueError(f"baseline has unknown rate(s): {', '.join(unknown)}")
    if missing:
        raise ValueError(f"baseline is missing rate(s): {', '.join(missing)}")
    return {name: _rate_value(name, data[name]) for name in METRIC_ORDER}


def read_baseline(path: str) -> dict[str, float]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read baseline '{path}': {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"baseline JSON is malformed: {exc}") from exc
    return baseline_rates(data)


def divergence(
    metrics: dict[str, dict[str, Any]], baseline: dict[str, float]
) -> dict[str, dict[str, Any]]:
    """Return per-metric signed deltas, with no threshold or aggregate."""
    result: dict[str, dict[str, Any]] = {}
    for name in METRIC_ORDER:
        draft_rate = float(metrics[name]["rate"])
        base_rate = baseline[name]
        delta = round(draft_rate - base_rate, 4)
        result[name] = {
            "baseline_rate": base_rate,
            "draft_rate": draft_rate,
            "delta": delta,
            "direction": "higher" if delta > 0 else "lower" if delta < 0 else "same",
        }
    return result


def build_record(
    analysis: dict[str, Any], path: str | None, baseline_path: str | None = None
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": TYPE,
        "format_version": FORMAT_VERSION,
        "path": None if path in (None, "-") else path,
        "advisory": (
            "Review signal only: heuristic, non-blocking, and never an aggregate score."
        ),
        "counts": analysis["counts"],
        "metrics": analysis["metrics"],
        "matches": analysis["matches"],
        "exclusions": list(EXCLUSIONS),
        "limitations": list(LIMITATIONS),
        "warnings": analysis["warnings"],
    }
    if baseline_path is not None:
        rates = read_baseline(baseline_path)
        record["baseline"] = {"path": baseline_path, "rates": rates}
        record["divergence"] = divergence(analysis["metrics"], rates)
    return record


def render_human(record: dict[str, Any]) -> str:
    counts = record["counts"]
    metrics = record["metrics"]
    passive = metrics["passive_voice_ratio"]
    hedge = metrics["hedge_density_per_1000_words"]
    nominal = metrics["nominalization_rate_per_1000_words"]

    lines = [
        "SYNTACTIC HEDGE SCREEN — REVIEW ONLY; NO AGGREGATE SCORE",
        f"Prose counted: {counts['words']} words, {counts['sentences']} sentences",
        (
            "passive voice ratio                  "
            f"{passive['rate'] * 100:.2f}% "
            f"({passive['count']}/{passive['denominator_sentences']} sentences; "
            f"{passive['match_count']} lexical matches)"
        ),
        (
            "hedge density                        "
            f"{hedge['rate']:.2f} per 1,000 words ({hedge['count']} matches)"
        ),
        (
            "nominalization rate                  "
            f"{nominal['rate']:.2f} per 1,000 words ({nominal['count']} candidates)"
        ),
    ]

    if "divergence" in record:
        lines.append("Divergence from accepted-prose baseline (no thresholds):")
        for name in METRIC_ORDER:
            item = record["divergence"][name]
            lines.append(
                f"  {name}: baseline {item['baseline_rate']:.4f}, "
                f"draft {item['draft_rate']:.4f}, delta {item['delta']:+.4f} "
                f"({item['direction']})"
            )

    lines.append("Excluded: " + "; ".join(record["exclusions"]) + ".")
    lines.append("Heuristic limits:")
    lines.extend(f"  - {item}" for item in record["limitations"])
    lines.extend(f"Warning: {item}" for item in record["warnings"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Screen passive voice, hedge density, and nominalizations as "
            "separate advisory metrics; never an aggregate score."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Markdown/prose file to screen (default: stdin; '-' also means stdin)",
    )
    parser.add_argument(
        "--baseline",
        metavar="FILE",
        help="accepted-prose rate JSON used only for per-metric divergence",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the stable JSON record"
    )
    args = parser.parse_args(argv)

    try:
        text = read_text(args.path)
        analysis = analyze(text)
        record = build_record(analysis, args.path, args.baseline)
    except ValueError as exc:
        print(f"hedges: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(render_human(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
