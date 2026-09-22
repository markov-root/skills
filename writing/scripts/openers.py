#!/usr/bin/env python3
"""Sentence-opener, expletive, and ``-ly`` pile-up review screen.

This deterministic, stdlib-only tool reports separate structural measurements:

* sentences participating in a repeated-opener cluster (the same first word
  appearing within a three-sentence window);
* sentences opening with ``This``, ``It``, or ``There``;
* sentence-opening ``there is/are/was/were`` and ``it is/was`` constructions
  per 1,000 prose words;
* likely ``-ly`` adverbs per 1,000 prose words; and
* sentences with at least two leading or nearby likely ``-ly`` adverbs.

The measurements are review signals, never assertions about writing quality and
never an aggregate score. With ``--baseline FILE``, the tool reports signed
per-metric divergence from accepted-prose rates; it invents no thresholds.

Markdown exclusions are deliberately conservative: fenced code, inline code,
ATX and Setext headings, blockquote lines, and text inside matched straight or
curly double quotes are omitted. Single-quoted text is retained because
apostrophes make a reliable context-free distinction impossible.

Known limitations
-----------------
Sentence splitting protects common titles, reference abbreviations, initials,
and initialisms, but it is not a full parser. Repeated openers and ``This``/
``It``/``There`` openers are sometimes rhetorically correct. Expletive matching
is lexical and does not judge whether a construction is useful. An ``-ly`` word
is not always an adverb; a conservative exception list reduces false positives
such as ``family``, ``reply``, and ``apply`` but also misses ambiguous adverbs.
The tokenizer is Latin-script oriented.

Exit 0 means the screen completed, regardless of the rates. Exit 2 means an
input or baseline could not be read or parsed. Reads a path, or stdin when the
path is omitted or ``-``.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
from typing import Any

FORMAT_VERSION = 1
TYPE = "sentence_opener_screen"

METRIC_ORDER = (
    "repeated_opener_sentence_rate",
    "this_it_there_opener_rate",
    "expletive_opener_rate_per_1000_words",
    "ly_adverb_rate_per_1000_words",
    "ly_pileup_sentence_rate",
)

THIS_IT_THERE = {"this", "it", "there"}
EXPLETIVE_OPENERS = {
    ("there", "is"),
    ("there", "are"),
    ("there", "was"),
    ("there", "were"),
    ("it", "is"),
    ("it", "was"),
}

# These are common nouns, verbs, adjectives, proper-name-like words, or
# otherwise ambiguous forms. Excluding them favors precision over recall.
LY_NON_ADVERBS = {
    "ally",
    "apply",
    "belly",
    "brotherly",
    "bully",
    "burly",
    "comely",
    "comply",
    "costly",
    "curly",
    "daily",
    "deadly",
    "early",
    "elderly",
    "family",
    "fatherly",
    "friendly",
    "ghastly",
    "heavenly",
    "holy",
    "homely",
    "hourly",
    "imply",
    "italy",
    "jelly",
    "july",
    "kingly",
    "likely",
    "lively",
    "lonely",
    "lovely",
    "manly",
    "monthly",
    "motherly",
    "multiply",
    "only",
    "orderly",
    "prickly",
    "reply",
    "scholarly",
    "silly",
    "sisterly",
    "sparkly",
    "stately",
    "supply",
    "surly",
    "ugly",
    "unlikely",
    "weekly",
    "womanly",
    "woolly",
    "worldly",
    "wrinkly",
    "yearly",
}

EXCLUSIONS = (
    "fenced code blocks (backticks or tildes)",
    "inline code spans",
    "ATX and Setext headings and Markdown blockquote lines",
    "matched straight or curly double-quoted spans",
)

LIMITATIONS = (
    "Sentence splitting is heuristic: common abbreviations and initialisms are "
    "protected, but uncommon abbreviations and unusual punctuation can split "
    "or join sentences incorrectly.",
    "A repeated opener, or a This/It/There opener, can be rhetorically correct; "
    "the repeated-opener cluster uses a fixed three-sentence window.",
    "Expletive matching is lexical and limited to sentence-opening 'there "
    "is/are/was/were' and 'it is/was'; it does not judge usefulness.",
    "An -ly word is not always an adverb. A conservative exception list removes "
    "common false positives such as family, reply, and apply, but context-blind "
    "matching still produces false positives and false negatives.",
    "An -ly pile-up means two candidates in the first four tokens or separated "
    "by at most one intervening token; it is not a syntactic parse.",
    "The word tokenizer is Latin-script oriented, so non-Latin prose is under-counted.",
)

WORD_RE = re.compile(
    r"[A-Za-z](?:\.[A-Za-z])+(?:\.)?"
    r"|[A-Za-z]+(?:[\N{RIGHT SINGLE QUOTATION MARK}'][A-Za-z]+)*"
    r"(?:-[A-Za-z]+(?:[\N{RIGHT SINGLE QUOTATION MARK}'][A-Za-z]+)*)*"
    r"|\d+(?:[.,]\d+)*"
)
FENCE_OPEN_RE = re.compile(r"^\s{0,3}(?P<marker>`{3,}|~{3,})")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:\s+|$)")
SETEXT_HEADING_RE = re.compile(r"^\s{0,3}(?:=+|-+)\s*$")
THEMATIC_BREAK_RE = re.compile(r"^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>")
LIST_MARKER_RE = re.compile(r"^\s*(?:[-+*]|\d{1,9}[.)])\s+(?:\[[ xX]\]\s+)?")
INLINE_CODE_RE = re.compile(r"`+[^`\n]*`+")
STRAIGHT_QUOTE_RE = re.compile(r'"[^"\n]*"')
CURLY_QUOTE_RE = re.compile(
    r"\N{LEFT DOUBLE QUOTATION MARK}[^\N{RIGHT DOUBLE QUOTATION MARK}\n]*\N{RIGHT DOUBLE QUOTATION MARK}"
)
LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\([^\s)]+(?:\s+[^)]*)?\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
PUNCTUATION_RE = re.compile(r"[.!?]+")
NONTERMINAL_ABBREVIATION_RE = re.compile(
    r"\b(?:mr|mrs|ms|dr|prof|sr|jr|st|mt|vs)\.$",
    re.IGNORECASE,
)
REFERENCE_ABBREVIATION_RE = re.compile(r"\b(?:fig|no)\.$", re.IGNORECASE)
EXAMPLE_ABBREVIATION_RE = re.compile(r"\b(?:e\.g|i\.e)\.$", re.IGNORECASE)
INITIALISM_RE = re.compile(r"(?:\b[A-Za-z]\.){2,}$")
SINGLE_INITIAL_RE = re.compile(r"\b[A-Z]\.$")
NEXT_WORD_RE = re.compile(r"[A-Za-z]+")
SENTENCE_STARTERS = {
    "a",
    "an",
    "but",
    "he",
    "however",
    "i",
    "in",
    "it",
    "meanwhile",
    "she",
    "that",
    "the",
    "they",
    "this",
    "there",
    "we",
    "yet",
    "you",
}


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
    lines = text.splitlines()
    kept: list[str] = []
    fence_char: str | None = None
    fence_length = 0
    index = 0

    while index < len(lines):
        line = lines[index]
        if fence_char is not None:
            close_re = re.compile(
                rf"^\s{{0,3}}{re.escape(fence_char)}{{{fence_length},}}\s*$"
            )
            if close_re.match(line):
                fence_char = None
                fence_length = 0
            kept.append("")
            index += 1
            continue

        fence = FENCE_OPEN_RE.match(line)
        if fence:
            marker = fence.group("marker")
            fence_char = marker[0]
            fence_length = len(marker)
            kept.append("")
            index += 1
            continue

        if (
            line.strip()
            and index + 1 < len(lines)
            and SETEXT_HEADING_RE.match(lines[index + 1])
        ):
            kept.extend(("", ""))
            index += 2
            continue

        if (
            HEADING_RE.match(line)
            or THEMATIC_BREAK_RE.match(line)
            or BLOCKQUOTE_RE.match(line)
        ):
            kept.append("")
            index += 1
            continue

        kept.append(LIST_MARKER_RE.sub("", line, count=1))
        index += 1

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
    """Return normalized English-oriented word/number tokens."""
    return [token.lower() for token in WORD_RE.findall(text)]


def _next_word(text: str, start: int) -> str:
    match = NEXT_WORD_RE.search(text, start)
    return match.group(0).lower() if match else ""


def _is_nonterminal_period(text: str, period_end: int) -> bool:
    prefix = text[:period_end]
    if NONTERMINAL_ABBREVIATION_RE.search(prefix):
        return True
    if REFERENCE_ABBREVIATION_RE.search(prefix):
        return bool(re.match(r"\s*(?:\d|[A-Z](?:\b|[.-]\d))", text[period_end:]))
    if EXAMPLE_ABBREVIATION_RE.search(prefix):
        return True
    if INITIALISM_RE.search(prefix):
        return _next_word(text, period_end) not in SENTENCE_STARTERS
    if SINGLE_INITIAL_RE.search(prefix):
        following = NEXT_WORD_RE.search(text, period_end)
        return bool(following and following.group(0)[:1].isupper())
    return False


def sentences_in(text: str) -> list[str]:
    """Split prose sentences, protecting decimals and common abbreviations."""
    sentences: list[str] = []
    start = 0

    for match in PUNCTUATION_RE.finditer(text):
        punctuation = match.group(0)
        end = match.end()
        closing = re.match(
            r"[\"'\N{RIGHT DOUBLE QUOTATION MARK}\N{RIGHT SINGLE QUOTATION MARK})}\]]*",
            text[end:],
        )
        boundary_end = end + (len(closing.group(0)) if closing else 0)
        if boundary_end < len(text) and not text[boundary_end].isspace():
            continue
        if set(punctuation) == {"."} and len(punctuation) == 1:
            if _is_nonterminal_period(text, end):
                continue

        segment = text[start:boundary_end].strip()
        if tokens_in(segment):
            sentences.append(segment)
        start = boundary_end

    trailing = text[start:].strip()
    if tokens_in(trailing):
        sentences.append(trailing)
    return sentences


def _per_1000(count: int, words: int) -> float:
    return round((count / words) * 1000.0, 4)


def _repeated_cluster_indices(openers: list[str]) -> set[int]:
    repeated: set[int] = set()
    for left, opener in enumerate(openers):
        for right in range(left + 1, min(left + 3, len(openers))):
            if openers[right] == opener:
                repeated.update((left, right))
    return repeated


def _adjacent_runs(openers: list[str]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    start = 0
    while start < len(openers):
        end = start + 1
        while end < len(openers) and openers[end] == openers[start]:
            end += 1
        if end - start >= 2:
            runs.append(
                {
                    "opener": openers[start],
                    "start_sentence": start + 1,
                    "length": end - start,
                }
            )
        start = end
    return runs


def _is_ly_candidate(token: str) -> bool:
    return any(
        len(part) >= 4 and part.endswith("ly") and part not in LY_NON_ADVERBS
        for part in token.split("-")
    )


def _pileup_kind(tokens: list[str], positions: list[int]) -> str | None:
    leading = sum(position < 4 for position in positions) >= 2
    clustered = any(right - left <= 2 for left, right in zip(positions, positions[1:]))
    if leading and clustered:
        return "leading_and_clustered"
    if leading:
        return "leading"
    if clustered:
        return "clustered"
    return None


def analyze(text: str) -> dict[str, Any]:
    """Analyze text and return separate structural metric records."""
    prose, warnings = extract_prose(text)
    words = tokens_in(prose)
    sentences = sentences_in(prose)
    if not words or not sentences:
        raise ValueError("input contains no prose words after exclusions")

    sentence_tokens = [tokens_in(sentence) for sentence in sentences]
    openers = [tokens[0] for tokens in sentence_tokens]
    repeated_indices = _repeated_cluster_indices(openers)
    adjacent_runs = _adjacent_runs(openers)

    opener_counts = collections.Counter(openers)
    first_positions = {opener: openers.index(opener) for opener in opener_counts}
    most_repeated = max(
        opener_counts,
        key=lambda opener: (opener_counts[opener], -first_positions[opener]),
    )

    this_it_there_indices = [
        index for index, opener in enumerate(openers) if opener in THIS_IT_THERE
    ]
    expletives: list[dict[str, Any]] = []
    ly_candidates: list[str] = []
    ly_pileups: list[dict[str, Any]] = []

    for index, tokens in enumerate(sentence_tokens):
        if len(tokens) >= 2 and tuple(tokens[:2]) in EXPLETIVE_OPENERS:
            expletives.append(
                {"sentence": index + 1, "construction": " ".join(tokens[:2])}
            )

        positions = [
            position for position, token in enumerate(tokens) if _is_ly_candidate(token)
        ]
        candidates = [tokens[position] for position in positions]
        ly_candidates.extend(candidates)
        kind = _pileup_kind(tokens, positions)
        if kind is not None:
            ly_pileups.append(
                {"sentence": index + 1, "candidates": candidates, "kind": kind}
            )

    sentence_count = len(sentences)
    metrics = {
        "repeated_opener_sentence_rate": {
            "count": len(repeated_indices),
            "denominator_sentences": sentence_count,
            "rate": round(len(repeated_indices) / sentence_count, 4),
            "unit": "proportion_of_sentences",
        },
        "this_it_there_opener_rate": {
            "count": len(this_it_there_indices),
            "denominator_sentences": sentence_count,
            "rate": round(len(this_it_there_indices) / sentence_count, 4),
            "unit": "proportion_of_sentences",
        },
        "expletive_opener_rate_per_1000_words": {
            "count": len(expletives),
            "denominator_words": len(words),
            "rate": _per_1000(len(expletives), len(words)),
            "unit": "constructions_per_1000_words",
        },
        "ly_adverb_rate_per_1000_words": {
            "count": len(ly_candidates),
            "denominator_words": len(words),
            "rate": _per_1000(len(ly_candidates), len(words)),
            "unit": "candidates_per_1000_words",
        },
        "ly_pileup_sentence_rate": {
            "count": len(ly_pileups),
            "denominator_sentences": sentence_count,
            "rate": round(len(ly_pileups) / sentence_count, 4),
            "unit": "proportion_of_sentences",
        },
    }

    return {
        "counts": {
            "words": len(words),
            "sentences": sentence_count,
            "adjacent_same_opener_runs": len(adjacent_runs),
        },
        "metrics": metrics,
        "matches": {
            "sentence_openers": openers,
            "most_repeated_opener": {
                "opener": most_repeated,
                "count": opener_counts[most_repeated],
            },
            "repeated_opener_sentences": [
                index + 1 for index in sorted(repeated_indices)
            ],
            "adjacent_same_opener_runs": adjacent_runs,
            "this_it_there_opener_sentences": [
                index + 1 for index in this_it_there_indices
            ],
            "expletive_openers": expletives,
            "ly_adverbs": ly_candidates,
            "ly_pileups": ly_pileups,
        },
        "warnings": warnings,
    }


def _rate_value(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"baseline rate {name!r} must be numeric")
    rate = float(value)
    if not math.isfinite(rate):
        raise ValueError(f"baseline rate {name!r} must be finite")
    if rate < 0:
        raise ValueError(f"baseline rate {name!r} must not be negative")
    if (
        name
        in {
            "repeated_opener_sentence_rate",
            "this_it_there_opener_rate",
            "ly_pileup_sentence_rate",
        }
        and rate > 1
    ):
        raise ValueError(f"baseline rate {name!r} must be between 0 and 1")
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
    repeated = metrics["repeated_opener_sentence_rate"]
    demonstrative = metrics["this_it_there_opener_rate"]
    expletive = metrics["expletive_opener_rate_per_1000_words"]
    ly_adverb = metrics["ly_adverb_rate_per_1000_words"]
    pileup = metrics["ly_pileup_sentence_rate"]
    most = record["matches"]["most_repeated_opener"]

    lines = [
        "SENTENCE OPENER SCREEN — REVIEW ONLY; NO AGGREGATE SCORE",
        f"Prose counted: {counts['words']} words, {counts['sentences']} sentences",
        (
            "repeated-opener sentence rate       "
            f"{repeated['rate'] * 100:.2f}% "
            f"({repeated['count']}/{repeated['denominator_sentences']} sentences)"
        ),
        (
            "This/It/There opener rate            "
            f"{demonstrative['rate'] * 100:.2f}% "
            f"({demonstrative['count']}/{demonstrative['denominator_sentences']} sentences)"
        ),
        (
            "most repeated opener                 "
            f"{most['opener']!r} ({most['count']} sentences)"
        ),
        (f"adjacent same-opener runs            {counts['adjacent_same_opener_runs']}"),
        (
            "expletive opener rate                "
            f"{expletive['rate']:.2f} per 1,000 words "
            f"({expletive['count']} constructions)"
        ),
        (
            "-ly adverb candidate rate            "
            f"{ly_adverb['rate']:.2f} per 1,000 words "
            f"({ly_adverb['count']} candidates)"
        ),
        (
            "-ly pile-up sentence rate            "
            f"{pileup['rate'] * 100:.2f}% "
            f"({pileup['count']}/{pileup['denominator_sentences']} sentences)"
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
            "Screen repeated sentence openers, expletive openers, and -ly "
            "pile-ups as separate advisory metrics; never an aggregate score."
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
        print(f"openers: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(render_human(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
