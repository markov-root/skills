#!/usr/bin/env python3
"""source_wall.py — the fact-integrity wall (ADR 0004).

A self-contained, deterministic, stdlib-only script that verifies MARKER
PRESENCE ONLY. It finds every source marker in a markdown/text document and
renders the "source wall": one line per unresolved marker giving the paragraph
number, source line, and the marker note.

Marker vocabulary (both equal forms; the note is OPTIONAL):
  - `[[SOURCE NEEDED]]`                      (bare)
  - `[[SOURCE NEEDED: <note>]]`
plus their unterminated open forms (no closing `]]`), per ADR 0004's call to
mark without requiring a balanced bracket.

It NEVER asserts entailment, never proposes an author/study/year/number, and
never "fixes" a marker by inventing a source. It verifies marker presence only.

Modes
-----
- default (draft):   markers are listed on the wall; exit 0 regardless.
- --final:           hard integrity failure — exit NON-ZERO while any markers
                     remain; exit 0 when none remain.

Notes on scope (documented decisions)
-------------------------------------
- Paragraph numbering counts only prose/list blocks (1-based). Heading blocks
  and fenced code blocks do NOT advance the counter. But heading markers ARE
  searched and are labelled with the ¶ number of the following prose block.
- Fenced code blocks (``` or ~~~) are excluded entirely; an unterminated fence
  at EOF warns on stderr so it cannot silently swallow later markers.
- Markers inside HTML comments (`<!-- ... -->`) ARE found — HTML comments are
  not code fences, and never false-cleaning is safer than aggressive masking.

Offline, no network, no model, no third-party deps. Reads a file path (first
positional arg) or stdin when no path is given.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# One marker = one match. The note is optional and lazily matched; the
# non-consuming lookahead stops it at a closing `]]`, the next `[[SOURCE
# NEEDED`, or end of paragraph, so markers can never consume each other (A1/A2)
# and the bare form `[[SOURCE NEEDED]]` matches with an empty note (A3).
_MARKER = re.compile(
    r"\[\[SOURCE NEEDED\s*(?::\s*)?"
    r"(?P<note>.*?)"
    r"(?:\]\])?(?=\[\[SOURCE NEEDED|(?:\]\])|$)",
    re.DOTALL,
)

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+\S")
# Fenced code delimiters: three-or-more backticks or tildes, allow indentation.
_FENCE = re.compile(r"^\s*(?:```+|~~~+)")


def _blocks(text: str) -> tuple[list[tuple[int, int, str]], bool]:
    """Split text into (start_line, end_line, kind) runs, 1-based inclusive.

    `kind` is one of `prose` (paragraphs/lists/blockquotes), `heading`, or
    `code` (fenced blocks). Blank lines separate runs. Returns the block list
    and `unterminated_fence` (True if a code fence was never closed at EOF).
    """
    lines = text.splitlines()
    raw_blocks: list[tuple[int, int, str]] = []

    def flush(current: list[int], kind: str) -> None:
        if current:
            raw_blocks.append((current[0], current[-1], kind))

    in_fence = False
    fence_lines: list[int] = []
    prose: list[int] = []
    heading: list[int] = []

    def flush_all() -> None:
        nonlocal prose, heading, fence_lines
        flush(prose, "prose")
        flush(heading, "heading")
        flush(fence_lines, "code")
        prose, heading, fence_lines = [], [], []

    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if _FENCE.match(raw):
            flush_all()
            fence_lines.append(lineno)  # the fence itself is code, not prose
            in_fence = not in_fence
            continue
        if in_fence:
            fence_lines.append(lineno)
            continue
        if not stripped:
            flush_all()
            continue
        if _HEADING.match(raw):
            heading.append(lineno)
            continue
        prose.append(lineno)

    unterminated = in_fence
    flush_all()

    # Fold consecutive code runs into one (open..close..open..close collapses).
    merged: list[tuple[int, int, str]] = []
    for start, end, kind in raw_blocks:
        if kind == "code" and merged and merged[-1][2] == "code":
            ps, pe, _ = merged[-1]
            merged[-1] = (ps, end, "code")
        else:
            merged.append((start, end, kind))
    return merged, unterminated


def _lines(text: str, start: int, end: int) -> list[str]:
    """Return source lines for a 1-based inclusive line range."""
    return text.splitlines()[start - 1 : end]


def _clean_note(note: str) -> str:
    """Flatten a note to one line and drop any leftover bracket fragments."""
    note = re.sub(r"\s*\n\s*", " / ", note)  # A3: one marker = one wall line
    return note.strip()


def _block_text(text: str, start: int, end: int) -> str:
    return "\n".join(_lines(text, start, end))


def _scan_text(para: str, start_line: int) -> list[tuple[int, str]]:
    """Return [(line_number, note), ...] markers found in one block's text."""
    found: list[tuple[int, str]] = []
    for match in _MARKER.finditer(para):
        note = _clean_note(match.group("note") or "")
        lineno = start_line + para[: match.start()].count("\n")
        found.append((lineno, note))
    return found


