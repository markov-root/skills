#!/usr/bin/env python3
"""prompt-lint — heuristic smell-checker for a draft prompt.

Advisory only. It flags common anti-patterns from the prompt-engineering skill's reference library
(negative-only rules, vague asks, missing output contract, debunked myths, overload). It does NOT
grade quality — a clean run means "no obvious smells", not "good prompt". Run the real test: the
colleague test + a tiny eval set.

Usage:
    prompt-lint.py path/to/draft.md
    pbpaste | prompt-lint.py -            # read from stdin
    prompt-lint.py draft.md --json        # machine-readable
    prompt-lint.py AGENTS.md --lines 40:70
    git diff -- AGENTS.md | prompt-lint.py - --diff
    pbpaste | prompt-lint.py - --fragment

Exit codes: 0 = no findings · 1 = findings emitted · 2 = usage error.
No third-party dependencies (stdlib only).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Each rule: (id, severity, human message, compiled regex or predicate).
# Severity: "warn" (likely hurts) | "info" (worth a look).
MYTH_PATTERNS = [
    (r"\bi(?:'| a)?ll tip\b|\btip you\b|\$\s?\d+\s+tip|\bi will tip\b", "tipping"),
    (
        r"\bi(?:'| wi)?ll\s+(?:kill|hurt|fire|punish)\s+you\b|"
        r"\bor\s+i(?:'| wi)?ll\s+(?:kill|hurt|fire|punish)\s+you\b",
        "threat",
    ),
    (
        r"\b(?:if\s+you\s+(?:get|do|answer|make)[^.!?\n]{0,80}?\bwrong\b"
        r"[^.!?\n]{0,80}?\b)?you\s+(?:will|would|shall|'ll|are going to)\s+"
        r"(?:be\s+)?(?:fired|punished|penali[sz]ed|hurt|killed)\b",
        "threat/penalty",
    ),
]

RULES = []


def _rx(pattern, flags=re.I | re.M):
    return re.compile(pattern, flags)


# --- negative-only instruction density -------------------------------------------------
NEG_RX = _rx(r"\b(do not|don't|never|avoid|no\b(?!\s+(?:more than|fewer)))\b")
POS_VERB_RX = _rx(
    r"^\s*(?:[-*\d.]+\s*)?(?:you\s+(?:should|must|will)\s+)?"
    r"(act|analy[sz]e|answer|apply|classify|compare|compose|create|define|describe|extract|"
    r"generate|identify|list|output|produce|provide|rank|rewrite|return|summari[sz]e|translate|"
    r"use|write)\b",
    re.I | re.M,
)

# --- vague verbs / fillers -------------------------------------------------------------
VAGUE_RX = _rx(
    r"\b(some|good|nice|better|appropriate|as needed|etc\.?|and so on|stuff|things)\b"
)

# --- forced CoT ------------------------------------------------------------------------
COT_RX = _rx(
    r"\b(think step[-\s]?by[-\s]?step|let'?s think step by step|show your reasoning|"
    r"reason step by step|chain[-\s]?of[-\s]?thought|internal reasoning|scratchpad)\b"
)

# --- self-verification as gate ---------------------------------------------------------
SELFVERIFY_RX = _rx(
    r"\b(?:"
    r"(?:verify|check|critique|review)\s+(?:your own|your)\s+"
    r"(?:answer|work|output|response|reasoning)|"
    r"(?:double[-\s]?check|verify)\s+(?:the|your)\s+"
    r"(?:answer|work|output|response|reasoning)|"
    r"make\s+sure\b[\s\S]{0,120}?\bbefore\s+"
    r"(?:final|finalizing|you\s+finalize|responding)"
    r")\b"
)

# --- over-emphatic scaffolding ---------------------------------------------------------
SHOUT_RX = _rx(
    r"\b(CRITICAL|VERY IMPORTANT|YOU MUST|ABSOLUTELY|UNDER NO CIRCUMSTANCES|IMPORTANT!)\b",
    re.M,
)

# --- output-contract signals -----------------------------------------------------------
CONTRACT_RX = _rx(
    r"^\s*(?:#{1,6}\s*)?(?:output|output format|response format|format)\s*:|"
    r"\breturn\s+only\b|"
    r"\b(?:respond|return|output|provide)\s+(?:with|as|in)\s+"
    r"(?:valid\s+)?(?:json|xml|yaml|csv|a\s+table|a\s+numbered\s+list|bullets?)\b|"
    r"\b(?:json|xml|yaml)\s+schema\b|"
    r"```(?:json|yaml|xml)?|"
    r"<[a-z][\w-]*>[\s\S]*?</[a-z][\w-]*>|"
    r"\b(?:fields?|keys?|columns?)\s*:|"
    r"\b(?:allowed values|enum|one of)\s*:|"
    r"\b(?:exactly|at most|at least|no more than|no fewer than|maximum|minimum|max|min|"
    r"under|over)\s+\d+\s+(?:words?|sentences?|paragraphs?|bullets?|items?|characters?)\b|"
    r"\b\d+\s+(?:words?|sentences?|paragraphs?|bullets?|items?|characters?)\s+"
    r"(?:or\s+(?:less|fewer|more)|maximum|minimum|max|min)\b"
)

# --- unknown escape hatch --------------------------------------------------------------
IDK_RX = _rx(
    r"\b(i don'?t know|not enough information|unsure|cannot determine|insufficient "
    r"(?:context|information)|if you'?re not sure)\b"
)

# --- politeness-for-accuracy (soft) ----------------------------------------------------
POLITE_RX = _rx(r"^\s*(please\b.*){2,}", re.I | re.M)


def strip_quoted_code_spans(text: str) -> str:
    """Remove quoted/code data so local-smell rules only inspect instructions."""
    stripped = re.sub(r"(?ms)^```.*?^```", " ", text)
    stripped = re.sub(r"(?ms)^~~~.*?^~~~", " ", stripped)
    stripped = re.sub(r"`[^`\n]*`", " ", stripped)
    stripped = re.sub(r"(?m)^\s*>.*$", " ", stripped)
    stripped = re.sub(r'"[^"\n]{2,}"', " ", stripped)
    stripped = re.sub(r"(?<!\w)'[^'\n]{2,}'(?!\w)", " ", stripped)
    return stripped


def lint(text: str, *, scope: str = "document") -> list[dict]:
    if scope not in {"document", "fragment"}:
        raise ValueError(f"unknown lint scope: {scope}")
    findings: list[dict] = []
    words = max(1, len(re.findall(r"\w+", text)))
    instruction_text = strip_quoted_code_spans(text)

    def add(sev, rule, msg, fix):
        findings.append({"severity": sev, "rule": rule, "message": msg, "fix": fix})

    # Myths / coercion
    for pat, label in MYTH_PATTERNS:
        if re.search(pat, text, re.I | re.M):
            add(
                "warn",
                f"myth:{label}",
                f"Coercion/myth detected ({label}).",
                "Remove it — tipping/threats show no measurable benefit (Prompting Science Report 3).",
            )

    # Negative-only density
    neg = len(NEG_RX.findall(text))
    pos = len(POS_VERB_RX.findall(text))
    if neg >= 3 and neg > pos:
        add(
            "warn",
            "negative-only",
            f"{neg} negative rules vs {pos} positive instructions.",
            "Restate as positive 'do X' instructions; keep negatives only for hard safety/format rules.",
        )

    # Vague language
    vague = len(VAGUE_RX.findall(text))
    if vague / words > 0.02 and vague >= 3:
        add(
            "info",
            "vague",
            f"{vague} vague/filler tokens (some/good/appropriate/etc.).",
            "Replace with concrete specs: length, audience, exact criteria.",
        )

    # Forced CoT
    if COT_RX.search(instruction_text):
        add(
            "info",
            "forced-cot",
            "Explicit 'think step by step' present.",
            "On reasoning-era models this often adds latency/variance and can hurt instruction-"
            "following. Use CoT only if the task needs it; otherwise rely on the model's own thinking.",
        )

    # Self-verify as gate
    if SELFVERIFY_RX.search(instruction_text):
        add(
            "info",
            "self-verify",
            "Asks the model to verify/critique its own answer.",
            "Self-critique is a weak correctness verifier (Stechly 2025). Use an external check or a "
            "rubric; keep self-review for polish only.",
        )

    # Shouting
    shout = len(SHOUT_RX.findall(text))
    if shout >= 3:
        add(
            "info",
            "over-emphatic",
            f"{shout} CRITICAL/MUST-style emphases.",
            "Modern models over-trigger on this and bloat output. Use plain phrasing; reserve emphasis "
            "for genuine hard rules.",
        )

    # Missing output contract
    if scope == "document" and not CONTRACT_RX.search(text):
        add(
            "warn",
            "no-output-contract",
            "No explicit output format/shape detected.",
            "Specify the exact output: fields, allowed values, length, or a schema/tag. This is one of "
            "the highest-leverage additions.",
        )

    # Missing IDK hatch (only nudge for longer prompts)
    if scope == "document" and words > 60 and not IDK_RX.search(text):
        add(
            "info",
            "no-idk-hatch",
            "No 'I don't know / not enough information' escape hatch.",
            "If hallucination is a risk, permit the model to decline when unsure.",
        )

    # Politeness spam
    if POLITE_RX.search(text):
        add(
            "info",
            "politeness",
            "Multiple 'please' in one line.",
            "Politeness doesn't reliably improve accuracy (contested, mixed evidence). Be direct.",
        )

    # Overload heuristic: many imperative verbs + very long single block
    imperatives = len(POS_VERB_RX.findall(text))
    if scope == "document" and imperatives >= 8 and text.count("\n\n") <= 2:
        add(
            "info",
            "overload",
            f"{imperatives} distinct instructions in a dense block.",
            "One prompt = one responsibility. Consider decomposing/chaining, or clearly sectioning it.",
        )

    order = {"warn": 0, "info": 1}
    findings.sort(key=lambda f: order.get(f["severity"], 9))
    return findings


def parse_line_range(spec: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)(?::(\d+))?", spec)
    if not match:
        raise ValueError("line range must be N or START:END")
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if start < 1 or end < start:
        raise ValueError("line range must be one-based with END >= START")
    return start, end


def select_lines(text: str, spec: str) -> tuple[str, dict]:
    start, end = parse_line_range(spec)
    lines = text.splitlines(keepends=True)
    if end > len(lines):
        raise ValueError(f"line range {start}:{end} exceeds {len(lines)} lines")
    return "".join(lines[start - 1 : end]), {
        "kind": "lines",
        "start": start,
        "end": end,
    }


def select_diff_additions(text: str) -> tuple[str, dict]:
    additions = []
    for line in text.splitlines():
        if line.startswith("+++") or not line.startswith("+"):
            continue
        additions.append(line[1:])
    if not additions:
        raise ValueError("unified diff contains no added lines")
    return "\n".join(additions), {
        "kind": "diff_additions",
        "added_lines": len(additions),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Heuristic smell-checker for a draft prompt (advisory)."
    )
    ap.add_argument("path", help="file path, or '-' for stdin")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument(
        "--lines",
        metavar="N|START:END",
        help="lint only a one-based inclusive line range as a fragment",
    )
    scope.add_argument(
        "--diff",
        action="store_true",
        help="lint only added lines from a unified diff as a fragment",
    )
    scope.add_argument(
        "--fragment",
        action="store_true",
        help="lint the supplied text as a fragment; suppress document-completeness rules",
    )
    args = ap.parse_args(argv)

    try:
        text = (
            sys.stdin.read()
            if args.path == "-"
            else Path(args.path).read_text(encoding="utf-8")
        )
    except UnicodeError:
        source = "stdin" if args.path == "-" else args.path
        print(
            f"prompt-lint: cannot read {source}: input is not valid UTF-8",
            file=sys.stderr,
        )
        return 2
    except OSError as e:
        print(f"prompt-lint: cannot read {args.path}: {e}", file=sys.stderr)
        return 2

    selection = {"kind": "document"}
    lint_scope = "document"
    try:
        if args.lines:
            text, selection = select_lines(text, args.lines)
            lint_scope = "fragment"
        elif args.diff:
            text, selection = select_diff_additions(text)
            lint_scope = "fragment"
        elif args.fragment:
            selection = {"kind": "fragment"}
            lint_scope = "fragment"
    except ValueError as error:
        print(f"prompt-lint: invalid selection: {error}", file=sys.stderr)
        return 2

    findings = lint(text, scope=lint_scope)

    if args.json:
        print(
            json.dumps(
                {
                    "scope": lint_scope,
                    "selection": selection,
                    "findings": findings,
                    "count": len(findings),
                },
                indent=2,
            )
        )
        return 1 if findings else 0

    if not findings:
        print(
            "prompt-lint: no obvious smells. (Advisory only — still run the colleague test + an eval.)"
        )
        return 0

    icon = {"warn": "⚠", "info": "·"}
    print(
        f"prompt-lint: {len(findings)} finding(s) — advisory heuristics, not a grade.\n"
    )
    for f in findings:
        print(f"{icon.get(f['severity'], '·')} [{f['rule']}] {f['message']}")
        print(f"    → {f['fix']}\n")
    print("See the bundled knowledge/anti-patterns.md for the full rationale.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
