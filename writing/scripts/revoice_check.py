#!/usr/bin/env python3
"""Lossless re-voice preservation check for slide-sectioned scripts.

A re-voice pass may change how a script sounds; it must not lose what the script
says. This deterministic, stdlib-only tool compares two versions of a script
(Markdown: ``## <slide-id>`` headings, each followed by spoken paragraphs) and
reports everything present in BEFORE that is missing or altered in AFTER:

* slide headings (``## id``) that were dropped; headings new in AFTER are
  reported as ``added`` (information, not loss);
* numbers, compared per slide as multisets: digits with thousands separators or
  decimals, percentages, currency amounts with a scale word (``$2.5 billion``),
  ordinals (``80th``), and bare years. A number that leaves its slide is lost
  from that slide even if it reappears elsewhere. When the slide also gained a
  number it did not have, the pair is reported as ``altered``;
* direct quotations (straight or curly double quotes, three words or more).
  A missing quotation is ``altered`` when the same slide gained a quotation with
  ``difflib`` ratio >= 0.6, otherwise ``missing``;
* with ``--annotations``: each stand-off anchor (``slide`` + ``quote``) whose
  quoted span, exact or whitespace/punctuation/case-normalised, no longer
  appears in AFTER's section for that slide is ``orphaned``.

The content of a slide whose heading was dropped is compared against the whole
of AFTER instead: the heading loss is already reported, and the surviving words
usually merged into a neighbouring slide.

The annotations file is a YAML list of flat mappings. Only that subset is
parsed (no third-party YAML parser): ``- key: value`` / ``  key: value`` lines,
plain, single- or double-quoted scalars, ``[]``/``{}`` for empty, ``#``
comments, and folded continuation lines. Anything else exits 2.

Exit 0 = lossless, 1 = loss found, 2 = usage error or unreadable input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

TOOL = "revoice_check"
FORMAT_VERSION = 1
ALTERED_MIN_RATIO = 0.6
MIN_QUOTE_WORDS = 3

HEADING = re.compile(r"^##[ \t]+(.*?)[ \t]*#*[ \t]*$")
FENCE = re.compile(r"^\s*(```|~~~)")
NUMBER = re.compile(
    r"(?<![\w.,])"
    r"(?:[$€£¥]\s?)?"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)"
    r"(?:\.\d+)?"
    r"(?:\s?%|(?:st|nd|rd|th)\b)?"
    r"(?:\s+(?:thousand|million|billion|trillion)\b)?",
    re.IGNORECASE,
)
QUOTE = re.compile(
    r"\"((?:[^\"\n]|\n(?![ \t]*\n))+?)\""
    r"|“((?:[^“”\n]|\n(?![ \t]*\n))+?)”"
)
KEEP = "%$€£"


class InputError(Exception):
    """Unreadable or unparseable input (exit 2)."""


# --------------------------------------------------------------------------- parsing


def parse_sections(text: str) -> list[tuple[str | None, str]]:
    """Split a script into (slide id, body) in document order.

    Text before the first heading becomes a section with id ``None``. Only
    level-2 ATX headings outside code fences open a section.
    """
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else HEADING.match(line)
        if m and m.group(1):
            sections.append((m.group(1), []))
        else:
            sections[-1][1].append(line)
    out = [(sid, "\n".join(body)) for sid, body in sections]
    if out[0][0] is None and not out[0][1].strip():
        out.pop(0)
    return out


def squash(text: str) -> str:
    return " ".join(text.split())


def numbers(body: str) -> list[str]:
    return [squash(m.group(0)) for m in NUMBER.finditer(body)]


def quotations(body: str) -> list[str]:
    out = []
    for m in QUOTE.finditer(body):
        inner = squash(m.group(1) if m.group(1) is not None else m.group(2))
        if len(inner.split()) >= MIN_QUOTE_WORDS:
            out.append(inner)
    return out


def quote_key(q: str) -> str:
    """Comparison key: whitespace collapsed and apostrophe style unified."""
    return squash(q.replace("’", "'").replace("‘", "'"))


def _normal_char(ch: str) -> str:
    if ch.isspace():
        return " "
    if ch in KEEP:
        return ch
    if unicodedata.category(ch) == "Pd" or ch in "/…":
        return " "
    if unicodedata.category(ch)[0] in "PS":
        return ""
    base = unicodedata.normalize("NFKD", ch)
    return "".join(c for c in base if not unicodedata.combining(c)).casefold()


def normalise(text: str) -> str:
    """Case-folded, accent- and punctuation-stripped, whitespace-collapsed text."""
    return squash("".join(_normal_char(ch) for ch in text))


# --------------------------------------------------------------------------- annotations


def _scalar(raw: str, where: str) -> Any:
    v = raw.strip()
    if v in ("[]", "{}"):
        return [] if v == "[]" else {}
    if v.startswith('"'):
        m = re.fullmatch(r'("(?:[^"\\]|\\.)*")\s*(?:#.*)?', v)
        if not m:
            raise InputError(f"{where}: malformed double-quoted string")
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            # YAML escapes json lacks (e.g. "\'" or "\ "); keep the common cases.
            return m.group(1)[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if v.startswith("'"):
        m = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", v)
        if not m:
            raise InputError(f"{where}: malformed single-quoted string")
        return m.group(1).replace("''", "'")
    if v[:1] in ("|", ">", "[", "{", "&", "*", "!"):
        raise InputError(f"{where}: unsupported YAML construct {v[:1]!r}")
    v = re.sub(r"\s+#.*$", "", v)
    return v


def _open_quote(raw: str) -> bool:
    """True when a quoted scalar starts on this line but does not end on it."""
    v = raw.strip()
    if v.startswith('"'):
        body = v[1:]
        i, closed = 0, False
        while i < len(body):
            if body[i] == "\\":
                i += 2
                continue
            if body[i] == '"':
                closed = True
                break
            i += 1
        return not closed
    if v.startswith("'"):
        return not re.fullmatch(r"'(?:[^']|'')*'\s*(#.*)?", v)
    return False


KEY = re.compile(r"^([A-Za-z_][\w-]*)\s*:(?:\s+(.*)|\s*)$")


def parse_annotations(text: str) -> list[dict[str, Any]]:
    """Parse the flat-mapping-list YAML subset used by stand-off annotations."""
    items: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    pending: tuple[str, list[str], int] | None = (
        None  # key, raw value lines, key column
    )
    item_indent: int | None = None
    started = False

    def close_pending() -> None:
        nonlocal pending
        if pending is None or cur is None:
            return
        key, parts, _ = pending
        where = f"annotation {len(items) - 1} key {key!r}"
        first = parts[0].strip()
        if first.startswith('"'):
            joined = first
            for p in parts[1:]:
                joined = (
                    joined[:-1] + p.strip()
                    if joined.endswith("\\")
                    else f"{joined} {p.strip()}"
                )
            cur[key] = _scalar(joined, where)
        else:
            joined = " ".join(p.strip() for p in parts if p.strip())
            cur[key] = _scalar(joined, where) if joined else None
        pending = None

    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if pending is not None:
            if _open_quote(" ".join(pending[1])) or (
                stripped and indent > pending[2] and not stripped.startswith("#")
            ):
                pending[1].append(line)
                continue
        if not stripped or stripped.startswith("#") or stripped in ("---", "..."):
            continue
        if line[:1] == "\t" or "\t" in line[: indent + 1]:
            raise InputError(f"annotations line {n}: tab indentation")
        if not started:
            started = True
            if stripped == "[]":
                return []
            m = KEY.match(stripped)
            if indent == 0 and m and not m.group(2):
                continue  # tolerate one wrapping key, e.g. "annotations:"
        if stripped == "-" or stripped.startswith("- "):
            close_pending()
            if item_indent is None:
                item_indent = indent
            elif indent != item_indent:
                raise InputError(
                    f"annotations line {n}: nested lists are not supported"
                )
            cur = {}
            items.append(cur)
            rest = stripped[1:].strip()
            if not rest:
                continue
            m = KEY.match(rest)
            if not m:
                raise InputError(
                    f"annotations line {n}: expected 'key: value' after '-'"
                )
            pending = (m.group(1), [m.group(2) or ""], indent + 2)
            continue
        m = KEY.match(stripped)
        if m and cur is not None and item_indent is not None and indent > item_indent:
            close_pending()
            pending = (m.group(1), [m.group(2) or ""], indent)
            continue
        raise InputError(
            f"annotations line {n}: not a flat list of mappings: {stripped!r}"
        )
    close_pending()
    for i, item in enumerate(items):
        for key in ("slide", "quote"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise InputError(f"annotation {i}: missing string {key!r}")
    return items


# --------------------------------------------------------------------------- comparison


def _diff(
    before: list[str], after: list[str], key=lambda s: s
) -> tuple[list[str], list[str]]:
    """Items of `before` not matched in `after` (and vice versa), in position order."""
    remaining = Counter(key(a) for a in after)
    lost = []
    for b in before:
        k = key(b)
        if remaining[k] > 0:
            remaining[k] -= 1
        else:
            lost.append(b)
    have = Counter(key(b) for b in before)
    gained = []
    for a in after:
        k = key(a)
        if have[k] > 0:
            have[k] -= 1
        else:
            gained.append(a)
    return lost, gained


def compare(
    before_text: str, after_text: str, annotations: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    before = parse_sections(before_text)
    after = parse_sections(after_text)
    after_by: dict[str | None, list[str]] = {}
    for sid, body in after:
        after_by.setdefault(sid, []).append(body)
    after_ids = Counter(sid for sid, _ in after if sid is not None)
    before_ids = Counter(sid for sid, _ in before if sid is not None)
    whole_after = "\n\n".join(body for _, body in after)

    losses: list[dict[str, Any]] = []
    counts = {
        "headings": {"before": sum(before_ids.values()), "kept": 0},
        "numbers": {"before": 0, "kept": 0},
        "quotations": {"before": 0, "kept": 0},
        "anchors": {"checked": 0, "orphaned": 0},
    }

    seen: Counter[str] = Counter()
    for sid, body in before:
        dropped = False
        if sid is not None:
            seen[sid] += 1
            if seen[sid] > after_ids[sid]:
                dropped = True
                losses.append(
                    {
                        "type": "heading",
                        "slide": sid,
                        "value": sid,
                        "change": "missing",
                        "after": None,
                    }
                )
            else:
                counts["headings"]["kept"] += 1
        # Duplicate ids share their combined AFTER content; a dropped slide
        # is checked against the whole of AFTER.
        target = whole_after if dropped else "\n\n".join(after_by.get(sid, []))

        b_nums, a_nums = numbers(body), numbers(target)
        lost, gained = _diff(b_nums, a_nums)
        counts["numbers"]["before"] += len(b_nums)
        counts["numbers"]["kept"] += len(b_nums) - len(lost)
        for i, value in enumerate(lost):
            alt = gained[i] if (i < len(gained) and not dropped) else None
            losses.append(
                {
                    "type": "number",
                    "slide": sid,
                    "value": value,
                    "change": "altered" if alt else "missing",
                    "after": alt,
                }
            )

        b_q, a_q = quotations(body), quotations(target)
        lost_q, gained_q = _diff(b_q, a_q, key=quote_key)
        counts["quotations"]["before"] += len(b_q)
        counts["quotations"]["kept"] += len(b_q) - len(lost_q)
        used: set[int] = set()
        for value in lost_q:
            best, best_i = 0.0, None
            if not dropped:
                for j, cand in enumerate(gained_q):
                    if j in used:
                        continue
                    r = SequenceMatcher(
                        None, quote_key(value), quote_key(cand), autojunk=False
                    ).ratio()
                    if r > best + 1e-12:
                        best, best_i = r, j
            if best_i is not None and best >= ALTERED_MIN_RATIO:
                used.add(best_i)
                losses.append(
                    {
                        "type": "quotation",
                        "slide": sid,
                        "value": value,
                        "change": "altered",
                        "after": gained_q[best_i],
                    }
                )
            else:
                losses.append(
                    {
                        "type": "quotation",
                        "slide": sid,
                        "value": value,
                        "change": "missing",
                        "after": None,
                    }
                )

    if annotations is not None:
        for ann in annotations:
            counts["anchors"]["checked"] += 1
            slide, quote = ann["slide"], ann["quote"]
            section = "\n\n".join(after_by.get(slide, []))
            nq = normalise(quote)
            if section and (quote in section or (nq and nq in normalise(section))):
                continue
            counts["anchors"]["orphaned"] += 1
            losses.append(
                {
                    "type": "anchor",
                    "slide": slide,
                    "value": quote,
                    "change": "orphaned",
                    "after": None,
                }
            )

    added = []
    seen_after: Counter[str] = Counter()
    for sid, _ in after:
        if sid is None:
            continue
        seen_after[sid] += 1
        if seen_after[sid] > before_ids[sid]:
            added.append({"type": "heading", "value": sid})

    return {
        "tool": TOOL,
        "version": FORMAT_VERSION,
        "lossless": not losses,
        "losses": losses,
        "added": added,
        "counts": counts,
    }


# --------------------------------------------------------------------------- output


def summary(result: dict[str, Any]) -> str:
    c = result["counts"]
    parts = [
        f"numbers {c['numbers']['kept']}/{c['numbers']['before']}",
        f"quotations {c['quotations']['kept']}/{c['quotations']['before']}",
        f"headings {c['headings']['kept']}/{c['headings']['before']}",
    ]
    a = c["anchors"]
    if a["checked"]:
        parts.append(f"anchors {a['checked'] - a['orphaned']}/{a['checked']}")
    n = len(result["losses"])
    verdict = "lossless" if result["lossless"] else f"{n} loss{'es' if n != 1 else ''}"
    lines = [", ".join(parts) + " — " + verdict]
    for loss in result["losses"]:
        where = f"[{loss['slide']}]" if loss["slide"] is not None else "[preamble]"
        line = f"  {loss['type']} {loss['change']} {where} {loss['value']!r}"
        if loss["after"] is not None:
            line += f" -> {loss['after']!r}"
        lines.append(line)
    for add in result["added"]:
        lines.append(f"  (info) heading added [{add['value']}]")
    return "\n".join(lines)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc


class _Parser(argparse.ArgumentParser):
    def error(
        self, message: str
    ) -> None:  # usage errors exit 2 (argparse default, kept explicit)
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    p = _Parser(
        prog="revoice_check.py",
        description="Report numbers, quotations, slide headings and annotation anchors a re-voiced script lost.",
    )
    p.add_argument("--json", action="store_true", help="print one JSON object")
    p.add_argument(
        "--annotations",
        metavar="ANNOTATIONS_YAML",
        help="stand-off anchors to re-resolve against AFTER",
    )
    p.add_argument("before", metavar="BEFORE.md")
    p.add_argument("after", metavar="AFTER.md")
    args = p.parse_args(argv)
    try:
        before, after = _read(args.before), _read(args.after)
        anns = parse_annotations(_read(args.annotations)) if args.annotations else None
    except InputError as exc:
        print(f"revoice_check.py: error: {exc}", file=sys.stderr)
        return 2
    result = compare(before, after, anns)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=False))
    else:
        print(summary(result))
    return 0 if result["lossless"] else 1


if __name__ == "__main__":
    sys.exit(main())