def parse_markers(text: str) -> list[tuple[int, int, str]]:
    """Return [(paragraph_number, line_number, marker_note), ...].

    `paragraph_number` counts only prose/list blocks (1-based). Fenced code is
    never searched. Headings ARE searched but get the ¶ number of the following
    prose block (they can carry claims). `line_number` is the 1-based source
    line where the marker begins. Ordering follows document order.
    """
    blocks, _unterminated = _blocks(text)
    entries: list[tuple[int, int, str]] = []
    para_counter = 0
    pending_headings: list[list[tuple[int, str]]] = []

    for start, end, kind in blocks:
        if kind == "prose":
            para_counter += 1
            # A heading's markers take the ¶ number of the section it opens,
            # i.e. the prose block that follows it.
            for hfound in pending_headings:
                for lineno, note in hfound:
                    entries.append((para_counter, lineno, note))
            pending_headings = []
            for lineno, note in _scan_text(_block_text(text, start, end), start):
                entries.append((para_counter, lineno, note))
        elif kind == "heading":
            pending_headings.append(_scan_text(_block_text(text, start, end), start))
        # code blocks are skipped entirely.

    # Headings with no following prose get the next (unused) ¶ number so their
    # markers are never silently swallowed.
    if pending_headings:
        para_counter += 1
        for hfound in pending_headings:
            for lineno, note in hfound:
                entries.append((para_counter, lineno, note))
    return entries


def fence_warnings(text: str) -> list[str]:
    """Warnings for structural oddities (currently: unterminated fences)."""
    _, unterminated = _blocks(text)
    if unterminated:
        return ["source_wall: warning: unterminated code fence at EOF — code "
                "content up to the end is treated as code and not searched."]
    return []


def render_wall(entries: list[tuple[int, int, str]]) -> list[str]:
    """One human-readable line per unresolved marker (`¶ N (line L)  note`)."""
    return [
        f"\u00b6 {num} (line {line})  {note}" for num, line, note in entries
    ]


def _read_source(path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Render the fact-integrity source wall. Verifies marker presence "
            "only — never fabricates a source."
        )
    )
    ap.add_argument(
        "path",
        nargs="?",
        default=None,
        help="markdown/text file to check (default: read stdin)",
    )
    ap.add_argument(
        "--final",
        action="store_true",
        help=(
            "final mode: exit non-zero while any marker remains; exit 0 when "
            "none remain"
        ),
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable JSON record alongside (after) the wall",
    )
    args = ap.parse_args(argv)

    if args.path is not None and args.path != "-":
        try:
            text = _read_source(args.path)
        except OSError as exc:
            # Clean diagnosis, exit 2 — never a traceback exit 1, so --final's
            # "non-zero == unresolved markers" stays unambiguous (A6).
            print(f"source_wall: cannot read '{args.path}': {exc}", file=sys.stderr)
            return 2
    else:
        text = _read_source(None)

    for warning in fence_warnings(text):
        print(warning, file=sys.stderr)

    entries = parse_markers(text)
    wall_lines = render_wall(entries)

    if wall_lines:
        print("SOURCE WALL")
        for line in wall_lines:
            print(line)
    else:
        print("SOURCE WALL — all clear")

    if args.json:
        record = {
            "mode": "final" if args.final else "draft",
            "path": args.path,
            "unresolved": len(entries),
            "markers": [
                {"paragraph": n, "line": line, "note": note}
                for n, line, note in entries
            ],
            "exit_code": 1 if (args.final and entries) else 0,
        }
        print(json.dumps(record, ensure_ascii=False, indent=2))

    return 1 if (args.final and entries) else 0


if __name__ == "__main__":
    raise SystemExit(main())