"""The claims ledger and the advisory claims check (task 0006; ADR 0006; specification §7).

The ledger is Markdown: any table whose header starts `ID | Claim …` and has a `Status` column.
Detectors find numbers, quotations and names in the *spoken* text; a detection is covered when a
resolved `claim` anchor overlaps it (names: anywhere in the same sentence). Concerns come in
three tiers; licensed anchors are reported as licensed and never as concerns. Agents flag, they
do not fix: nothing here rewrites a script.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import annotate

TIERS = ("high", "medium", "low")
TIER_OF = {
    "number_unanchored": "high",
    "quotation_unanchored": "high",
    "name_unanchored": "high",
    "claim_unverified": "high",
    "anchor_orphaned": "medium",
    "anchor_ambiguous": "medium",
    "claim_missing": "medium",
    "claim_id_invalid": "medium",
    "source_unresolved": "medium",  # a research:/dataset: reference that does not resolve (0022)
    "soft_as_fact": "low",
    "claim_uncited": "low",
    "ledger_row_invalid": "low",
    "source_newer_available": "low",  # the cited version or release is not the current one (0022)
}


# --------------------------------------------------------------------------- ledger


@dataclass
class Row:
    id: str
    claim: str
    source: str
    status: str
    notes: str
    line: int


@dataclass
class Ledger:
    path: Path | None
    rows: dict[str, Row] = field(default_factory=dict)
    problems: list[dict[str, Any]] = field(default_factory=list)
    skipped_tables: list[int] = field(default_factory=list)


def _cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    parts = re.split(r"(?<!\\)\|", body)
    return [p.strip().replace("\\|", "|") for p in parts]


def _plain(cell: str) -> str:
    return re.sub(r"[`*_]", "", cell).strip()


def _is_rule(cells: list[str]) -> bool:
    return (
        bool(cells)
        and all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c)
        and any(cells)
    )


def parse_ledger(
    text: str, id_pattern: str, statuses: list[str], path: Path | None = None
) -> Ledger:
    led = Ledger(path)
    rx = re.compile(rf"^(?:{id_pattern})$")
    lines = text.splitlines()
    cols: dict[str, int] | None = None
    width = 0
    skipped_open = False
    for n, line in enumerate(lines, 1):
        if not line.lstrip().startswith("|"):
            cols = None
            skipped_open = False
            continue
        cells = _cells(line)
        if _is_rule(cells):
            continue
        heads = [_plain(c).lower() for c in cells]
        if heads and heads[0] == "id":
            if "status" in heads and len(heads) > 1 and heads[1].startswith("claim"):
                cols = {"id": 0, "claim": 1, "status": heads.index("status")}
                src = next(
                    (
                        i
                        for i, h in enumerate(heads)
                        if h in ("source", "sources", "how")
                    ),
                    None,
                )
                cols["source"] = src if src is not None else -1
                cols["notes"] = next(
                    (i for i, h in enumerate(heads) if i not in cols.values()), -1
                )
                width = len(cells)
            else:
                cols = None
                led.skipped_tables.append(n)
                skipped_open = True
            continue
        if cols is None:
            first = _plain(cells[0]) if cells else ""
            if rx.match(first):
                why = (f"in a table without a Status column (header line {led.skipped_tables[-1]})"
                       if led.skipped_tables and skipped_open else "after the table ended (a blank line "
                       "ends a Markdown table; repeat the header or remove the blank line)")
                led.problems.append({"code": "row_outside_claims_table", "line": n,
                                     "message": f"{first} is {why}; not read"})
            continue
        if len(cells) != width:
            led.problems.append(
                {
                    "code": "row_shape",
                    "line": n,
                    "message": f"{len(cells)} cells, header has {width}",
                }
            )
            continue
        rid = _plain(cells[cols["id"]])
        status = _plain(cells[cols["status"]]).upper()
        if not rx.match(rid):
            led.problems.append(
                {
                    "code": "row_id_invalid",
                    "line": n,
                    "message": f"ID {rid!r} does not match {id_pattern!r}",
                }
            )
            continue
        if status not in statuses:
            led.problems.append(
                {
                    "code": "row_status_invalid",
                    "line": n,
                    "message": f"{rid}: status {status!r} is not one of {', '.join(statuses)}",
                }
            )
            continue
        if rid in led.rows:
            led.problems.append(
                {
                    "code": "row_duplicate",
                    "line": n,
                    "message": f"{rid} repeats line {led.rows[rid].line}",
                }
            )
            continue
        get = lambda k: cells[cols[k]] if cols[k] >= 0 else ""  # noqa: E731
        led.rows[rid] = Row(rid, get("claim"), get("source"), status, get("notes"), n)
    return led


def find_ledger(talk: Path) -> Path | None:
    research = talk / "research"
    for name in ("claims.md", "CLAIMS.md"):
        if (research / name).is_file():
            return research / name
    return None


def load_ledger(path: Path | None, id_pattern: str, statuses: list[str]) -> Ledger:
    if path is None or not path.is_file():
        return Ledger(path)
    return parse_ledger(path.read_text(encoding="utf-8"), id_pattern, statuses, path)


# --------------------------------------------------------------------------- detectors

_UNITS = (
    r"(?:\s?%|\s?(?:per\s?cent|percent|million|billion|trillion|thousand|times|x)\b)"
)
NUMBER = re.compile(
    rf"(?<![\w.\-/])(?:[$€£]\s?)?(?:\d{{1,3}}(?:,\d{{3}})+|\d+)(?:\.\d+)?(?:st|nd|rd|th)?{_UNITS}?(?![\w])"
)
YEAR = re.compile(r"^(1[89]\d\d|20\d\d)$")
QUOTE = re.compile(r"[\"“]([^\"“”\n]{3,400})[\"”]")
CAP = r"[A-Z][\w'’\-]*"
NAME = re.compile(
    rf"\b{CAP}(?:\s+(?:of|the|for|and|de|del|la|von|van|der)?\s*{CAP})+\b"
)
ACRONYM = re.compile(r"\b[A-Z][A-Z0-9&]{1,9}s?\b")
NAME_STOP = {"IT", "PC", "GPS", "USB", "OK", 
    "AI",
    "I",
    "OK",
    "TV",
    "PM",
    "AM",
    "US",
    "UK",
    "EU",
    "UN",
    "GPU",
    "GPUs",
    "LLM",
    "LLMs",
    "CEO",
    "CEOs",
    "PDF",
    "API",
    "APIs",
    "AGI",
}
HEDGES = re.compile(
    r"\b(i think|i believe|we think|probably|perhaps|maybe|roughly|about|around|"
    r"approximately|estimate[sd]?|may|might|could|likely|suggests?|seems?|appears?|"
    r"arguably|in my view|my guess|plausibly)\b",
    re.I,
)
COMMON = {"In", "On", "At", "The", "A", "An", "And", "But", "So", "If", "When", "While", "This", "That",
          "These", "Those", "We", "Our", "It", "Its", "They", "Their", "You", "Your", "He", "She", "His",
          "Her", "There", "Here", "What", "Why", "How", "Now", "Then", "For", "Of", "To", "By", "With",
          "From", "As", "Last", "Next", "Every", "Each", "One", "Some", "Most", "All", "Many", "No", "Not",
          "My", "Me", "Us", "Let", "Today", "Yesterday", "Tomorrow", "Yes", "Think", "Look", "Remember",
          "Imagine", "Consider", "Since", "After", "Before", "Over", "Under", "Across", "Even", "Only"}
CALENDAR = {"January", "February", "March", "April", "May", "June", "July", "August", "September",
            "October", "November", "December", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"}
PLACES = ("United States", "United Kingdom", "United Arab Emirates", "New Zealand", "South Korea",
          "North Korea", "South Africa", "Saudi Arabia", "Costa Rica", "Hong Kong", "Latin America",
          "North America", "South America", "Middle East", "Southeast Asia", "European Union")
LINKERS = {"of", "the", "for", "and", "de", "del", "la", "von", "van", "der"}
SENTENCE = re.compile(r"[^.!?]+[.!?]*")


def _sentences(body: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in SENTENCE.finditer(body)]


def detect(body: str, entities: set[str] | None = None) -> list[dict[str, Any]]:
    """Numbers, quotations and names in one section's spoken text, with character spans."""
    out: list[dict[str, Any]] = []
    quoted: list[tuple[int, int]] = []
    for m in QUOTE.finditer(body):
        if (
            len(m.group(1).split()) >= 3
        ):  # shorter quoted spans are scare quotes, not quotations
            out.append(
                {
                    "type": "quotation",
                    "text": m.group(0),
                    "start": m.start(),
                    "end": m.end(),
                }
            )
            quoted.append((m.start(), m.end()))
    for m in NUMBER.finditer(body):
        raw = m.group(0).strip()
        if YEAR.match(raw):
            continue  # a bare year dates a claim; it is not one
        before, after = body[:m.start()], body[m.end():]
        if re.search(rf"\b(?:{'|'.join(CALENDAR)})\s*$", before) or re.match(rf"\s+(?:{'|'.join(CALENDAR)})\b", after):
            continue  # a day of the month ("12 June", "June 12") dates a claim; it is not one
        if re.search(r"\b[A-Z][A-Za-z]+[ -]$", before) and not re.match(r"\s*(?:%|per|percent|million|billion)", after):
            continue  # a version in a product name ("Mythos 5", "GPT-4")
        out.append({"type": "number", "text": raw, "start": m.start(), "end": m.end()})
    seen: list[tuple[int, int]] = []
    for m in NAME.finditer(body):
        words = list(re.finditer(r"\S+", m.group(0)))
        while words and (words[0].group(0) in COMMON or words[0].group(0) in CALENDAR
                         or words[0].group(0) in LINKERS):
            words.pop(0)
        while words and (words[-1].group(0) in CALENDAR or words[-1].group(0).lower() in LINKERS):
            words.pop()
        if len(words) < 2:
            continue
        a, b = m.start() + words[0].start(), m.start() + words[-1].end()
        if all(w.group(0) in NAME_STOP or w.group(0).lower() in LINKERS for w in words):
            continue  # only stop-listed acronyms ("AI IT")
        rest = body[a:b]
        for place in PLACES:
            rest = rest.replace(place, "")
        if len(re.findall(r"\b[A-Z]", rest)) < 2:
            continue  # a place, or places joined by "and", is not an organisation or a person
        out.append({"type": "name", "text": body[a:b], "start": a, "end": b})
        seen.append((a, b))
    for m in ACRONYM.finditer(body):
        if m.group(0) in NAME_STOP or any(a <= m.start() < b for a, b in seen):
            continue
        out.append(
            {"type": "name", "text": m.group(0), "start": m.start(), "end": m.end()}
        )
        seen.append((m.start(), m.end()))
    for ent in sorted(entities or ()):
        for m in re.finditer(rf"\b{re.escape(ent)}\b", body):
            if not any(a <= m.start() < b for a, b in seen):
                out.append(
                    {"type": "name", "text": ent, "start": m.start(), "end": m.end()}
                )
                seen.append((m.start(), m.end()))
    # drop numbers and names that sit inside a detected quotation: the quotation is the claim
    out = [
        d
        for d in out
        if d["type"] == "quotation" or not any(a <= d["start"] < b for a, b in quoted)
    ]
    return sorted(out, key=lambda d: (d["start"], d["type"]))


