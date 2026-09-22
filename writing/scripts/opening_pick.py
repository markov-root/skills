#!/usr/bin/env python3
"""opening_pick.py — deterministic blind-pick ballot for alternative openings.

Implements ADR 0001 / task 0011 (the "alternative-opening generator + blind
pick"). The GENERATION of openings is a model judgment and does not live here;
this script supplies only the deterministic blind-pick *mechanics*:

  1. Accepts a controlling idea plus N candidate openings (3-5), each tagged
     with a type from {claim, question, scene, counterintuitive_fact}.
  2. STRIPS the type labels and any model-ordering signal, deterministically
     shuffles the openings (seeded), and presents them as an anonymised ballot
     (option letters). This is what lets the human pick without being biased by
     the model's safe-default ordering.
  3. Records the blind pick, then REVEALS which opening and which type it maps
     back to.
  4. Emits a note to thread the chosen opening through the trace map
     (trace_map.py): the chosen opening fixes the draft's opening image/question,
     and its controlling claim must appear in the per-passage rows.

The seed is part of the contract: a pick is only meaningful against the ballot
it was made from, so `--pick` without `--seed` is rejected, and a pick letter
outside the ballot's actual size is rejected cleanly. Ballot seeding is meant to
be chosen outside the model so the model cannot pre-compose so its favourite
lands under the same letter.

Deterministic (seeded), stdlib-only, offline. It never writes or judges an
opening itself.

INPUT (JSON; file path or stdin):
    {
      "controlling_idea": "one-sentence draft contract",
      "openings": [
        {"type": "claim", "text": "..."},
        {"type": "question", "text": "..."},
        {"type": "scene", "text": "..."},
        {"type": "counterintuitive_fact", "text": "..."}
      ]
    }

CLI:
    opening_pick.py INPUT.JSON [--seed N] [--pick A|B|C|D|E] [--json] [--reveal]
    --pick requires --seed; a pick outside the ballot fires exit 2.
"""

from __future__ import annotations

import argparse
import json
import random
import sys

VALID_TYPES = ("claim", "question", "scene", "counterintuitive_fact")
MIN_OPENINGS = 3
MAX_OPENINGS = 5
LABELS = "ABCDEFGHIJ"[:MAX_OPENINGS]


def validate_openings(openings):
    """Return normalized openings or raise ValueError with a clear message.

    Also returns a list of duplicate texts (verbatim) as a review warning so the
    caller can surface them; duplicate texts are legal but worth flagging.
    """
    if not isinstance(openings, list):
        raise ValueError("'openings' must be an array")
    n = len(openings)
    if not (MIN_OPENINGS <= n <= MAX_OPENINGS):
        raise ValueError(
            f"need {MIN_OPENINGS}-{MAX_OPENINGS} openings, got {n}"
        )
    seen = {}
    duplicates = []
    for i, item in enumerate(openings, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"opening {i}: must be an object")
        if "text" not in item or not isinstance(item["text"], str) or not item["text"].strip():
            raise ValueError(f"opening {i}: missing non-empty 'text'")
        t = item.get("type")
        if t not in VALID_TYPES:
            raise ValueError(
                f"opening {i}: type={t!r} not in {VALID_TYPES}"
            )
        norm = _norm_text(item["text"])
        if norm in seen:
            if seen[norm] not in duplicates:
                duplicates.append(seen[norm])
        else:
            seen[norm] = i
    return openings, duplicates


def _norm_text(text):
    import re

    return re.sub(r"\s+", " ", text.strip().lower())


def make_ballot(openings, seed=None):
    """Anonymise + deterministically shuffle openings into a per-option ballot.

    Returns a list of dicts with keys: label ('A'..), text. The original order
    is retained only in a hidden 'index' for the reveal (it is a transport
    detail, never shown on the ballot). Same seed always produces the same
    label->text assignment.
    """
    rng = random.Random(seed)
    items = list(enumerate(openings))  # (original_index, opening)
    rng.shuffle(items)
    ballot = []
    for opt_i, (orig_i, opening) in enumerate(items):
        ballot.append(
            {
                "label": LABELS[opt_i],
                "text": opening["text"],
                "_index": orig_i,
            }
        )
    return ballot


def blind_pick(openings, seed=None, pick_option=None):
    """Run the ballot: return record with ballot, chosen option, reveal.

    When `pick_option` is None, the ballot is presented and the *human* chooses
    after seeing the anonymised order. When provided, it must be a label that is
    actually on the ballot (a label beyond the ballot's size raises ValueError).
    Reveal maps the chosen label back to the original opening and its type.
    """
    b = make_ballot(openings, seed)
    chosen = next((x for x in b if x["label"] == (pick_option or "")), None)
    if not chosen and pick_option:
        raise ValueError(
            f"pick option {pick_option!r} is not on the ballot "
            f"(only {len(b)} option(s): {', '.join(o['label'] for o in b)})"
        )
    revealed = None
    if chosen:
        orig = openings[chosen["_index"]]
        revealed = {
            "label": chosen["label"],
            "index": chosen["_index"],
            "type": orig["type"],
            "text": orig["text"],
        }
    return {"ballot": b, "chosen_label": chosen["label"] if chosen else None,
            "revealed": revealed}


