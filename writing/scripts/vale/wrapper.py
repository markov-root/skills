#!/usr/bin/env python3
"""Thin wrapper around the Vale style pack for the writing skill.

Vale is a Go binary (not pip-installable). This wrapper:

1. Detects a `vale` binary and reports its absence gracefully (it does not crash,
   and it never fabricates findings).
2. Runs Vale against Markdown using the bundled pack (Tier-A exact phrases,
   Tier-B connectives, correlative structure, and the blocking integrity marker).
3. Masks findings that land inside **blockquotes** or **inline quotes** (Vale does
   not mask inline quotes natively), so no rule fires inside quoted or cited
   material.
4. Groups findings into three *never-merged* contracts: integrity (blocking),
   review (non-blocking), and profile (opt-in reference stats only — never an
   aggregate AI score). Every message says "review", never "AI-written".

Stdlib-only, offline, self-contained.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

PACK_ROOT = os.path.realpath(os.path.dirname(__file__))
CONFIG = os.path.join(PACK_ROOT, "writing_pack", ".vale.ini")

# Contract = threshold by Vale severity, never merged.
SEVERITY_TO_CONTRACT = {
    "error": "integrity",
    "warning": "review",
    "suggestion": "profile",
}
BLOCKING = {"integrity"}

_official_binary = "vale"


def find_vale(override=None):
    """Locate the Vale binary. Returns a path or None."""
    if override:
        return override if os.path.isfile(override) else None
    return shutil.which("vale")


# ---------------------------------------------------------------------------
# Masking helpers (Vale does not mask inline quotes; blockquote scoping is
# enforced here for every rule, including the blocking marker).
# ---------------------------------------------------------------------------

def _line_spans(text):
    """Return (start, end) absolute offsets for each physical line."""
    spans = []
    start = 0
    for raw in text.split("\n"):
        end = start + len(raw)
        spans.append((start, end))
        start = end + 1  # the newline
    return spans


def blockquote_spans(text):
    """Absolute spans of prose inside markdown blockquotes (`> ` lines)."""
    spans = []
    for m in re.finditer(r"(?m)^>[ \t]*([^\n]*)", text):
        s, e = m.start(1), m.end(1)
        if e > s:
            spans.append((s, e))
    return spans


def _pair_quotes_in_segment(segment, base, spans):
    """Pair quote delimiters within ONE paragraph segment.

    Runs with absolute offsets (base + local index). An unpaired opening quote
    is simply left unpaired — it never reaches across a paragraph boundary.
    """
    for field in ('"', "`"):
        start = None
        for i, ch in enumerate(segment):
            if ch == field:
                if start is None:
                    start = i + 1
                else:
                    spans.append((base + start, base + i))
                    start = None


def quoted_spans(text):
    """Absolute spans of inline double-quoted fragments.

    Kept conservative: single-quotes are skipped so possessives and
    contractions are never masked. Backticks are handled by Vale's Markdown
    format in most builds; the wrapper also masks them for determinism.

    Quote pairing RESETS at blank-line (paragraph) boundaries: an unpaired
    opening quote in one paragraph must never swallow fully-unquoted prose in a
    later paragraph.
    """
    spans = []
    para_re = re.compile(r"\n[ \t]*\n")
    base = 0
    for m in para_re.finditer(text):
        _pair_quotes_in_segment(text[base:m.start()], base, spans)
        base = m.end()
    _pair_quotes_in_segment(text[base:], base, spans)
    return spans


def merged_protected_spans(text):
    spans = sorted(blockquote_spans(text) + quoted_spans(text))
    if not spans:
        return []
    merged = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= merged[-1][1]:
            if b > merged[-1][1]:
                merged[-1][1] = b
        else:
            merged.append([a, b])
    return [tuple(s) for s in merged]


def locate_alert(alert, text, line_spans):
    """Absolute (start, end) for a Vale alert, or None if not locatable.

    Vale 3.x reports a per-line Span as [from, to] character offsets (absolute
    if the file is a single physical segment; relative to the line when it is
    not), plus a 1-based Line number. Try, in order: an explicit absolute span
    (a dict with from/to), then line + within-line span, then a text search for
    the matched phrase. Returns None when none succeeds so the wrapper never
    silently drops an alert.
    """
    # (a) absolute span as a dict {from, to}
    raw_span = alert.get("span")
    if isinstance(raw_span, dict):
        start = raw_span.get("from")
        end = raw_span.get("to")
        if isinstance(start, int) and isinstance(end, int):
            return start, end
    # (b) absolute span as a [start(0-based), end] pair AND a positive Line.
    if isinstance(raw_span, (list, tuple)) and len(raw_span) >= 2:
        start, end = raw_span[0], raw_span[1]
        if isinstance(start, int) and isinstance(end, int):
            line_no = alert.get("line") or alert.get("lineNumber")
            if line_no and 0 < int(line_no) <= len(line_spans):
                base = line_spans[int(line_no) - 1][0]
                return base + start, base + end
            return start, end
    # (c) line dict (vale 2.x): {col, end} with lineNumber elsewhere.
    line_info = alert.get("line")
    if isinstance(line_info, dict):
        col = line_info.get("col")
        endcol = line_info.get("end")
        line_no = alert.get("lineNumber")
        if isinstance(col, int) and line_no and 0 < int(line_no) <= len(line_spans):
            base = line_spans[int(line_no) - 1][0]
            start = base + int(col) - 1
            end = base + int(endcol) if isinstance(endcol, int) else start + 1
            return start, end
    # (d) fall back to the matched phrase text.
    phrase = alert.get("text") or alert.get("match")
    if isinstance(phrase, str) and phrase:
        matcher = re.compile(re.escape(phrase), re.IGNORECASE)
        for m in matcher.finditer(text):
            return m.start(), m.end()
    return None


def is_protected(abs_span, protected):
    s, e = abs_span if abs_span else (0, 0)
    for ps, pe in protected:
        if s < pe and ps < e:
            return True
    return False


def mask_alerts(alerts, text, protected=None):
    protected = protected if protected is not None else merged_protected_spans(text)
    line_spans = _line_spans(text)
    kept = []
    for alert in alerts:
        span = locate_alert(alert, text, line_spans)
        if span is not None and is_protected(span, protected):
            continue  # inside a quote or blockquote
        # W1: integrity findings must be anchored to a real [[SOURCE marker.
        # Vale strips the opening '[[' so over-matches plain prose; we require
        # the raw text to actually carry the brackets here.
        if alert.get("level") in ("error", "integrity") and span is not None:
            if not is_anchored_source_marker(text, span):
                continue
        out = dict(alert)
        out["located"] = span is not None
        out["masked"] = False
        kept.append(out)
    return kept


def mask_alerts_for_file(alerts, file_text):
    """Mask one file's own alerts against its OWN text (per-file offsets).

    Used for multi-file runs so signs are never located over merged text.
    """
    return mask_alerts(alerts, file_text, merged_protected_spans(file_text))


def group_by_contract(alerts):
    groups = {"integrity": [], "review": [], "profile": []}
    for alert in alerts:
        contract = SEVERITY_TO_CONTRACT.get(str(alert.get("level") or
                                                alert.get("severity") or "").lower(),
                                            "review")
        if contract == "breaking":
            contract = "integrity"
        groups.setdefault(contract, []).append(alert)
    return groups


def _normalize_keys(alert):
    """Vale's JSON uses capitalized keys (Span, Line, Check, Severity, ...).

    Fold them to lowercase so the rest of the wrapper reads one shape, and set
    `level` from `severity` so contract grouping has a single source.
    """
    out = {}
    for key, value in alert.items():
        out[key.lower()] = value
    out.setdefault("level", out.get("severity"))
    out.setdefault("text", out.get("match"))
    out.setdefault("match", out.get("text"))
    return out


def _extract_alerts_by_file(proc):
    """Return (mapping path->[normalized alerts], stderr-warning).

    Vale 3.x emits {path: [alert, ...], ...}. Preserve the per-file grouping so
    masking can happen against each file's OWN text (never merged offsets).
    """
    stderr = proc.stderr.strip()
    body = proc.stdout.strip()
    if not body:
        return {}, stderr
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        return {}, f"could not parse Vale JSON output: {exc}\n{stderr}"
    if isinstance(data, list):
        return {"<stdin>": [_normalize_keys(a) for a in data]}, stderr
    if isinstance(data, dict):
        out = {}
        for path, path_alerts in data.items():
            if isinstance(path_alerts, list):
                out[path] = [_normalize_keys(a) for a in path_alerts]
        if out or not data:
            # `data == {}` is Vale's normal zero-findings output, not an error.
            return out, stderr
    return {}, f"unexpected Vale JSON shape\n{stderr}"


def _match_file_key(vale_key, given_path):
    """Match a Vale output key to one of the requested file args.

    Vale may echo the path as passed, or normalize it (e.g. strip './').
    Accept an exact match or one being a suffix of the other.
    """
    v, g = os.path.normpath(vale_key), os.path.normpath(given_path)
    return v == g or v.endswith(g) or g.endswith(v)


_SOURCE_MARKER_RE = re.compile(r"\[\[SOURCE NEEDED")


def is_anchored_source_marker(text, span):
    """True when the located span sits on a real `[[SOURCE NEEDED` marker.

    Vale strips the `[[` wiki-link opener before its tokenizer runs, so a rule
    token 'SOURCE NEEDED' can never see the brackets — and thus over-matches any
    plain-prose mention of "SOURCE NEEDED". It also shifts the reported span by
    one char (it consumed a leading '['). We compensate here (we have the raw
    text) by checking whether the located span overlaps a genuine `[[SOURCE
    NEEDED` region; bare prose mentions are dropped.
    """
    if span is None:
        return False
    s, e = span
    for m in _SOURCE_MARKER_RE.finditer(text):
        ms = m.start()          # '[' of the opening '[['
        me = m.end()            # end of "SOURCE NEEDED"
        # Allow vale's ~2-char span shift around the marker run.
        if ms - 2 <= e and s <= me + 2:
            return True
    return False


def profile_stats(text):
    """Opt-in profile: coarse usage stats only — never a single quality score."""
    import re as _re
    words = _re.findall(r"[a-z0-9]+(?:['’-][a-z0-9]+)*", text.lower())
    sentences = [s for s in _re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    lens = [len(_re.findall(r"[a-z0-9]+", s)) for s in sentences]
    total = len(words)
    return {
        "total_words": total,
        "sentences": len(sentences),
        "mean_sentence_length": round(sum(lens) / len(lens), 2) if lens else 0.0,
        "contractions_per_1000_words": round((sum(1 for w in words if re.search(r"[’'](ll|ve|re|d|t|s|m)$", w)) / total) * 1000, 2) if total else 0.0,
    }


def human_report(groups, warnings):
    lines = []
    if warnings:
        lines.append("notice: " + "; ".join(warnings))
    for contract in ("integrity", "review", "profile"):
        alerts = groups.get(contract, [])
        if not alerts and contract != "profile":
            continue
        tag = "review (blocking)" if contract == "integrity" else (
            "review (non-blocking)" if contract == "review" else "profile (opt-in stats)")
        lines.append(f"[{tag}] {len(alerts)} finding(s)")
        for a in alerts:
            if contract == "profile":
                for k, v in a.get("stat", {}).items() if a.get("stat") else a.items():
                    if isinstance(v, (int, float)) and k != "stat":
                        lines.append(f"  {k}: {v}")
            else:
                txt = a.get("text", "")
                col = ""
                line_no = a.get("lineNumber")
                if line_no:
                    col = f" line {line_no}"
                mark = " <<review>>" if contract == "integrity" or a.get("level") else ""
                lines.append(f"  [{a.get('check_id') or a.get('check') or 'rule'}{col}] {txt}{mark}")
                msg = a.get("message")
                if msg and msg != txt:
                    lines.append(f"    {msg}")
    return "\n".join(lines)


def cmd_run(args):
    vale = find_vale(args.vale)
    if not vale:
        print(
            "ERROR: Vale binary not found. This style pack needs the Vale tool "
            "(a Go binary, not pip-installable). Install it or point VALE_BIN / "
            "--vale at the binary, then re-run. Not producing results rather than "
            "fabricating them.",
            file=sys.stderr,
        )
        return 3

    proc = _run_vale(vale, args.files, args.config, args.min_level)
    by_file, warning = _extract_alerts_by_file(proc)

    masked = []
    for f in args.files:
        file_text = _read(f)
        # collect this file's alerts, whether Vale keys it exactly or normalized
        file_alerts = []
        for vkey, alerts in by_file.items():
            if _match_file_key(vkey, f):
                file_alerts = alerts
                break
        masked.extend(mask_alerts_for_file(file_alerts, file_text))

    if args.profile:
        for f in args.files:
            masked.append({"check_id": "writing.profile", "text": f,
                           "level": "suggestion", "stat": profile_stats(_read(f))})

    groups = group_by_contract(masked)
    if args.json:
        out = {
            "type": "writing_style_pack",
            "vale_present": True,
            "files": args.files,
            "contracts": {k: (v if k != "profile" else v) for k, v in groups.items()},
        }
        print(json.dumps(out, indent=2))
    else:
        print(human_report(groups, [warning] if warning else []))
    if warning:
        print(f"notice: {warning}", file=sys.stderr)
    # W2: integrity findings are blocking — exit non-zero so a pipeline can act.
    if groups["integrity"]:
        return 1
    return 0


def _read(f):
    with open(f, encoding="utf-8") as fh:
        return fh.read()


def _run_vale(vale, files, config, minlevel):
    cmd = [vale, "--config", config or CONFIG, "--minAlertLevel", minlevel, "--output=JSON"]
    cmd += files
    return subprocess.run(cmd, capture_output=True, text=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run Vale over Markdown with the writing style pack; mask "
        "blockquotes and inline quotes; group by contract (integrity / review / "
        "profile). Review only — never an AI score."
    )
    parser.add_argument("files", nargs="+", help="Markdown files to screen")
    parser.add_argument("--vale", default=os.environ.get("VALE_BIN"),
                        help="path to the Vale binary (default: VALE_BIN env, then PATH)")
    parser.add_argument("--config", default=None, help="override .vale.ini path")
    parser.add_argument("--min-level", default="warning",
                        choices=["suggestion", "warning", "error"],
                        help="minimum Vale severity to collect")
    parser.add_argument("--profile", action="store_true",
                        help="include the opt-in profile stats contract")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return cmd_run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())