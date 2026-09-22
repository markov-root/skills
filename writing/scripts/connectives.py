#!/usr/bin/env python3
"""Heuristic connective and AI-transition overuse screen.

This deterministic, stdlib-only tool reports two independent measurements:

* connective density: maintained transition/connective phrases per 1,000 prose
  words; and
* sentence-initial connective ratio: prose sentences that open with one of the
  maintained phrases, divided by prose sentences.

The maintained list covers conspicuous additive, consequential, contrastive,
summative, and framing transitions often overused in model-written prose. It is
defined in ``CONNECTIVE_PHRASES`` below and includes multiword phrases such as
``in addition``, ``it's worth noting``, ``on the other hand``, and
``in conclusion``. Longest-first token matching makes each occurrence atomic
and preserves word boundaries (for example, ``thus`` does not match
``thusly``).

The measurements are review signals, never assertions about authorship or
writing quality and never an aggregate score. With ``--baseline FILE``, the
tool reports signed divergence from the author's accepted-prose rates; it
invents no thresholds.

Baseline JSON may be either a prior ``--json`` result from this script or a flat
object containing exactly these numeric rate keys::

    {
      "connective_density_per_1000_words": 8.5,
      "sentence_initial_connective_ratio": 0.12
    }

Markdown exclusions mirror the sibling syntactic screen: fenced code, inline
code, ATX headings, blockquote lines, and text inside matched straight or curly
double quotes are omitted. Single-quoted text is retained because apostrophes
make a reliable context-free distinction impossible.

Known limitations
-----------------
Connectives are legitimate rhetorical tools and no listed phrase is an AI tell
in isolation. Phrase matching is context-blind and misses unlisted or
paraphrased transitions. Sentence splitting is punctuation-based, so unusual
abbreviations or formatting can change the sentence-initial denominator. The
tokenizer is Latin-script oriented.

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
from collections import Counter
from typing import Any

FORMAT_VERSION = 1
TYPE = "connective_overuse_screen"

METRIC_ORDER = (
    "connective_density_per_1000_words",
    "sentence_initial_connective_ratio",
)

# Maintained, reviewable vocabulary. Longest-first token sequences prevent
# overlapping phrases from being counted twice and make phrase boundaries
# explicit rather than relying on substring searches.
CONNECTIVE_PHRASES = (
    "it's worth noting",
    "it is worth noting",
    "on the other hand",
    "in other words",
    "in conclusion",
    "to summarize",
    "in addition",
    "as such",
    "that said",
    "additionally",
    "consequently",
    "furthermore",
    "importantly",
    "nevertheless",
    "nonetheless",
    "specifically",
    "conversely",
    "meanwhile",
    "moreover",
    "therefore",
    "ultimately",
    "however",
    "notably",
    "similarly",
    "hence",
    "indeed",
    "overall",
    "thus",
)
CONNECTIVE_TOKEN_SEQUENCES = tuple(
    sorted(
        (tuple(phrase.split()) for phrase in CONNECTIVE_PHRASES),
        key=lambda parts: (-len(parts), parts),
    )
)

EXCLUSIONS = (
    "fenced code blocks (backticks or tildes)",
    "inline code spans",
    "ATX headings and Markdown blockquote lines",
    "matched straight or curly double-quoted spans",
)

LIMITATIONS = (
    "Connectives are legitimate rhetorical tools; a listed phrase is not an "
    "AI or quality tell without context.",
    "Phrase matching is context-blind and limited to the maintained list, so "
    "it can flag appropriate transitions and miss unlisted or paraphrased ones.",
    "Sentence splitting is punctuation-based; abbreviations and unusual "
    "formatting can change the sentence-initial denominator.",
    "The word tokenizer is Latin-script oriented, so non-Latin prose is under-counted.",
)

WORD_RE = re.compile(r"[A-Za-z]+(?:[\N{RIGHT SINGLE QUOTATION MARK}'-][A-Za-z]+)*")
INITIALISM_RE = re.compile(r"(?:[A-Za-z]\.){2,}")
NONTERMINAL_ABBREVIATION_RE = re.compile(
    r"\b(?:mr|mrs|ms|dr|prof|sr|jr|st|mt|vs)\.",
    re.IGNORECASE,
)
# Reference-label abbreviations (No., Fig., fig.) that precede a number or a
# single-letter label — mirror openers.py so they do not cause false sentence
# splits (e.g. "No. 7 failed. In addition." stays two sentences).
REFERENCE_ABBREVIATION_RE = re.compile(
    r"\b(?:fig|no)\.",
    re.IGNORECASE,
)
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


def read_text(path: str | None) -> str:
    """Read UTF-8 text from ``path`` or stdin, normalizing I/O failures."""
    if path is None or path == "-":
        try:
            return sys.stdin.read()
        except (OSError, UnicodeError) as exc:
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
    return [
        token.lower().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
        for token in WORD_RE.findall(normalized)
    ]


def sentences_in(text: str) -> list[str]:
    """Split prose into punctuation-delimited sentences within paragraphs."""
    sentences: list[str] = []
    for paragraph in re.split(r"\n\s*\n+", text):
        paragraph = INITIALISM_RE.sub(
            lambda match: match.group().replace(".", ""), paragraph
        )
        paragraph = NONTERMINAL_ABBREVIATION_RE.sub(
            lambda match: match.group()[:-1], paragraph
        )
        # Reference labels: drop the dot only when "No."/"Fig." is followed by a
        # number or single-letter label (so "No. 7 failed." is one clause but
        # "No. It failed." still splits). Mirrors openers.py:296-298.
        paragraph = REFERENCE_ABBREVIATION_RE.sub(
            lambda match: match.group()[:-1]
            if re.match(
                r"\s*(?:\d|[A-Z](?:\b|[.-]\d))",
                paragraph[match.end() :],
            )
            else match.group(),
            paragraph,
        )
        for candidate in re.split(r"(?<=[.!?])\s+", paragraph):
            candidate = candidate.strip()
            if tokens_in(candidate):
                sentences.append(candidate)
    return sentences


def connective_matches(tokens: list[str]) -> list[str]:
    """Return non-overlapping maintained phrases with token boundaries."""
    matches: list[str] = []
    index = 0
    while index < len(tokens):
        for phrase in CONNECTIVE_TOKEN_SEQUENCES:
            width = len(phrase)
            if tuple(tokens[index : index + width]) == phrase:
                matches.append(" ".join(phrase))
                index += width
                break
        else:
            index += 1
    return matches


def initial_connective(sentence: str) -> str | None:
    """Return the maintained phrase opening ``sentence``, if any."""
    tokens = tokens_in(sentence)
    for phrase in CONNECTIVE_TOKEN_SEQUENCES:
        if tuple(tokens[: len(phrase)]) == phrase:
            return " ".join(phrase)
    return None


def _per_1000(count: int, words: int) -> float:
    return round((count / words) * 1000.0, 4)


def analyze(text: str) -> dict[str, Any]:
    """Analyze text and return the raw, separate metric record."""
    prose, warnings = extract_prose(text)
    tokens = tokens_in(prose)
    sentences = sentences_in(prose)
    if not tokens or not sentences:
        raise ValueError("input contains no prose words after exclusions")

    matches = connective_matches(tokens)
    initial_matches = [
        phrase
        for sentence in sentences
        if (phrase := initial_connective(sentence)) is not None
    ]
    all_counts = Counter(matches)
    initial_counts = Counter(initial_matches)
    used_phrases = sorted(set(all_counts) | set(initial_counts))

    metrics = {
        "connective_density_per_1000_words": {
            "count": len(matches),
            "denominator_words": len(tokens),
            "rate": _per_1000(len(matches), len(tokens)),
            "unit": "matches_per_1000_words",
        },
        "sentence_initial_connective_ratio": {
            "count": len(initial_matches),
            "denominator_sentences": len(sentences),
            "rate": round(len(initial_matches) / len(sentences), 4),
            "unit": "proportion_of_sentences",
        },
    }
    return {
        "counts": {"words": len(tokens), "sentences": len(sentences)},
        "metrics": metrics,
        "matches": {
            "connectives": matches,
            "sentence_initial_connectives": initial_matches,
        },
        "breakdown": {
            phrase: {
                "count": all_counts[phrase],
                "sentence_initial_count": initial_counts[phrase],
            }
            for phrase in used_phrases
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
    if name == "sentence_initial_connective_ratio" and rate > 1:
        raise ValueError(
            "baseline sentence_initial_connective_ratio must be between 0 and 1"
        )
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
        "breakdown": analysis["breakdown"],
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
    density = metrics["connective_density_per_1000_words"]
    initial = metrics["sentence_initial_connective_ratio"]

    lines = [
        "CONNECTIVE OVERUSE SCREEN — REVIEW ONLY; NO AGGREGATE SCORE",
        f"Prose counted: {counts['words']} words, {counts['sentences']} sentences",
        (
            "connective density                    "
            f"{density['rate']:.2f} per 1,000 words ({density['count']} matches)"
        ),
        (
            "sentence-initial connective ratio    "
            f"{initial['rate'] * 100:.2f}% "
            f"({initial['count']}/{initial['denominator_sentences']} sentences)"
        ),
    ]

    if record["breakdown"]:
        lines.append("Per-connective breakdown:")
        for phrase, item in record["breakdown"].items():
            lines.append(
                f"  {phrase}: {item['count']} total, "
                f"{item['sentence_initial_count']} sentence-initial"
            )

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
            "Screen connective density and sentence-initial transitions as "
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
        print(f"connectives: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(render_human(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
