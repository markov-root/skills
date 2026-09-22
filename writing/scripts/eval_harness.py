#!/usr/bin/env python3
"""eval_harness.py — v1 EVAL-HARNESS STUB (ADR 0005 / task 0012).

A deterministic, stdlib-only instrument that STRUCTURES evidence for the
marginal-return evaluator (roadmap 0017). It does NOT judge prose: it emits a
blind comparison form and deterministic screens; a human/judge fills verdicts.

This stub provides, per ADR 0005:
  1. FIXED BRIEFS  — a small built-in set of representative briefs, overridable
     from a JSON file or a directory of JSON files.
  2. BLIND PAIRWISE — given two candidate outputs (A/B) for a brief, it strips
     identifying labels, deterministically randomises A/B order from a --seed,
     and emits a BLIND COMPARISON FORM over the non-tell dimensions (clarity,
     specificity, argument strength, reader pull).
  3. SOURCED-ANCHOR COUNT — counts concrete anchors (named studies / real
     numbers / dates), each paired with a source marker or resolved citation.
     Reuses source_wall.parse_markers (imported, not re-implemented). Reported
     as a SCREEN, never a score.
  4. TELL-DENSITY — a screen (divergence only), never a quality score.
  5. COMPLETION-CONTRACT CHECKLIST structure.

Strategy hooks (one-shot / one-revision / defect-driven / ordered-altitude /
panel) are carried as labels so the FULL evaluator (roadmap 0017) can compare
them budget-matched; the stub itself only runs blind-pairwise. This prevents
the circular resolution ADR 0005 prohibits — ordered-altitude is a named
comparator from day one.

Anchor summary: a concrete anchor (year, number, %, named "Surname (Year)")
is "sourced/marked" when its paragraph also contains a source marker or a
resolved citation; otherwise it is "unpaired" (a fabrication risk). This is a
SCREEN — it never awards or penalises a quality score.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys

# Reuse the marker parser from the fact-integrity wall (ADR 0004). Import via
# the sibling module; do not re-implement the [[SOURCE NEEDED]] grammar.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import source_wall  # noqa: E402

DIMENSIONS = ("clarity", "specificity", "argument_strength", "reader_pull")

# Strategies the FULL evaluator (roadmap 0017) compares budget-matched. The
# stub only labels them; ordered-altitude MUST remain a named comparator
# (ADR 0005 — dropping it made the original resolution circular).
STRATEGIES = (
    "one-shot",
    "one-revision",
    "defect-driven",
    "ordered-altitude",
    "panel",
)

BUILTIN_BRIEFS = [
    {
        "id": "b001",
        "reader": "a busy technical reader",
        "effect": "grasp the core trade-off in under 60 seconds",
        "prompt": (
            "Explain, for a busy technical reader, why the trace map makes "
            "draft coherence auditable instead of merely asserted."
        ),
    },
    {
        "id": "b002",
        "reader": "a non-technical decision-maker",
        "effect": "decide whether to adopt the new workflow",
        "prompt": (
            "Convince a non-technical decision-maker to adopt the fact-integrity "
            "discipline for a writing pipeline."
        ),
    },
    {
        "id": "b003",
        "reader": "a peer writer",
        "effect": "recognise the voice-preservation principle",
        "prompt": (
            "For a peer writer, explain why 'missing evidence is not a style "
            "defect' is the correct framing."
        ),
    },
]


# ---------------------------------------------------------------- anchors ---

# Ordered from most specific to least so named-study citations consume the
# year rather than double-counting it as a bare date.
_ANCHOR_PATTERNS = (
    (r"\b[A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)*(?:,?\s+(?:et\s+al\.?))?,?\s*\((?:19|20)\d{2}\)", "named_study"),
    (r"\b(?:19|20)\d{2}\b", "year"),
    (r"\b\d+(?:[.,]\d+)?%", "percent"),
    (r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w%])", "number"),
)

_ANCHOR_TYPES = ("named_study", "year", "percent", "number")
# A resolved citation such as "Smith (2020)" — a name followed by a parenthesised
# year. Its presence (or a [[SOURCE NEEDED]] marker) 'sources' a nearby anchor.
_CITATION = re.compile(r"\b[A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)*(?:,?\s+(?:et\s+al\.?))?,?\s*\((?:19|20)\d{2}\)")


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]


def detect_anchors(paragraph: str) -> list[dict]:
    """Return [{"type","value","pos"}, ...] anchors found in one paragraph.

    Earlier (more specific) patterns match first; consumed spans are not
    revisited, so a named-study year is not also counted as a bare year.
    Values are kept verbatim. Order is document order.
    """
    found: list[dict] = []
    used: list[tuple[int, int]] = []  # (start, end) consumed spans relative to paragraph
    for pattern, kind in _ANCHOR_PATTERNS:
        for m in re.finditer(pattern, paragraph):
            start, end = m.span()
            # Skip if this span overlaps a previously consumed (more specific) match.
            if any(start < ue and us < end for us, ue in used):
                continue
            used.append((start, end))
            found.append({"type": kind, "value": m.group(0), "pos": start})
    found.sort(key=lambda a: a["pos"])
    return found


def _paragraph_is_sourced(paragraph: str) -> tuple[bool, bool]:
    """(has_citation, has_marker) for a paragraph.

    An inline-backtick marker such as `[[SOURCE NEEDED]]` also counts as a
    source signal — source_wall.parse_markers still sees the brackets whether
    they are fenced in backticks or not.
    """
    has_citation = bool(_CITATION.search(paragraph))
    has_marker = bool(source_wall.parse_markers(paragraph))
    return has_citation, has_marker


def sourced_anchor_count(text: str) -> dict:
    """Count anchors and how many are paired with a source.

    Returns a SCREEN record — never used as a quality score:
      {
        "anchors_total": int,
        "anchors_by_type": {type: count},
        "sourced": int,      # anchors whose paragraph has a citation/marker
        "unpaired": int,     # anchors whose paragraph has neither
        "notes": ...
      }
    """
    total = 0
    by_type = {t: 0 for t in _ANCHOR_TYPES}
    sourced_anchors = 0
    unpaired = 0
    for para in _paragraphs(text):
        anchors = detect_anchors(para)
        if not anchors:
            continue
        has_citation, has_marker = _paragraph_is_sourced(para)
        paired = has_citation or has_marker
        for a in anchors:
            total += 1
            by_type[a["type"]] += 1
            if paired:
                sourced_anchors += 1
            else:
                unpaired += 1
    return {
        "anchors_total": total,
        "anchors_by_type": by_type,
        "sourced": sourced_anchors,
        "unpaired": unpaired,
    }


# --------------------------------------------------------------- a tell ---
# The stub has no author baseline, so tell-density is reported as a SCREEN:
# per-candidate feature counts and the A/B divergence magnitude. It is never a
# quality score (ADR 0005 double-Goodhart guard).

_TELL_COUNTERS = (
    ("sentences", r"[.!?](?=\s|$)"),
    ("marker_count", r"\[\[SOURCE NEEDED"),
    ("source_anchors", r"\b(?:19|20)\d{2}\b"),
)


def tell_screen(text: str, other: str) -> dict:
    """Feature counts for `text` plus divergence vs `other` — a screen only."""
    counts: dict[str, int] = {}
    for name, pat in _TELL_COUNTERS:
        counts[name] = len(re.findall(pat, text))
    other_counts = {}
    for name, pat in _TELL_COUNTERS:
        other_counts[name] = len(re.findall(pat, other))
    # Simple divergence magnitude across the shared screen features.
    divergence = round(
        sum(abs(counts[n] - other_counts[n]) for n in dict(_TELL_COUNTERS)),
        3,
    )
    return {
        "per_candidate_counts": counts,
        "divergence_from_peer": divergence,
        "screen_only": True,
        "not_a_quality_score": True,
    }


# ------------------------------------------------------------------ form ----

def blind_form(
    brief: dict, cand_a: str, cand_b: str, seed: int
) -> dict:
    """Deterministically shuffle A/B and emit the blind comparison form.

    `--seed` controls the order urn: with a fixed seed the same two candidates
    always produce the same labelled 'P'/'Q' assignment, so comparisons are
    reproducible. The form lists the four non-tell dimensions with blank
    verdicts for the judge; it never scores the prose itself.

    BLINDING (E1): the returned form contains ONLY what a judge may see — the
    brief id, the P/Q *texts*, the dimensions, and the seed. It carries NO
    answer key and NO P/Q->strategy mapping. The mapping lives in the separate
    `mapping` dict returned alongside, which the caller routes to stderr / an
    audit channel / --reveal, NEVER to the judge's page.
    """
    rng = random.Random(seed)
    order = ["A", "B"] if rng.random() < 0.5 else ["B", "A"]
    left = {"label": order[0], "text": cand_a}
    right = {"label": order[1], "text": cand_b}
    shown_order = [left["label"], right["label"]]
    mapping = {"P": shown_order[0], "Q": shown_order[1]}
    form = {
        "brief": brief["id"],
        "seed": seed,
        "candidates": [
            {"shown_as": "P", "content": left["text"]},
            {"shown_as": "Q", "content": right["text"]},
        ],
        "dimensions": [
            {
                "dimension": d,
                "verdict": None,  # judge fills: prefer P / prefer Q / tie
                "note": "",
            }
            for d in DIMENSIONS
        ],
        "judge_fills_verdicts_only": True,
    }
    return {"form": form, "mapping": mapping}


COMPLETION_CONTRACT = ("evidence_said", "residual_risk_said", "checks_ran", "veto_or_not")


def completion_checklist() -> dict:
    return {k: None for k in COMPLETION_CONTRACT}


# --------------------------------------------------------------- source ----

def _read_source(path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}")


def _resolve_briefs(override: str | None) -> list[dict]:
    """Built-in briefs, overridable by a JSON file or a directory of JSON files.

    Raises ValueError (not SystemExit) on a missing path or malformed JSON so
    the CLI can report cleanly and exit 2.
    """
    if not override:
        return BUILTIN_BRIEFS
    p = pathlib.Path(override)
    try:
        if p.is_dir():
            briefs = []
            for f in sorted(p.glob("*.json")):
                briefs.append(json.loads(f.read_text(encoding="utf-8")))
            if not briefs:
                raise ValueError(f"no JSON briefs found in directory {override}")
            return briefs
        return json.loads(p.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read briefs source: {exc}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed briefs JSON at {override}: {exc}")


def _find_brief(briefs: list[dict], brief_id: str) -> dict:
    for b in briefs:
        if b.get("id") == brief_id:
            return b
    raise ValueError(f"eval_harness: unknown brief '{brief_id}'")


# ------------------------------------------------------------------ cli ----
# Kept small: `{{candidate}}`-templating is out of scope; candidates come from
# files or stdin.


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "v1 eval-harness stub (ADR 0005). Structures blind pairwise evidence "
            "over non-tell dimensions + sourced-anchor/tell screens. Never judges prose."
        )
    )
    ap.add_argument("-b", "--brief", required=True, help="brief id (b001..)")
    ap.add_argument("--briefs-file", default=None, help="JSON file or dir overriding built-in briefs")
    ap.add_argument("--a", help="candidate A text file ('-'=stdin)")
    ap.add_argument("--b", help="candidate B text file ('-'=stdin)")
    ap.add_argument("--seed", type=int, default=0, help="deterministic shuffle seed")
    ap.add_argument("--strategy-a", default=None, choices=list(STRATEGIES), help="label for A (roadmap 0017 hook)")
    ap.add_argument("--strategy-b", default=None, choices=list(STRATEGIES), help="label for B (roadmap 0017 hook)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable record")
    ap.add_argument("--answer-file", default=None,
                    help="write the P/Q->candidate mapping to FILE (audit channel; "
                         "never shown to the judge)")
    ap.add_argument("--reveal", action="store_true",
                    help="after the judge channel, print the P/Q->candidate mapping "
                         "to stderr")
    args = ap.parse_args(argv)

    if args.a is None or args.b is None:
        print("eval_harness: both --a and --b are required", file=sys.stderr)
        return 2

    try:
        cand_a = _read_source(args.a)
        cand_b = _read_source(args.b)
        brief = _find_brief(_resolve_briefs(args.briefs_file), args.brief)
    except ValueError as exc:
        print(f"eval_harness: {exc}", file=sys.stderr)
        return 2

    brief = dict(brief)
    brief["strategy_a"] = args.strategy_a
    brief["strategy_b"] = args.strategy_b

    blind = blind_form(brief, cand_a, cand_b, args.seed)
    form = blind["form"]
    mapping = blind["mapping"]

    anchors_a = sourced_anchor_count(cand_a)
    anchors_b = sourced_anchor_count(cand_b)
    tells_a = tell_screen(cand_a, cand_b)
    tells_b = tell_screen(cand_b, cand_a)

    # ---- judge channel (stdout): brief, P/Q TEXT, dimensions, screens. NO mapping.
    p_text = next(c["content"] for c in form["candidates"] if c["shown_as"] == "P")
    q_text = next(c["content"] for c in form["candidates"] if c["shown_as"] == "Q")
    out: list[str] = []
    out.append(f"EVAL — brief {brief['id']} ({brief.get('reader','')})")
    out.append(f"  prompt: {brief.get('prompt','')}")
    out.append("")
    out.append("CANDIDATES (the texts only — identity and provenance are never shown here):")
    out.append(f"  P: {p_text}")
    out.append(f"  Q: {q_text}")
    out.append("")
    out.append("BLIND COMPARISON FORM (judge fills verdicts; P/Q order is seeded = "
               f"{form['seed']})")
    out.append("  dimensions (verdict: prefer P / prefer Q / tie):")
    for d in form["dimensions"]:
        out.append(f"    - {d['dimension']}: [ ]")
    out.append("")
    out.append("SOURCED-ANCHOR SCREEN (not a score):")
    out.append(f"  A: {anchors_a['anchors_total']} anchors, {anchors_a['sourced']} sourced, {anchors_a['unpaired']} unpaired")
    out.append(f"  B: {anchors_b['anchors_total']} anchors, {anchors_b['sourced']} sourced, {anchors_b['unpaired']} unpaired")
    out.append("")
    out.append("TELL-DENSITY SCREEN (divergence only, not a score):")
    out.append(f"  A: {tells_a['per_candidate_counts']} (divergence {tells_a['divergence_from_peer']})")
    out.append(f"  B: {tells_b['per_candidate_counts']} (divergence {tells_b['divergence_from_peer']})")
    out.append("")
    out.append("COMPLETION-CONTRACT CHECKLIST (structure):")
    for key in COMPLETION_CONTRACT:
        out.append(f"    [ ] {key}")
    print("\n".join(out))

    # ---- judge-facing --json record: blank verdicts + texts, NO mapping.
    if args.json:
        record = {
            "brief": brief["id"],
            "seed": args.seed,
            "candidates": [
                {"shown_as": "P", "content": p_text},
                {"shown_as": "Q", "content": q_text},
            ],
            "dimensions": DIMENSIONS,
            "anchors": {"A": anchors_a, "B": anchors_b},
            "tells": {"A": tells_a, "B": tells_b},
            "completion_checklist": completion_checklist(),
        }
        print(json.dumps(record, ensure_ascii=False, indent=2))

    # ---- audit channel (stderr unless a file is given): mapping + strategies.
    audit_lines = (
        f"eval_harness audit (NOT for the judge): P->{mapping['P']}, Q->{mapping['Q']}; "
        f"strategies A<-{args.strategy_a or 'unlabelled'}, B<-{args.strategy_b or 'unlabelled'}"
    )
    if args.answer_file:
        try:
            with open(args.answer_file, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"seed": args.seed, "mapping": mapping,
                                     "strategies": {"A": args.strategy_a,
                                                    "B": args.strategy_b}},
                                    indent=2) + "\n")
        except OSError as exc:
            print(f"eval_harness: cannot write answer file: {exc}", file=sys.stderr)
            return 2
    elif args.reveal:
        print(audit_lines, file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())