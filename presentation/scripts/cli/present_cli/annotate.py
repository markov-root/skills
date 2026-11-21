"""Scripts as `## <slide-id>` sections, and stand-off annotations resolved against them.

Task 0018 (ADR 0010; specification §7). Resolution is the W3C Web Annotation TextQuoteSelector
pattern: exact quote within the slide's section, then a whitespace/punctuation/case-normalised
quote, disambiguated by `prefix`/`suffix`. The outcome is `resolved`, `ambiguous` or `orphaned`;
an orphan gets the most similar span as a suggestion, which is reported and never applied.
Everything here is deterministic: same input, same output.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

SLIDE_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
# A bracketed marker is any [ … ] span whose content starts with a letter, a digit or a sigil —
# [Slide 3], [C-07], [CLAIM], [pause] — but not a Markdown link's text ("[text](url)").
MARKER = re.compile(r"\[(?=[A-Za-z0-9#@!^*])[^\[\]\n]{1,80}\](?!\()")
SUGGEST_MIN = 0.5
KEEP = "%$€£"  # symbols that carry meaning in a claim ("64%" is not "64")


@dataclass
class Section:
    slide: str
    body: str  # the spoken text under the heading, exactly as written
    line: int  # 1-based line of the heading


@dataclass
class Script:
    sections: list[Section]
    findings: list[dict[str, Any]] = field(
        default_factory=list
    )  # format findings (task 0007)

    def by_slide(self) -> dict[str, Section]:
        out: dict[str, Section] = {}
        for s in self.sections:
            out.setdefault(s.slide, s)
        return out

    def spoken(self) -> str:
        return "\n\n".join(s.body.strip() for s in self.sections if s.body.strip())


def parse_script(text: str) -> Script:
    """Split a script into sections and report every departure from 'headings + spoken words'."""
    lines = text.splitlines()
    sections: list[Section] = []
    findings: list[dict[str, Any]] = []
    cur: Section | None = None
    buf: list[str] = []
    in_fence = False
    seen: dict[str, int] = {}

    def flush():
        if cur is not None:
            cur.body = "\n".join(buf).strip("\n")
            sections.append(cur)

    for n, line in enumerate(lines, 1):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            findings.append(
                {
                    "code": "format_code_block",
                    "line": n,
                    "message": "code fence in a script; scripts hold only spoken words",
                }
            )
        m = HEADING.match(line) if not in_fence else None
        if m:
            level, title = len(m.group(1)), m.group(2)
            if level != 2:
                findings.append(
                    {
                        "code": "format_heading_level",
                        "line": n,
                        "message": f"only '## <slide-id>' headings are allowed: {line.strip()!r}",
                    }
                )
                buf.append(line)
                continue
            flush()
            buf = []
            if not SLIDE_ID.match(title):
                findings.append(
                    {
                        "code": "format_slide_id",
                        "line": n,
                        "message": f"slide id must be kebab-case: {title!r}",
                    }
                )
            if title in seen:
                findings.append(
                    {
                        "code": "format_duplicate_slide",
                        "line": n,
                        "message": f"slide id {title!r} repeats line {seen[title]}",
                    }
                )
            seen.setdefault(title, n)
            cur = Section(title, "", n)
            continue
        if cur is None:
            if line.strip():
                findings.append(
                    {
                        "code": "format_text_before_first_slide",
                        "line": n,
                        "message": "text before the first '## <slide-id>' heading",
                    }
                )
            continue
        for mk in MARKER.finditer(line):
            findings.append(
                {
                    "code": "format_marker",
                    "line": n,
                    "message": f"bracketed marker in spoken text: {mk.group(0)!r} "
                    "(move it to annotations.yaml)",
                }
            )
        if re.match(r"^\s*(<!--|>|\||[-*+] |\d+\. )", line):
            findings.append(
                {
                    "code": "format_markup",
                    "line": n,
                    "message": "markup (comment, quote, table or list) in spoken text",
                }
            )
        buf.append(line)
    flush()
    if not sections:
        findings.append(
            {
                "code": "format_no_slides",
                "line": 1,
                "message": "no '## <slide-id>' sections",
            }
        )
    for s in sections:
        if not s.body.strip():
            findings.append(
                {
                    "code": "format_empty_slide",
                    "line": s.line,
                    "message": f"slide {s.slide!r} has no spoken text",
                }
            )
    return Script(sections, findings)


# --------------------------------------------------------------------------- normalisation


def _normal_char(ch: str) -> str:
    """Case-folded, accent-stripped character, '' for punctuation, ' ' for whitespace."""
    if ch.isspace():
        return " "
    if ch in KEEP:
        return ch
    if unicodedata.category(ch) == "Pd" or ch in "/\u2026":  # dashes, slashes, ellipsis separate words
        return " "
    if unicodedata.category(ch)[0] in "PS":
        return ""
    base = unicodedata.normalize("NFKD", ch)
    return "".join(c for c in base if not unicodedata.combining(c)).casefold()


def normalise(text: str) -> tuple[str, list[int]]:
    """Normalised text plus, for each normalised character, its index in the original."""
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        for c in _normal_char(ch):
            if c == " " and (not out or out[-1] == " "):
                continue
            out.append(c)
            idx.append(i)
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def _find_all(hay: str, needle: str) -> list[int]:
    out, i = [], hay.find(needle)
    while needle and i >= 0:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out


# --------------------------------------------------------------------------- resolution


def _disambiguate(
    hay: str, starts: list[int], length: int, prefix: str, suffix: str
) -> list[int]:
    keep = starts
    if prefix:
        keep = [s for s in keep if hay[:s].rstrip().endswith(prefix.strip())]
    if suffix:
        keep = [
            s for s in keep if hay[s + length :].lstrip().startswith(suffix.strip())
        ]
    return keep


def _suggest(body: str, quote: str) -> dict[str, Any] | None:
    """The span of `body` most similar to `quote`, over word windows of similar length."""
    words = list(re.finditer(r"\S+", body))
    qn = normalise(quote)[0]
    n = max(1, len(qn.split()))
    best: tuple[float, int, int] | None = None
    for size in sorted({max(1, n - 2), max(1, n - 1), n, n + 1, n + 2}):
        for i in range(0, max(0, len(words) - size) + 1):
            a, b = words[i].start(), words[i + size - 1].end()
            cand = normalise(body[a:b])[0]
            score = SequenceMatcher(None, qn, cand, autojunk=False).ratio()
            if best is None or score > best[0] + 1e-12:
                best = (score, a, b)
    if best is None or best[0] < SUGGEST_MIN:
        return None
    score, a, b = best
    return {"quote": body[a:b].strip(" ,.;:"), "score": round(score, 3)}


def resolve_one(script: Script, ann: dict[str, Any]) -> dict[str, Any]:
    slide, quote = ann["slide"], ann["quote"]
    prefix, suffix = ann.get("prefix", ""), ann.get("suffix", "")
    base = {"slide": slide, "quote": quote, "kind": ann["kind"]}
    for k in ("claim", "licence", "text"):
        if k in ann:
            base[k] = ann[k]
    sec = script.by_slide().get(slide)
    if sec is None:
        hint = next((s.slide for s in script.sections if quote in s.body), None)
        return {
            **base,
            "state": "orphaned",
            "reason": "slide_missing",
            "suggestion": {"slide": hint, "quote": quote, "score": 1.0}
            if hint
            else None,
        }
    body = sec.body
    hits = _find_all(body, quote)
    if len(hits) > 1:
        hits = _disambiguate(body, hits, len(quote), prefix, suffix)
    if len(hits) == 1:
        return {
            **base,
            "state": "resolved",
            "match": "exact",
            "start": hits[0],
            "end": hits[0] + len(quote),
        }
    if len(hits) > 1:
        return {
            **base,
            "state": "ambiguous",
            "occurrences": len(hits),
            "reason": "quote occurs more than once; add prefix or suffix",
        }
    nb, idx = normalise(body)
    nq = normalise(quote)[0]
    nhits = _find_all(nb, nq) if nq else []
    if len(nhits) > 1:
        nhits = _disambiguate(
            nb, nhits, len(nq), normalise(prefix)[0], normalise(suffix)[0]
        )
    if len(nhits) == 1:
        s = nhits[0]
        start, end = idx[s], idx[s + len(nq) - 1] + 1
        return {
            **base,
            "state": "resolved",
            "match": "normalised",
            "start": start,
            "end": end,
            "matched": body[start:end],
        }
    if len(nhits) > 1:
        return {
            **base,
            "state": "ambiguous",
            "occurrences": len(nhits),
            "reason": "normalised quote occurs more than once; add prefix or suffix",
        }
    sug = _suggest(body, quote)
    return {
        **base,
        "state": "orphaned",
        "reason": "quote_not_found",
        "suggestion": {"slide": slide, **sug} if sug else None,
    }


def resolve(script: Script, annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"index": i, **resolve_one(script, a)} for i, a in enumerate(annotations)]


def counts(results: list[dict[str, Any]]) -> dict[str, int]:
    out = {"resolved": 0, "ambiguous": 0, "orphaned": 0}
    for r in results:
        out[r["state"]] += 1
    return out
