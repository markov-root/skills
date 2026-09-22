#!/usr/bin/env python3
"""trace_map.py — deterministic renderer/validator of a per-paragraph pass.

Implements ADR 0005 / task 0008 (the "trace map / intent checksum"). It is NOT
a semantic judge of prose: the AGENT supplies every judgment as structured
data, and this script only renders the auditable table, tallies the verdicts,
flags the coherence-negative rows, and diffs the recovered one-sentence point
against the declared controlling idea (contract). It never reads or scores the
prose itself.

INPUT (JSON; file path or stdin):
    {
      "controlling_idea": "declared one-sentence contract",
      "recovered_point":  "one-sentence point recovered from the draft",
      "passes": [
        {
          "section":   "label",
          "claim":     "one-line claim",
          "advances":  "yes" | "tangent" | "restates" | "no",
          "earns_via": "evidence" | "argument" | "transition" | "color",
          "action":    "keep" | "cut" | "merge" | "rewrite"
        }
      ]
    }

Output:
  - the auditable trace table (one row per pass entry),
  - a TALLY of verdicts and a FLAG list of every tangent/restates/no row,
  - a deterministic lexical diff flag between recovered_point and
    controlling_idea.

The contract diff is STRICTLY lexical: it compares normalised surface text and
reports MATCH / PARTIAL / MISMATCH. It never infers meaning; a MISMATCH flags
unextracted intent, not bad prose. Semantic calls stay with the writer.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

VALID_ADVANCES = ("yes", "tangent", "restates", "no")
VALID_EARNS = ("evidence", "argument", "transition", "color")
VALID_ACTION = ("keep", "cut", "merge", "rewrite")
NONADVANCES = ("tangent", "restates", "no")


def _norm(value: str) -> str:
    """Lowercase, NFKD-decompose, keep unicode word chars, collapse whitespace.

    Keeping unicode `\\w` (rather than stripping to ASCII-only) means non-Latin
    scripts such as CJK survive normalisation; a fully-supplied non-empty point
    is never falsely reported as 'empty' (T2).
    """
    decomposed = unicodedata.normalize("NFKD", value)
    text = re.sub(r"[^\w\s]", "", decomposed.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def contract_diff(recovered: str, declared: str) -> dict[str, str]:
    """Lexical relation between the recovered point and the declared idea.

    Returns {"status", "detail"}. Comparisons are threshold-exact only — no
    meaning inference. A MATCH/PARTIAL leaves semantics to the writer.
    """
    a, b = _norm(recovered), _norm(declared)
    if not a or not b:
        return {
            "status": "UNPROVIDED",
            "detail": "recovered_point and/or controlling_idea is empty",
        }
    if a == b:
        return {"status": "MATCH", "detail": "normalised text identical"}
    # Token-boundary containment: space-pad both sides so a whole word match is
    # required, not a character substring (T4) — "cat" must not match "catalogue".
    if " " + a + " " in " " + b + " " or " " + b + " " in " " + a + " ":
        return {
            "status": "PARTIAL",
            "detail": "one normalised point is contained (token-boundary) in the other",
        }
    return {
        "status": "MISMATCH",
        "detail": "no normalised containment — review intent against contract",
    }


class PassValidationError(ValueError):
    pass


def validate_pass(rows: list[dict]) -> None:
    """Raise PassValidationError on the first row violating schemas."""
    for i, row in enumerate(rows, start=1):
        for key in ("section", "claim", "advances", "earns_via", "action"):
            if key not in row:
                raise PassValidationError(f"row {i}: missing '{key}'")
            val = row[key]
            # T1: every field must BE a string — a numeric/list value would
            # otherwise pass key/emptiness checks then crash at render with a
            # misleading exit-1 that collides with the flagged-rows exit code.
            if not isinstance(val, str):
                raise PassValidationError(
                    f"row {i}: '{key}' must be a string, got {type(val).__name__}"
                )
            if not val.strip():
                raise PassValidationError(f"row {i}: '{key}' is empty")
        if row["advances"] not in VALID_ADVANCES:
            raise PassValidationError(
                f"row {i}: advances={row['advances']!r} not in {VALID_ADVANCES}"
            )
        if row["earns_via"] not in VALID_EARNS:
            raise PassValidationError(
                f"row {i}: earns_via={row['earns_via']!r} not in {VALID_EARNS}"
            )
        if row["action"] not in VALID_ACTION:
            raise PassValidationError(
                f"row {i}: action={row['action']!r} not in {VALID_ACTION}"
            )


def tally(rows: list[dict]) -> dict[str, int]:
    """Count rows by their `advances` verdict."""
    counts = {k: 0 for k in VALID_ADVANCES}
    for row in rows:
        counts[row["advances"]] += 1
    return counts


def flagged(rows: list[dict]) -> list[dict]:
    """Rows whose verdict is tangent, restates, or no (not 'yes')."""
    return [r for r in rows if r["advances"] in NONADVANCES]


def render_table(rows: list[dict]) -> list[str]:
    header = "| § | section | claim | advances | earns_via | action |"
    sep = "|---|---|---|---|---|---|"
    lines = [header, sep]
    for i, row in enumerate(rows, start=1):
        claim = row["claim"].replace("|", "\\|")
        lines.append(
            f"| {i} | {row['section'].replace('|', '\\|')} | {claim} "
            f"| {row['advances']} | {row['earns_via']} | {row['action']} |"
        )
    return lines


def flag_entries(rows: list[dict]) -> list[tuple[int, dict]]:
    """Return (1-based_index, row) for every row whose verdict is non-yes."""
    return [
        (i, r)
        for i, r in enumerate(rows, start=1)
        if r["advances"] in NONADVANCES
    ]


def render_report(
    rows: list[dict], recovered: str | None, declared: str | None
) -> list[str]:
    out = ["TRACE MAP", ""]
    out.extend(render_table(rows))
    counts = tally(rows)
    flag_rows = flag_entries(rows)
    coherent = counts["yes"]
    out += ["", "TALLY", f"  {len(rows)} rows", f"  advances {dict(counts)}"]
    if coherent == len(rows) and len(rows) > 0:
        out.append("  verdict: every row advances the controlling idea.")
    else:
        out.append(
            f"  verdict: {len(rows) - coherent} of {len(rows)} rows do not advance the controlling idea."
        )
    if flag_rows:
        out += [
            "",
            "FLAG — rows that do not 'advance' the controlling idea (tangent/restates/no):",
        ]
        # Enumerate once and carry the real index — `rows.index(r)` returns the
        # FIRST equal row when duplicates exist, mislabelling every FLAG href (T5).
        for i, r in flag_rows:
            out.append(f"  · §{i} [{r['section']}] {r['advances']} / {r['action']}")
    else:
        out += ["", "FLAG — none: every row advances the controlling idea."]

    diff = contract_diff(recovered or "", declared or "")
    out += [
        "",
        "CONTROLLING-IDEA DIFF",
        f"  {diff['status']}: {diff['detail']}",
    ]
    return out


def _read_source(path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Render the auditable trace map from a structured per-¶pass JSON. "
            "Deterministic renderer/validator — never judges prose itself."
        )
    )
    ap.add_argument(
        "path", nargs="?", default=None, help="JSON file to read (default: stdin)"
    )
    ap.add_argument("--json", action="store_true", help="emit a machine report")
    args = ap.parse_args(argv)

    try:
        data = json.loads(_read_source(args.path))
    except json.JSONDecodeError as exc:
        print(f"trace_map: invalid JSON: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # T3: missing file / directory → clean stderr + exit 2 (never a
        # traceback exit-1 that collides with the flagged-rows exit code).
        print(f"trace_map: cannot read '{args.path}': {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("trace_map: top-level must be an object", file=sys.stderr)
        return 2

    # T6: top-level contract fields must be strings when present — a non-string
    # here must not silently degrade to UNPROVIDED/exit-0.
    for key in ("controlling_idea", "recovered_point"):
        if key in data and data[key] is not None and not isinstance(data[key], str):
            print(
                f"trace_map: '{key}' must be a string, got {type(data[key]).__name__}",
                file=sys.stderr,
            )
            return 2

    rows = data.get("passes")
    if not isinstance(rows, list):
        print("trace_map: 'passes' must be an array", file=sys.stderr)
        return 2
    try:
        validate_pass(rows)
    except PassValidationError as exc:
        print(f"trace_map: validation error: {exc}", file=sys.stderr)
        return 2

    declared = data.get("controlling_idea")
    recovered = data.get("recovered_point")
    declared = declared if isinstance(declared, str) and declared.strip() else None
    recovered = recovered if isinstance(recovered, str) and recovered.strip() else None

    for line in render_report(rows, recovered, declared):
        print(line)

    if args.json:
        record = {
            "controlling_idea": declared,
            "recovered_point": recovered,
            "rows": len(rows),
            "tally": tally(rows),
            "flagged": [
                {
                    "section": r["section"],
                    "advances": r["advances"],
                    "action": r["action"],
                }
                for r in flagged(rows)
            ],
            "controlling_idea_diff": contract_diff(recovered or "", declared or ""),
        }
        print(json.dumps(record, ensure_ascii=False, indent=2))

    return 1 if flagged(rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())