#!/usr/bin/env python3
"""readability.py — readability and length screen for Markdown/prose.

This self-contained, deterministic, stdlib-only tool reports separate raw
metrics. It is a review screen, never a quality score, an AI score, a gate, or
an autofixer. Successful analysis always exits 0; unreadable, malformed, or
prose-empty input exits 2 with a clean diagnostic.

Markdown handling
-----------------
- fenced code blocks opened by three-or-more backticks or tildes are removed;
- ATX and Setext heading text is removed;
- thematic breaks are removed; and
- bullet, numbered-list, and task-list markers are removed while their prose is
  retained.

The Flesch metrics are English-oriented estimates. Words are letter/number
tokens. The syllable heuristic counts contiguous vowel groups (including y),
discounts common silent-e/-ed/-es endings, preserves consonant+le endings, and
uses at least one syllable per token. It uses no pronunciation dictionary, so
names, acronyms, and irregular words remain approximations.

Use ``--json`` output from accepted prose as ``--baseline FILE``. Divergence is
reported as per-metric baseline/current/delta records; no threshold, aggregate,
or verdict is invented. A baseline must use the same ``--long-sentence`` value
so its count remains comparable.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys

FORMAT_VERSION = 1
OUTPUT_TYPE = "readability_screen"

WORD_RE = re.compile(
    r"[A-Za-z](?:\.[A-Za-z])+(?:\.)?"
    r"|[A-Za-z](?:&[A-Za-z])+"
    r"|[A-Za-z]+(?:[’'][A-Za-z]+)*(?:-[A-Za-z]+(?:[’'][A-Za-z]+)*)*"
    r"|\d+(?:[.,]\d+)*"
)
PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
FENCE_RE = re.compile(r"^\s{0,3}(?P<fence>`{3,}|~{3,})")
ATX_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:\s+|$)")
SETEXT_HEADING_RE = re.compile(r"^\s{0,3}(?:=+|-+)\s*$")
THEMATIC_BREAK_RE = re.compile(r"^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
LIST_MARKER_RE = re.compile(r"^\s*(?:[-+*]|\d{1,9}[.)])\s+(?:\[[ xX]\]\s+)?")
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

SYLLABLE_EXCEPTIONS = {
    "science": 2,
    "sciences": 2,
}

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
    "we",
    "yet",
    "you",
}

PROCESSING = {
    "fenced_code_blocks": "removed",
    "headings": "removed (ATX and Setext)",
    "list_markers": "removed; list prose retained",
}

METRIC_PATHS = (
    ("flesch_kincaid_grade",),
    ("flesch_reading_ease",),
    ("sentence_length_words", "mean"),
    ("sentence_length_words", "median"),
    ("sentence_length_words", "longest"),
    ("sentence_length_words", "over_threshold"),
    ("sentences_per_paragraph", "mean"),
    ("sentences_per_paragraph", "median"),
    ("sentences_per_paragraph", "longest"),
)


def _read_source(path: str | None) -> str:
    try:
        if path is None or path == "-":
            return sys.stdin.read()
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeError) as exc:
        label = "stdin" if path is None or path == "-" else repr(path)
        raise ValueError(f"cannot read {label}: {exc}") from None


def strip_markdown(text: str) -> str:
    """Remove non-prose Markdown constructs described in the module docstring."""
    lines = text.splitlines()
    cleaned: list[str] = []
    in_fence = False
    fence_character = ""
    fence_length = 0
    index = 0

    while index < len(lines):
        line = lines[index]
        if in_fence:
            closing = re.match(
                rf"^\s{{0,3}}{re.escape(fence_character)}"
                rf"{{{fence_length},}}\s*$",
                line,
            )
            if closing:
                in_fence = False
            cleaned.append("")
            index += 1
            continue

        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group("fence")
            in_fence = True
            fence_character = marker[0]
            fence_length = len(marker)
            cleaned.append("")
            index += 1
            continue

        if (
            line.strip()
            and index + 1 < len(lines)
            and SETEXT_HEADING_RE.match(lines[index + 1])
        ):
            cleaned.extend(("", ""))
            index += 2
            continue

        if ATX_HEADING_RE.match(line) or THEMATIC_BREAK_RE.match(line):
            cleaned.append("")
            index += 1
            continue

        cleaned.append(LIST_MARKER_RE.sub("", line, count=1))
        index += 1

    return "\n".join(cleaned)


def tokens_in(text: str) -> list[str]:
    """Return English-oriented word/number tokens, preserving contractions."""
    return WORD_RE.findall(text)


def _next_word(text: str, start: int) -> str:
    match = NEXT_WORD_RE.search(text, start)
    return match.group(0).lower() if match else ""


def _is_nonterminal_period(text: str, period_end: int) -> bool:
    prefix = text[:period_end]
    if NONTERMINAL_ABBREVIATION_RE.search(prefix):
        return True
    if REFERENCE_ABBREVIATION_RE.search(prefix):
        # "No. 7" and "Fig. A" are reference labels; "No. It failed." is
        # two sentences. Keeping these cases separate avoids a blanket under-split.
        return bool(re.match(r"\s*(?:\d|[A-Z](?:\b|[.-]\d))", text[period_end:]))
    if EXAMPLE_ABBREVIATION_RE.search(prefix):
        return True
    if INITIALISM_RE.search(prefix):
        # Initialisms can finish a sentence. A small high-precision starter list
        # prevents the common "U.S. The ..." under-split without pretending to
        # solve every abbreviation in English.
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

        closing = re.match(r"[\"'”’)}\]]*", text[end:])
        boundary_end = end + (len(closing.group(0)) if closing else 0)
        if boundary_end < len(text) and not text[boundary_end].isspace():
            # Includes decimal points such as 3.14 and dots inside abbreviations.
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


def syllables_in_word(token: str) -> int:
    """Estimate syllables with a documented vowel-group/silent-ending rule."""
    if token[:1].isdigit():
        return 1

    normalized = token.lower().replace("’", "'")
    parts = normalized.split("-")
    total = 0
    for part in parts:
        word = re.sub(r"[^a-z]", "", part)
        if not word:
            continue
        if word in SYLLABLE_EXCEPTIONS:
            total += SYLLABLE_EXCEPTIONS[word]
            continue
        count = len(re.findall(r"[aeiouy]+", word))
        if len(word) > 2 and word.endswith("e"):
            consonant_le = (
                len(word) >= 3 and word.endswith("le") and word[-3] not in "aeiouy"
            )
            if not consonant_le and count > 1:
                count -= 1
        elif len(word) > 3 and word.endswith("ed") and word[-3] not in "dt":
            if count > 1:
                count -= 1
        elif len(word) > 3 and word.endswith("es"):
            pronounced_es = word.endswith(("ses", "xes", "zes", "ches", "shes"))
            if not pronounced_es and count > 1:
                count -= 1
        total += max(1, count)
    return max(1, total)


def _distribution(values: list[int]) -> dict[str, float | int]:
    return {
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
        "longest": max(values),
    }


def analyze_text(text: str, long_sentence: int = 40) -> dict:
    """Return counts and separate readability/length metrics for prose text."""
    cleaned = strip_markdown(text)
    raw_paragraphs = [
        paragraph.strip()
        for paragraph in PARAGRAPH_SPLIT_RE.split(cleaned)
        if paragraph.strip()
    ]

    paragraph_sentences: list[list[str]] = []
    for paragraph in raw_paragraphs:
        sentences = [
            sentence for sentence in sentences_in(paragraph) if tokens_in(sentence)
        ]
        if sentences:
            paragraph_sentences.append(sentences)

    sentences = [sentence for group in paragraph_sentences for sentence in group]
    sentence_tokens = [tokens_in(sentence) for sentence in sentences]
    sentence_lengths = [len(words) for words in sentence_tokens if words]
    words = [word for sentence in sentence_tokens for word in sentence]

    if not words or not sentence_lengths or not paragraph_sentences:
        raise ValueError(
            "input contains no prose words after removing fenced code and headings"
        )

    syllables = sum(syllables_in_word(word) for word in words)
    words_per_sentence = len(words) / len(sentence_lengths)
    syllables_per_word = syllables / len(words)

    sentence_distribution = _distribution(sentence_lengths)
    sentence_distribution["over_threshold"] = sum(
        length > long_sentence for length in sentence_lengths
    )
    paragraph_distribution = _distribution(
        [len(group) for group in paragraph_sentences]
    )

    metrics = {
        "flesch_kincaid_grade": round(
            0.39 * words_per_sentence + 11.8 * syllables_per_word - 15.59,
            2,
        ),
        "flesch_reading_ease": round(
            206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word,
            2,
        ),
        "sentence_length_words": sentence_distribution,
        "sentences_per_paragraph": paragraph_distribution,
    }
    return {
        "counts": {
            "words": len(words),
            "syllables": syllables,
            "sentences": len(sentence_lengths),
            "paragraphs": len(paragraph_sentences),
        },
        "metrics": metrics,
    }


def _metric_value(metrics: dict, path: tuple[str, ...]) -> float | int:
    value = metrics
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"baseline missing metric: {'.'.join(path)}")
        value = value[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"baseline metric is not numeric: {'.'.join(path)}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"baseline metric is not finite: {'.'.join(path)}")
    return value


def load_baseline(path: str, long_sentence: int) -> dict:
    """Load and validate JSON previously emitted by this script."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            baseline = json.load(fh)
    except OSError as exc:
        raise ValueError(f"cannot read baseline {path!r}: {exc}") from None
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot parse baseline {path!r}: {exc}") from None

    if not isinstance(baseline, dict):
        raise ValueError("baseline JSON must be an object")
    if baseline.get("type") != OUTPUT_TYPE:
        raise ValueError(f"baseline type must be {OUTPUT_TYPE!r}")
    if baseline.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"baseline format_version must be {FORMAT_VERSION}")
    if baseline.get("long_sentence_words") != long_sentence:
        raise ValueError(
            f"baseline long_sentence_words must match --long-sentence ({long_sentence})"
        )
    metrics = baseline.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("baseline missing metrics object")
    for metric_path in METRIC_PATHS:
        _metric_value(metrics, metric_path)
    return metrics