def render_ballot(ballot):
    lines = ["BLIND PICK — openings are anonymised and shuffled. Choose one."]
    for opt in ballot:
        safe = opt["text"].replace("\n", " ")
        lines.append(f"  [{opt['label']}] {safe}")
    lines.append("  (choose by letter; the mapping to type/origin is hidden.)")
    return lines


def trace_map_note(controlling_idea, chosen_type):
    return (
        f"TRACE-MAP NOTE: thread the chosen {chosen_type} opening through "
        "trace_map.py. Make the opening's claim the recovered opening of the "
        f"draft whose controlling idea is '{controlling_idea}'; ensure that "
        "claim appears in the per-passage rows that advance it."
    )


def _read_source(path):
    """Guard every file read: OSError is reported cleanly, never a traceback."""
    if path is None or path == "-":
        return sys.stdin.read()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}")


def render_human(record, controlling_idea, show_ballot=True):
    lines = []
    if record["revealed"]:
        r = record["revealed"]
        lines.append(f"BLIND PICK :: option [{r['label']}] revealed")
        lines.append(f"  type: {r['type']}")
        lines.append(f"  opening: {r['text']}")
        lines.append(trace_map_note(controlling_idea, r["type"]))
    else:
        lines.append("BLIND PICK :: no pick recorded (--pick) — the ballot is live.")
        if show_ballot:
            lines.extend(render_ballot(record["ballot"]))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=(
            "Blind-pick mechanics for alternative openings. Deterministic "
            "ballot, labels stripped+shuffled; reveal maps the blind pick back "
            "to the chosen opening type. Sends a trace-map note."
        )
    )
    ap.add_argument("path", nargs="?", default=None,
                    help="JSON file (default: stdin)")
    ap.add_argument("--seed", type=int, default=None,
                    help="deterministic shuffle seed (required with --pick)")
    ap.add_argument("--pick", choices=list(LABELS), default=None,
                    help="blind pick letter (A..E); requires --seed")
    ap.add_argument("--reveal", action="store_true",
                    help="always print the revealed opening (even if not --json)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable record")
    args = ap.parse_args(argv)

    # O1: a pick is only meaningful against the two sides of the SAME seeded
    # ballot. Without --seed the ballot reshuffles on every run, so a seedless
    # --pick would silently reveal the WRONG opening.
    if args.pick is not None and args.seed is None:
        print(
            "opening_pick: --pick requires --seed — without a fixed seed the "
            "ballot is reshuffled each run and the reveal would point at the "
            "wrong opening. Provide --seed (chosen outside the model).",
            file=sys.stderr,
        )
        return 2
    # O3: it is contradictory to ask to reveal without having picked.
    if args.reveal and args.pick is None:
        print(
            "opening_pick: --reveal with no --pick is contradictory (there is "
            "no pick to reveal). Provide both --seed and --pick, or drop "
            "--reveal to print the anonymised ballot only.",
            file=sys.stderr,
        )
        return 2

    try:
        raw = _read_source(args.path)
    except ValueError as exc:
        print(f"opening_pick: {exc}", file=sys.stderr)
        return 2
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"opening_pick: invalid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("opening_pick: top-level must be an object", file=sys.stderr)
        return 2

    controlling = data.get("controlling_idea")
    if not isinstance(controlling, str) or not controlling.strip():
        print("opening_pick: 'controlling_idea' is required and non-empty",
              file=sys.stderr)
        return 2
    openings = data.get("openings")
    try:
        openings, duplicates = validate_openings(openings)
    except ValueError as exc:
        print(f"opening_pick: validation error: {exc}", file=sys.stderr)
        return 2

    if duplicates:
        print(
            f"opening_pick: warning: duplicate opening text(s) at input position(s) "
            f"{duplicates} — this reduces the value of the blind pick.",
            file=sys.stderr,
        )

    try:
        record = blind_pick(openings, seed=args.seed, pick_option=args.pick)
    except ValueError as exc:
        print(f"opening_pick: {exc}", file=sys.stderr)
        return 2

    if args.json:
        out = {
            "controlling_idea": controlling,
            "ballot": [
                {"label": o["label"], "text": o["text"]} for o in record["ballot"]
            ],
            "chosen": record["revealed"],
            "trace_map": "thread the chosen opening through trace_map.py "
                         "(claim must appear in per-passage rows)",
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for line in render_human(record, controlling,
                                 show_ballot=not args.reveal):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())