def ledger_entities(ledger: Ledger) -> set[str]:
    """Single capitalised words that the ledger itself names mid-sentence (e.g. Mozilla, Anthropic)."""
    out: set[str] = set()
    for row in ledger.rows.values():
        text = re.sub(r"[`*_]", "", row.claim)
        for m in re.finditer(r"(?<=[a-z,;:]\s)([A-Z][a-z]{2,}[A-Za-z]*)\b", text):
            out.add(m.group(1))
    return out


# --------------------------------------------------------------------------- the check


@dataclass
class ScriptInput:
    label: str  # repository-relative path of the script, for reports
    script: annotate.Script
    annotations: list[dict[str, Any]]


def _concern(code: str, where: str, message: str, **extra) -> dict[str, Any]:
    return {
        "code": code,
        "tier": TIER_OF[code],
        "where": where,
        "message": message,
        **extra,
    }


def check(
    scripts: list[ScriptInput],
    ledger: Ledger,
    *,
    id_pattern: str,
    talk_level: bool = True,
) -> dict[str, Any]:
    """Concerns over every script against one ledger. `talk_level` adds uncited-row concerns."""
    rx = re.compile(rf"^(?:{id_pattern})$")
    entities = ledger_entities(ledger)
    concerns: list[dict[str, Any]] = []
    licensed: list[dict[str, Any]] = []
    cited: set[str] = set()
    for si in scripts:
        results = annotate.resolve(si.script, si.annotations)
        by_slide = si.script.by_slide()
        spans: dict[str, list[tuple[int, int, dict[str, Any]]]] = {}
        for r in results:
            if r["kind"] != "claim":
                continue
            where = f"{si.label}#{r['slide']}"
            cid = r.get("claim", "")
            if cid:
                cited.add(cid)
            if r["state"] == "orphaned":
                concerns.append(
                    _concern(
                        "anchor_orphaned",
                        where,
                        f"anchor {r['quote']!r} no longer appears",
                        claim=cid,
                        suggestion=r.get("suggestion"),
                    )
                )
                continue
            if r["state"] == "ambiguous":
                concerns.append(
                    _concern(
                        "anchor_ambiguous",
                        where,
                        f"anchor {r['quote']!r} occurs "
                        f"{r['occurrences']} times; add prefix or suffix",
                        claim=cid,
                    )
                )
                continue
            spans.setdefault(r["slide"], []).append((r["start"], r["end"], r))
            if "licence" in r:
                licensed.append(
                    {
                        "where": where,
                        "quote": r["quote"],
                        "claim": cid,
                        "licence": r["licence"],
                    }
                )
                continue
            if not rx.match(cid):
                concerns.append(
                    _concern(
                        "claim_id_invalid",
                        where,
                        f"{cid!r} does not match {id_pattern!r}",
                        claim=cid,
                    )
                )
                continue
            row = ledger.rows.get(cid)
            if row is None:
                concerns.append(
                    _concern(
                        "claim_missing", where, f"{cid} is not in the ledger", claim=cid
                    )
                )
                continue
            if row.status == "UNVERIFIED":
                concerns.append(
                    _concern(
                        "claim_unverified",
                        where,
                        f"{cid} is UNVERIFIED",
                        claim=cid,
                        quote=r["quote"],
                    )
                )
            elif row.status == "SOFT":
                body = by_slide[r["slide"]].body
                sent = next(
                    (body[a:b] for a, b in _sentences(body) if a <= r["start"] < b),
                    r["quote"],
                )
                if not HEDGES.search(sent):
                    concerns.append(
                        _concern(
                            "soft_as_fact",
                            where,
                            f"{cid} is SOFT but worded as fact",
                            claim=cid,
                            sentence=sent.strip(),
                        )
                    )
        for sec in si.script.sections:
            anchored = spans.get(sec.slide, [])
            sents = _sentences(sec.body)
            for d in detect(sec.body, entities):
                if d["type"] == "name":
                    sent = next(
                        ((a, b) for a, b in sents if a <= d["start"] < b),
                        (d["start"], d["end"]),
                    )
                    covered = any(s < sent[1] and e > sent[0] for s, e, _ in anchored)
                else:
                    covered = any(
                        s < d["end"] and e > d["start"] for s, e, _ in anchored
                    )
                if not covered:
                    code = {
                        "number": "number_unanchored",
                        "quotation": "quotation_unanchored",
                        "name": "name_unanchored",
                    }[d["type"]]
                    concerns.append(
                        _concern(
                            code,
                            f"{si.label}#{sec.slide}",
                            f"{d['type']} {d['text']!r} has no claim anchor",
                            text=d["text"],
                        )
                    )
    if talk_level:
        for rid, row in ledger.rows.items():
            if rid not in cited:
                concerns.append(
                    _concern(
                        "claim_uncited",
                        f"{ledger.path.name if ledger.path else 'ledger'}:{row.line}",
                        f"{rid} is in the ledger but no script cites it",
                        claim=rid,
                    )
                )
        for p in ledger.problems:
            concerns.append(
                _concern(
                    "ledger_row_invalid",
                    f"{ledger.path.name if ledger.path else 'ledger'}:{p['line']}",
                    p["message"],
                    detail=p["code"],
                )
            )
    summary = {t: sum(1 for c in concerns if c["tier"] == t) for t in TIERS}
    summary["licensed"] = len(licensed)
    return {"concerns": concerns, "licensed": licensed, "summary": summary}


def blocking(summary: dict[str, int], blocking_tiers: list[str]) -> list[str]:
    return [t for t in blocking_tiers if summary.get(t, 0) > 0]