def _difference(current: float | int, baseline: float | int) -> dict:
    delta = round(current - baseline, 2)
    return {
        "baseline": baseline,
        "current": current,
        "delta": delta,
        "direction": "higher" if delta > 0 else "lower" if delta < 0 else "unchanged",
    }


def build_divergence(current: dict, baseline: dict) -> dict:
    """Mirror the raw metric shape with per-leaf baseline/current deltas."""
    divergence: dict = {}
    for path in METRIC_PATHS:
        current_value = _metric_value(current, path)
        baseline_value = _metric_value(baseline, path)
        target = divergence
        for key in path[:-1]:
            target = target.setdefault(key, {})
        target[path[-1]] = _difference(current_value, baseline_value)
    return divergence


def _render_divergence(prefix: str, value: dict, lines: list[str]) -> None:
    if set(value) == {"baseline", "current", "delta", "direction"}:
        lines.append(
            f"  {prefix:<39} baseline {value['baseline']:>7}  "
            f"current {value['current']:>7}  delta {value['delta']:>7}"
        )
        return
    for key, nested in value.items():
        label = f"{prefix}.{key}" if prefix else key
        _render_divergence(label, nested, lines)


def human_report(record: dict) -> str:
    metrics = record["metrics"]
    sentences = metrics["sentence_length_words"]
    paragraphs = metrics["sentences_per_paragraph"]
    counts = record["counts"]
    lines = [
        "READABILITY SCREEN — review only; no aggregate quality or AI score",
        (
            f"  prose: {counts['words']} words · {counts['sentences']} sentences · "
            f"{counts['paragraphs']} paragraphs"
        ),
        f"  Flesch-Kincaid grade: {metrics['flesch_kincaid_grade']}",
        f"  Flesch reading ease:  {metrics['flesch_reading_ease']}",
        (
            "  sentence words:      "
            f"mean {sentences['mean']} · median {sentences['median']} · "
            f"longest {sentences['longest']} · over "
            f"{record['long_sentence_words']}: {sentences['over_threshold']}"
        ),
        (
            "  sentences/paragraph: "
            f"mean {paragraphs['mean']} · median {paragraphs['median']} · "
            f"longest {paragraphs['longest']}"
        ),
        "  preprocessing: fenced code and headings removed; list prose retained",
    ]
    if "divergence" in record:
        lines.append("DIVERGENCE FROM THIS AUTHOR'S ACCEPTED-PROSE BASELINE")
        _render_divergence("", record["divergence"], lines)
        lines.append("  Deltas are review signals, not thresholds or verdicts.")
    return "\n".join(lines)


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report separate readability and length metrics. Review screen only: "
            "never a quality/AI score and never a gate."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Markdown/prose file to analyze (default: stdin; '-' also means stdin)",
    )
    parser.add_argument(
        "--baseline",
        help="JSON emitted by this tool for the author's accepted prose",
    )
    parser.add_argument(
        "--long-sentence",
        type=positive_integer,
        default=40,
        metavar="N",
        help="count sentences longer than N words (default: 40)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit one stable machine-readable JSON object",
    )
    args = parser.parse_args(argv)

    try:
        text = _read_source(args.path)
        analysis = analyze_text(text, args.long_sentence)
        baseline_metrics = (
            load_baseline(args.baseline, args.long_sentence) if args.baseline else None
        )
    except ValueError as exc:
        print(f"readability: {exc}", file=sys.stderr)
        return 2

    record = {
        "type": OUTPUT_TYPE,
        "format_version": FORMAT_VERSION,
        "path": args.path,
        "long_sentence_words": args.long_sentence,
        "processing": PROCESSING,
        "counts": analysis["counts"],
        "metrics": analysis["metrics"],
    }
    if baseline_metrics is not None:
        record["baseline_path"] = args.baseline
        record["divergence"] = build_divergence(analysis["metrics"], baseline_metrics)

    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(human_report(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
