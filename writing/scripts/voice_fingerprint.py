#!/usr/bin/env python3
"""Voice-fingerprint baseline: deterministic, stdlib-only, offline.

A *screen*, never a gate, and never an AI detector. Given a writer's own accepted
same-genre passages it derives a coarse voice profile; given a draft it reports only
how far the draft deviates from THAT writer's own baseline. The comparison frame is
"deviates from YOU", never "deviates from generic good prose", and there is no
aggregate quality score.

Subcommands
-----------
baseline PATH... [--genre LABEL] [--out FILE]
    Build a profile JSON from 3+ writer-accepted passages.
compare --baseline PROFILE.json DRAFT_PATH [--human]
    Screen a draft against the writer's own baseline. Emits JSON on stdout and
    (with --human) the summary on stderr. Exit 0 when the compare completed (flags
    are a review signal, not a block); exit 2 on a malformed/missing baseline,
    an unknown metric key, or an unreadable/unparseable input — never masking a
    broken baseline as a clean pass.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys

FORMAT_VERSION = 1
MIN_PASSAGES = 3

# Small, deliberately high-precision contraction whitelist. Cleaner than a regex
# that misreads possessives ("john's") as contractions.
CONTRACTIONS = {
    "don't", "can't", "won't", "isn't", "aren't", "wasn't", "weren't",
    "i'm", "we're", "you're", "they're",
    "i've", "we've", "you've", "they've", "could've", "would've", "should've",
    "it's", "that's", "there's", "here's", "what's", "who's", "how's",
    "i'll", "we'll", "you'll", "they'll", "it'll", "let's",
    "i'd", "we'd", "you'd", "they'd", "he'd", "she'd", "it'd",
    "hasn't", "haven't", "he's", "she's",
}

# Coarse stance/hedge vocabulary, high-precision single words so the screen reflects
# genuine hedging rather than incidental modal verbs (could/might/may).
HEDGE_VOCAB = {
    "arguably", "perhaps", "maybe", "usually", "generally", "typically",
    "largely", "broadly", "mostly", "somewhat", "fairly", "relatively",
    "seemingly", "apparently", "reportedly", "notably", "rather",
    "some", "several", "likely",
}

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[’'\-][a-z0-9]+)*")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
EM_DASH_RE = re.compile(r"—|–|--")

# Flag thresholds are calibrated to the writer's *own* variability, not to any
# generic ideal. REL means "deviate by more than REL% of the baseline value".
REL_TOLERANCE = 0.08
# First-word screen: flag when more than this fraction of a draft's sentence openers
# fall entirely outside the writer's own opener vocabulary.
OPENER_TOLERANCE = 0.30


def read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}")


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in PARAGRAPH_SPLIT.split(text) if p.strip()]


def tokens_in(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def sentences_in(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]


def analyze(text: str) -> dict:
    paragraphs = split_paragraphs(text)
    sentences = [s for para in paragraphs for s in sentences_in(para)]

    sentence_lengths = [len(tokens_in(s)) for s in sentences]
    all_tokens = [tok for s in sentences for tok in tokens_in(s)]
    total_words = len(all_tokens)

    contraction_hits = sum(1 for t in all_tokens if t in CONTRACTIONS)
    hedge_hits = sum(1 for t in all_tokens if t in HEDGE_VOCAB)
    em_dash_count = len(EM_DASH_RE.findall(text))

    openers = []
    for s in sentences:
        toks = tokens_in(s)
        if toks:
            openers.append(toks[0])

    return {
        "sentence_lengths": sentence_lengths,
        "per_paragraph_counts": [len(sentences_in(p)) for p in paragraphs],
        "total_words": total_words,
        "contraction_count": contraction_hits,
        "hedge_count": hedge_hits,
        "em_dash_count": em_dash_count,
        "openers": openers,
        "coverage": coverage_note(text, total_words),
    }


def coverage_note(text: str, ascii_words: int) -> str | None:
    """Return a non-None warning when the ASCII tokenizer under-measures text.

    TOKEN_RE matches only [a-z0-9], so any non-Latin script (CJK, Cyrillic, etc.)
    — whether a draft is entirely in it or mixed with Latin — is measured with a
    skewed token count and this screen silently under-covers voice. Surface a
    coverage warning (never a verdict) whenever non-ASCII word characters are
    present, rather than quietly passing it.
    """
    if not re.search(r"[\u0080-\U0010FFFF]", text):
        return None
    return (
        "coverage: the tokenizer is ASCII/Latin-only and this draft contains "
        f"non-ASCII word characters ({ascii_words} ASCII tokens counted). Voice "
        "metrics for this draft are partial — treat results as a screen, not a "
        "measurement."
    )


def span_stats(values):
    """Return coarse distribution stats over numeric observations."""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": 0.0, "median": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0}
    mean = statistics.fmean(values)
    return {
        "n": n,
        "mean": round(mean, 2),
        "median": round(statistics.median(values), 2),
        "stdev": round(statistics.pstdev(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def _rate_meta(pass_analyses, key: str, total_words: int) -> dict:
    per_passage = [_rate(a[key], a["total_words"]) for a in pass_analyses]
    pooled = _rate(sum(a[key] for a in pass_analyses), total_words)
    return {
        "rate": pooled,
        "per_passage": span_stats(per_passage),
        "total_words": total_words,
    }


def _rate(count: int, total_words: int) -> float:
    return round((count / total_words) * 1000.0, 2) if total_words else 0.0


def build_profile(genre: str, pass_analyses: list[dict]) -> dict:
    lengths = [n for a in pass_analyses for n in a["sentence_lengths"]]
    para_counts = [n for a in pass_analyses for n in a["per_paragraph_counts"]]
    total_words = sum(a["total_words"] for a in pass_analyses)
    openers = [w for a in pass_analyses for w in a["openers"]]

    vocab = sorted(set(openers))
    top = {}
    for w in openers:
        top[w] = top.get(w, 0) + 1
    top = dict(sorted(top.items(), key=lambda kv: (-kv[1], kv[0]))[:10])

    profile = {
        "type": "voice_fingerprint_baseline",
        "format_version": FORMAT_VERSION,
        "genre": genre,
        "passages": len(pass_analyses),
        "metrics": {
            "sentence_length": span_stats(lengths),
            "sentences_per_paragraph": span_stats(
                para_counts) if para_counts else span_stats([0]),
            "contractions_per_1000_words": _rate_meta(
                pass_analyses, "contraction_count", total_words),
            "em_dashes_per_1000_words": _rate_meta(
                pass_analyses, "em_dash_count", total_words),
            "hedges_per_1000_words": _rate_meta(
                pass_analyses, "hedge_count", total_words),
        },
        "first_word": {
            "n_sentences": len(openers),
            "vocab_size": len(vocab),
            "vocab": vocab,
            "top": top,
        },
    }
    return profile


def _deviation(draft_val: float, base: dict, relative: bool = True) -> dict:
    mean = base.get("rate", base.get("mean", 0.0))
    if "per_passage" in base:
        stdev = (base["per_passage"] or {}).get("stdev", 0.0)
    else:
        stdev = base.get("stdev", 0.0)
    delta = round(draft_val - mean, 2)
    tolerance = stdev
    if relative:
        tolerance = max(tolerance, abs(mean) * REL_TOLERANCE)
    tolerance = max(tolerance, 1e-9)
    flagged = abs(delta) > tolerance
    return {
        "baseline": mean,
        "draft": round(draft_val, 2),
        "delta": delta,
        "deviation": ("wider" if delta > 0 else "narrower") if delta else "neutral",
        "flag": flagged,
    }


def compare_draft(draft: dict, profile: dict) -> list[dict]:
    metrics = profile["metrics"]
    total = draft["total_words"]

    results = []
    for key, base in metrics.items():
        if key == "sentence_length":
            value = statistics.fmean(draft["sentence_lengths"]) if draft["sentence_lengths"] else 0.0
        elif key == "sentences_per_paragraph":
            value = (
                statistics.fmean(draft["per_paragraph_counts"])
                if draft["per_paragraph_counts"] else 0.0
            )
        elif key in ("contractions_per_1000_words", "em_dashes_per_1000_words",
                     "hedges_per_1000_words"):
            count_key = {
                "contractions_per_1000_words": "contraction_count",
                "em_dashes_per_1000_words": "em_dash_count",
                "hedges_per_1000_words": "hedge_count",
            }[key]
            value = _rate(draft[count_key], total)
        else:
            raise ValueError(f"compare: unknown baseline metric key: {key!r}")
        dev = _deviation(value, base=base)
        dev["metric"] = key
        results.append(dev)

    vocab = set(profile["first_word"]["vocab"])
    results.append(first_word_result(vocab, draft["openers"]))
    return results


def first_word_result(vocab, draft_openers):
    absent = [w for w in draft_openers if w not in vocab] if draft_openers else []
    share = (len(absent) / len(draft_openers)) if draft_openers else 0.0
    return {
        "metric": "first_word_opener",
        "baseline_vocab_size": len(vocab),
        "draft_unique_openers": len(set(draft_openers)),
        "absent_share": round(share, 3),
        "flag": share > OPENER_TOLERANCE,
        "unexpected": absent[:10],
    }


REQUIRED_PROFILE_KEYS = ("metrics", "first_word")
REQUIRED_METRIC_KEYS = (
    "sentence_length",
    "sentences_per_paragraph",
    "contractions_per_1000_words",
    "em_dashes_per_1000_words",
    "hedges_per_1000_words",
)


def validate_profile(profile) -> None:
    """Raise ValueError with a clear message on a broken/mismatched baseline.

    Guarded separately from length checks so an unknown-metric baseline is
    reported exactly and never treated as a blocked draft.
    """
    if not isinstance(profile, dict):
        raise ValueError("baseline JSON must be an object")
    missing = [k for k in REQUIRED_PROFILE_KEYS if k not in profile]
    if missing:
        raise ValueError(f"baseline missing required key(s): {', '.join(missing)}")
    if not isinstance(profile["metrics"], dict):
        raise ValueError("baseline 'metrics' must be an object")
    if not isinstance(profile["first_word"], dict):
        raise ValueError("baseline 'first_word' must be an object")
    if not isinstance(profile["first_word"].get("vocab"), list):
        raise ValueError("baseline first_word.vocab must be a list")
    missing_metrics = [k for k in REQUIRED_METRIC_KEYS if k not in profile["metrics"]]
    if missing_metrics:
        raise ValueError(
            "baseline 'metrics' missing required key(s): "
            f"{', '.join(missing_metrics)}"
        )
    for key, base in profile["metrics"].items():
        if key not in REQUIRED_METRIC_KEYS:
            raise ValueError(f"baseline contains unknown metric key: {key!r}")

def human_summary(genre: str, passages: int, results: list[dict]) -> list[str]:
    flags = [r for r in results if r.get("flag")]
    lines = [
        f"[voice fingerprint] review — divergence from your '{genre}' baseline "
        f"({passages} passage(s)). Not a quality score."
    ]
    for r in results:
        if r["metric"] == "first_word_opener":
            line = (
                f"  first-word vocabulary : {int(r['absent_share'] * 100)}% of your "
                f"openers sit outside your own baseline vocab"
            )
        else:
            line = (
                f"  {r['metric']:<28} baseline {r['baseline']:<6} draft {r['draft']:<6} delta {r['delta']:>7}"
            )
        line += "   <<review>>" if r.get("flag") else ""
        lines.append(line)
    if flags:
        lines.append(
            f"  -- {len(flags)} metric(s) moved beyond your own usual range. "
            "Review these spans in context; none of this is a verdict."
        )
    else:
        lines.append("  -- this draft stays inside your own usual range. No flag.")
    lines.append("Review only. Reference is this writer's baseline, never generic "
                 "good prose, and never an AI score.")
    return lines


def cmd_baseline(args) -> int:
    if len(args.passages) < MIN_PASSAGES:
        print(
            f"baseline needs at least {MIN_PASSAGES} accepted passages, got "
            f"{len(args.passages)}.",
            file=sys.stderr,
        )
        return 2

    analyses = []
    for p in args.passages:
        try:
            text = read_text(p)
        except ValueError as exc:
            print(f"baseline: {exc}", file=sys.stderr)
            return 2
        analysis = analyze(text)
        if analysis["total_words"] == 0:
            print(
                f"baseline: passage '{p}' contains zero tokens; an empty or "
                "non-Latin-only passage cannot count toward the baseline and is "
                "rejected. Remove it (and any silent fail would be masked).",
                file=sys.stderr,
            )
            return 2
        analyses.append(analysis)

    profile = build_profile(args.genre, analyses)
    payload = json.dumps(profile, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    else:
        print(payload)
    return 0


def cmd_compare(args) -> int:
    try:
        with open(args.baseline, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        print(f"compare: cannot read baseline: {exc}", file=sys.stderr)
        return 2
    try:
        profile = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"compare: baseline JSON is malformed: {exc}", file=sys.stderr)
        return 2

    try:
        validate_profile(profile)
    except ValueError as exc:
        print(f"compare: baseline rejected: {exc}", file=sys.stderr)
        return 2

    try:
        draft_text = read_text(args.draft)
    except ValueError as exc:
        print(f"compare: {exc}", file=sys.stderr)
        return 2
    draft = analyze(draft_text)
    coverage = draft.get("coverage")
    if coverage:
        print(f"compare: {coverage}", file=sys.stderr)

    try:
        results = compare_draft(draft, profile)
    except (ValueError, KeyError, TypeError) as exc:
        print(f"compare: {exc}", file=sys.stderr)
        return 2

    flags = [r for r in results if r.get("flag")]
    genre = profile.get("genre", "unknown")
    passages = profile.get("passages", 0)
    summary = human_summary(genre, passages, results)
    out = {
        "type": "voice_fingerprint_compare",
        "genre": genre,
        "baseline_passages": passages,
        "flags_raised": len(flags),
        "coverage": coverage,
        "metrics": results,
    }
    print(json.dumps(out, indent=2))
    if args.human:
        print("\n".join(summary), file=sys.stderr)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Voice fingerprint: screen a draft against the writer's own "
        "same-genre baseline. Screen only—no quality score, never an AI detector."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_base = sub.add_parser("baseline", help="build a profile from 3+ accepted passages")
    p_base.add_argument("--genre", default="general", help="genre label for the profile")
    p_base.add_argument("--out", default=None, help="write profile JSON to FILE")
    p_base.add_argument("passages", nargs="+", help="paths to accepted writer passages")
    p_base.set_defaults(func=cmd_baseline)

    p_comp = sub.add_parser("compare", help="screen a draft against a saved baseline")
    p_comp.add_argument("--baseline", required=True, help="path to baseline profile JSON")
    p_comp.add_argument("draft", help="path to the draft text")
    p_comp.add_argument("--human", action="store_true", help="append a human summary")
    p_comp.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())