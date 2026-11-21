#!/usr/bin/env python3
"""pangram.py — opt-in self-adversarial detector screen + calibration corpus.

Wraps the Pangram text-detection API (ADR 0006, ADR 0009). One detector's
opinion on where a draft reads as AI — a SCREEN, never a gate, never a verdict
about who wrote anything. Every successful check is logged (unless --no-log) to
a private, append-only corpus that keeps PROVENANCE (who actually wrote the
text, supplied by the caller) separate from the detector's VERDICT. The corpus
commands mine that data for candidate AI-tells and measure the existing
`knowledge/ai-tells.md` watch-list. They never edit knowledge.

Commands
--------
  check FILE|-        send a draft to Pangram, print verdict + most AI-like
                      windows (line-anchored), log it. --dry-run: words and
                      estimated cost only, no network.
  balance             account credit balance (free call).
  corpus stats        counts by provenance x verdict, by genre, by version.
  corpus mine         contrastive log-odds n-grams: AI-labelled vs human-labelled
                      windows (or agent vs human provenance) -> CANDIDATE tells.
  corpus terms        does each watch-list term actually predict AI-labelled
                      windows? Defaults to the ai-tells.md lexical lists.
  corpus pairs        before/after revision pairs and their verdict change.

Key: $PANGRAM_API_KEY, else the fixed file ~/.config/pangram/key.env
(`PANGRAM_API_KEY=...`, mode 0600; $PANGRAM_KEY_FILE overrides the path). The
key is never printed or logged.

Corpus: $WRITING_CORPUS_DIR, else ~/Skills/exported-data/writing/detector-corpus
(created 0700). Layout: checks.jsonl (one record per check), texts/<sha>.txt,
responses/<sha>-<model>.json. A response is cached by text hash + model, so
re-checking an unchanged draft costs nothing (--refresh forces a new call).

Exit codes: 0 ok · 2 usage / input error (e.g. under 50 words) · 3 detector
unavailable (no key, rejected key, network) · 4 out of credits / rate-limited ·
5 detector task failed.

Stdlib only; no third-party dependencies.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict

BASE_URL = os.environ.get("PANGRAM_BASE_URL", "https://text.external-api.pangram.com")
DEFAULT_MODEL = "pangram-4"
MIN_WORDS = 50  # Pangram 4 model card: inputs of at least 50 words.
PRICE_PER_100_WORDS_USD = 0.05  # pangram.com/pricing, read 2026-11-19; an estimate.
PROVENANCES = ("agent", "human", "agent-human-edit", "human-agent-edit", "unknown")
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
AI_TELLS = SKILL_ROOT / "knowledge" / "ai-tells.md"

EXIT_OK, EXIT_USAGE, EXIT_UNAVAILABLE, EXIT_QUOTA, EXIT_FAILED = 0, 2, 3, 4, 5

WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
STOPWORDS = frozenset(
    """a about above after again against all am an and any are as at be because been
    before being below between both but by can could did do does doing down during each
    few for from further had has have having he her here hers herself him himself his how
    i if in into is it its itself just me more most my myself no nor not now of off on
    once only or other our ours ourselves out over own same she should so some such than
    that the their theirs them themselves then there these they this those through to too
    under until up very was we were what when where which while who whom why will with
    would you your yours yourself yourselves also may might must shall s t don it's""".split()
)


class DetectorError(Exception):
    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- paths


def corpus_dir() -> pathlib.Path:
    env = os.environ.get("WRITING_CORPUS_DIR")
    if env:
        return pathlib.Path(env).expanduser()
    return (
        pathlib.Path.home() / "Skills" / "exported-data" / "writing" / "detector-corpus"
    )


def ensure_corpus(root: pathlib.Path) -> pathlib.Path:
    for sub in (root, root / "texts", root / "responses"):
        sub.mkdir(parents=True, exist_ok=True)
        os.chmod(sub, 0o700)
    return root


def _write_private(path: pathlib.Path, data: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(data)


def skill_version() -> str:
    try:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = re.search(r'^\s*version:\s*"?([^"\n]+)"?', text, re.MULTILINE)
    return match.group(1).strip() if match else "unknown"


# ----------------------------------------------------------------------------- key


def load_key() -> str:
    key = os.environ.get("PANGRAM_API_KEY", "").strip()
    if key:
        return key
    path = pathlib.Path(
        os.environ.get("PANGRAM_KEY_FILE", "~/.config/pangram/key.env")
    ).expanduser()
    try:
        if path.stat().st_mode & 0o077:
            print(f"pangram: warning: {path} is readable by others; run `chmod 600 {path}`", file=sys.stderr)
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        raise DetectorError(
            f"no Pangram key: set PANGRAM_API_KEY or create {path} "
            "(one line `PANGRAM_API_KEY=...`, chmod 600)",
            EXIT_UNAVAILABLE,
        ) from None
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        name, sep, value = line.partition("=")
        if sep and name.strip() == "PANGRAM_API_KEY":
            value = value.strip().strip('"').strip("'")
            if value:
                return value
    raise DetectorError(f"{path} has no PANGRAM_API_KEY= line", EXIT_UNAVAILABLE)


# ---------------------------------------------------------------------- text prep


def prepare(raw: str) -> tuple[str, list[int]]:
    """Drop YAML frontmatter and fenced code; keep a kept-line -> source-line map.

    Returns the prose to send and, for each line of it, the 1-based line number
    in the original file, so detector windows can be anchored to the source.
    """
    lines = raw.splitlines()
    kept: list[str] = []
    origin: list[int] = []
    i = 0
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() in ("---", "..."):
                i = j + 1
                break
    fence: str | None = None
    for n in range(i, len(lines)):
        line = lines[n]
        stripped = line.lstrip()
        marker = stripped[:3]
        if fence is None and marker in ("```", "~~~"):
            fence = marker
            continue
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        kept.append(line)
        origin.append(n + 1)
    # Trim leading/trailing blank lines but keep the mapping aligned.
    while kept and not kept[0].strip():
        kept.pop(0)
        origin.pop(0)
    while kept and not kept[-1].strip():
        kept.pop()
        origin.pop()
    return "\n".join(kept), origin


def word_count(text: str) -> int:
    return len(text.split())


def estimate_cost(words: int) -> float:
    return math.ceil(words / 100) * PRICE_PER_100_WORDS_USD


# The six-category reading used in the user's EUL4 reports (scripts/pangram_check.py
# there): window label, with Medium/Low confidence shown as "likely". Shares are
# of words. Status bands follow the same reports.
CATS = ["AI", "Likely AI", "AI-assisted", "Likely AI-assisted", "Likely human", "Human"]
BASE = {"AI-Generated": "AI", "AI-Assisted": "AI-assisted", "Human Written": "Human"}
FLAGGED = ("AI", "Likely AI", "AI-assisted", "Likely AI-assisted")


def window_category(win: dict) -> str:
    base = BASE.get(win.get("label"), "Human")
    if win.get("confidence") == "High":
        return base
    return "Likely human" if base == "Human" else "Likely " + base


def categories(response: dict) -> dict[str, float]:
    tot = {k: 0 for k in CATS}
    for win in response.get("windows") or []:
        tot[window_category(win)] += win.get("word_count") or len(
            (win.get("text") or "").split()
        )
    n = sum(tot.values()) or 1
    return {k: round(v / n, 4) for k, v in tot.items()}


def flagged_share(cats: dict[str, float]) -> float:
    return round(sum(cats.get(k, 0) for k in FLAGGED), 4)


def status_band(flagged: float) -> str:
    if flagged < 0.10:
        return "OK"
    if flagged < 0.40:
        return "Review"
    if flagged < 0.70:
        return "Rewrite parts"
    return "Rewrite"


_TEX_SUBS = [
    (re.compile(r"(?<!\\)%.*$"), ""),
    (re.compile(r"\\\\(\[[^\]]*\])?"), " "),
    (re.compile(r"\$([^$]*)\$"), r"\1"),
    (re.compile(r"~?\\cite[pt]?\{[^}]*\}"), ""),
    (re.compile(r"\\(input|include|label)\{[^}]*\}"), ""),
    (re.compile(r"\\(begin|end)\{[^}]*\}(\[[^\]]*\])?"), ""),
    (re.compile(r"\\item\s*"), ""),
    (re.compile(r"\\[CcVv]?ref\{[^}]*\}"), "Section X"),
    (
        re.compile(
            r"\\(textbf|emph|textit|texttt|underline|paragraph|section|subsection|subsubsection|caption|EvalBy)\*?\{([^}]*)\}"
        ),
        r"\2",
    ),
]


def strip_latex_line(line: str) -> str:
    """Reduce one LaTeX source line to the prose a reader sees (after EUL4's strip_latex)."""
    for pattern, repl in _TEX_SUBS:
        line = pattern.sub(repl, line)
    line = (
        line.replace("\\%", "%")
        .replace("{,}", ",")
        .replace("``", '"')
        .replace("''", '"')
        .replace("`", "'")
    )
    line = (
        re.sub(r"\\[a-zA-Z]+\*?", "", line)
        .replace("{", "")
        .replace("}", "")
        .replace("~", " ")
    )
    return re.sub(r"[ \t]+", " ", line).strip()


def prepare_tex(raw: str) -> tuple[str, list[int]]:
    """Line-wise LaTeX stripping that keeps a kept-line -> source-line map."""
    lines = raw.splitlines()
    start = 0
    for n, line in enumerate(lines):
        if line.strip().startswith("\\begin{document}"):
            start = n + 1
            break
    kept: list[str] = []
    origin: list[int] = []
    for n in range(start, len(lines)):
        src = lines[n]
        if src.strip().startswith("\\end{document}"):
            break
        out = strip_latex_line(src)
        if not out and src.strip():
            continue  # markup- or comment-only line: drop it, don't invent a paragraph break
        if not out and kept and not kept[-1]:
            continue
        kept.append(out)
        origin.append(n + 1)
    while kept and not kept[0]:
        kept.pop(0)
        origin.pop(0)
    while kept and not kept[-1]:
        kept.pop()
        origin.pop()
    return "\n".join(kept), origin


def offset_to_line(text: str, origin: list[int], offset: int) -> int | None:
    if not origin or offset < 0:
        return None
    idx = text.count("\n", 0, min(offset, len(text)))
    return origin[min(idx, len(origin) - 1)]


def anchor_window(sent: str, returned: str, origin: list[int], win: dict) -> str:
    """Map a window to `Lx-y` in the source file; offsets refer to returned text."""
    start, end = win.get("start_index"), win.get("end_index")
    if returned == sent and isinstance(start, int) and isinstance(end, int):
        a, b = (
            offset_to_line(sent, origin, start),
            offset_to_line(sent, origin, max(end - 1, start)),
        )
    else:  # normalised by the service: fall back to locating the window text
        probe = (win.get("text") or "").strip()[:60]
        pos = sent.find(probe) if probe else -1
        if pos < 0:
            return "L?"
        a = offset_to_line(sent, origin, pos)
        b = offset_to_line(
            sent, origin, pos + len((win.get("text") or "").rstrip()) - 1
        )
    if a is None:
        return "L?"
    return f"L{a}" if a == b or b is None else f"L{a}-{b}"


# ---------------------------------------------------------------------------- http


def _request(
    method: str, path: str, key: str, body: dict | None = None, timeout: float = 60
):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE_URL.rstrip("/") + path,
        data=data,
        method=method,
        headers={
            "x-api-key": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001 - best-effort detail only
            pass
        status = exc.code
        if status in (401, 403):
            raise DetectorError(
                f"Pangram rejected the request ({status}): key invalid or model not enabled. {detail}",
                EXIT_UNAVAILABLE,
            ) from None
        if status in (402, 429):
            what = "insufficient credits" if status == 402 else "rate limited"
            raise DetectorError(
                f"Pangram {what} ({status}). {detail}", EXIT_QUOTA
            ) from None
        if status in (413, 415, 422):
            raise DetectorError(
                f"Pangram refused the input ({status}). {detail}", EXIT_USAGE
            ) from None
        raise DetectorError(
            f"Pangram HTTP {status}. {detail}", EXIT_UNAVAILABLE
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DetectorError(f"Pangram unreachable: {exc}", EXIT_UNAVAILABLE) from None


def detect(text: str, key: str, model: str, timeout: float, poll: float) -> dict:
    submitted = _request("POST", "/task", key, {"text": text, "model": model})
    task_id = submitted.get("task_id")
    if not task_id:
        raise DetectorError(f"Pangram returned no task_id: {submitted}", EXIT_FAILED)
    deadline = time.monotonic() + timeout
    while True:
        result = _request("GET", f"/task/{task_id}", key)
        stage = result.get("stage", "")
        if stage == "STAGE_SUCCESS":
            return result
        if stage == "STAGE_FAILED":
            raise DetectorError(
                f"Pangram task failed: {result.get('headline') or 'no detail'}",
                EXIT_FAILED,
            )
        if time.monotonic() > deadline:
            raise DetectorError(
                f"Pangram task {task_id} still {stage or 'pending'} after {timeout:.0f}s",
                EXIT_FAILED,
            )
        time.sleep(poll)


# -------------------------------------------------------------------------- corpus


def read_records(root: pathlib.Path) -> list[dict]:
    """Check records, with later `label` rows applied (append-only annotations)."""
    path = root / "checks.jsonl"
    if not path.exists():
        return []
    records: list[dict] = []
    labels: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        (labels if row.get("type") == "label" else records).append(row)
    by_id = {r.get("id"): r for r in records}
    for lab in labels:
        rec = by_id.get(lab.get("ref"))
        if rec is None:
            continue
        for field in ("provenance", "genre", "voice", "note", "pair_of"):
            if lab.get(field) is not None:
                rec[field] = lab[field]
    return records


def load_response(root: pathlib.Path, record: dict) -> dict | None:
    name = record.get("response_file")
    if not name:
        return None
    try:
        return json.loads((root / "responses" / name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def record_flagged(rec: dict) -> float | None:
    """Share of words flagged (AI, likely AI, AI-assisted, likely AI-assisted)."""
    if isinstance(rec.get("flagged_share"), (int, float)):
        return rec["flagged_share"]
    if isinstance(rec.get("fraction_ai"), (int, float)):
        return rec["fraction_ai"] + (rec.get("fraction_ai_assisted") or 0)
    return None


def latest_by_text(records: list[dict], version: str | None = None) -> list[dict]:
    """One record per (text, model): the latest wins, so re-checks don't double-count."""
    chosen: dict[tuple[str, str], dict] = {}
    for rec in records:
        if version and not str(rec.get("version", "")).startswith(version):
            continue
        chosen[(rec.get("text_sha256", ""), rec.get("model_requested", ""))] = rec
    return list(chosen.values())


def append_record(root: pathlib.Path, record: dict) -> None:
    path = root / "checks.jsonl"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


# ------------------------------------------------------------------------ commands


def cmd_check(args: argparse.Namespace) -> int:
    if args.file == "-":
        raw, source = sys.stdin.read(), None
    else:
        path = pathlib.Path(args.file)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"pangram: cannot read {path}: {exc}", file=sys.stderr)
            return EXIT_USAGE
        source = str(path.resolve())
    if args.raw:
        text, origin = raw.strip(), list(range(1, raw.count("\n") + 2))
    elif args.file != "-" and args.file.endswith(".tex"):
        text, origin = prepare_tex(raw)
    else:
        text, origin = prepare(raw)
    words = word_count(text)
    cost = estimate_cost(words)
    if words < MIN_WORDS:
        print(
            f"pangram: {words} words after preparation; Pangram needs at least {MIN_WORDS}.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if args.dry_run:
        out = {
            "words": words,
            "estimated_cost_usd": round(cost, 2),
            "model": args.model,
            "network": False,
        }
        print(
            json.dumps(out)
            if args.json
            else f"{words} words · est. ${cost:.2f} on {args.model} · nothing sent"
        )
        return EXIT_OK

    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    root = corpus_dir()
    response_name = f"{sha}-{args.model}.json"
    cached = False
    response = None
    if not args.refresh and (root / "responses" / response_name).exists():
        try:
            response = json.loads(
                (root / "responses" / response_name).read_text(encoding="utf-8")
            )
            cached = True
        except (OSError, json.JSONDecodeError):
            response = None
    if response is None:
        try:
            response = detect(text, load_key(), args.model, args.timeout, args.poll)
        except DetectorError as exc:
            print(f"pangram: {exc}", file=sys.stderr)
            return exc.code

    record = {
        "schema": 1,
        "id": f"{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{sha[:8]}",
        "checked_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "text_sha256": sha,
        "words": words,
        "source_path": source,
        "provenance": args.provenance,
        "genre": args.genre,
        "voice": args.voice,
        "note": args.note,
        "pair_of": args.pair_of,
        "skill_version": skill_version(),
        "detector": "pangram",
        "model_requested": args.model,
        "version": response.get("version"),
        "prediction_short": response.get("prediction_short"),
        "headline": response.get("headline"),
        "fraction_ai": response.get("fraction_ai"),
        "fraction_ai_assisted": response.get("fraction_ai_assisted"),
        "fraction_human": response.get("fraction_human"),
        "num_windows": len(response.get("windows") or []),
        "categories": categories(response),
        "cached": cached,
        "response_file": response_name,
    }
    record["flagged_share"] = flagged_share(record["categories"])
    record["status"] = status_band(record["flagged_share"])
    if not args.no_log:
        ensure_corpus(root)
        text_path = root / "texts" / f"{sha}.txt"
        if not text_path.exists():
            _write_private(text_path, text)
        if not cached:
            _write_private(
                root / "responses" / response_name,
                json.dumps(response, ensure_ascii=False),
            )
        append_record(root, record)

    returned = response.get("text") or ""
    windows = []
    for win in response.get("windows") or []:
        windows.append(
            {
                "anchor": anchor_window(text, returned, origin, win),
                "label": win.get("label"),
                "category": window_category(win),
                "ai_assistance_score": win.get("ai_assistance_score"),
                "confidence": win.get("confidence"),
                "is_humanized": win.get("is_humanized"),
                "text": (win.get("text") or "").strip(),
            }
        )
    flagged = sorted(
        (w for w in windows if w["label"] != "Human Written"),
        key=lambda w: -(w["ai_assistance_score"] or 0),
    )
    if args.json:
        print(
            json.dumps(
                {
                    "record": record,
                    "logged": not args.no_log,
                    "corpus": str(root) if not args.no_log else None,
                    "windows": windows,
                    "caveat": "one detector's opinion; a screen, not a verdict about authorship",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_OK

    def pct(v):
        return f"{round((v or 0) * 100)}%"

    print(
        f"pangram {record['version'] or args.model}: {record['status']} · "
        f"{pct(record['flagged_share'])} of words flagged ({record['prediction_short']}) — "
        f"{len(windows)} windows, {words} words{', cached' if cached else f', ~${cost:.2f}'}"
    )
    print("  " + " · ".join(f"{k} {pct(v)}" for k, v in record["categories"].items()))
    if flagged:
        print("most AI-like windows:")
        for w in flagged[: args.top]:
            snippet = re.sub(r"\s+", " ", w["text"])[:90]
            print(
                f"  {w['anchor']:<9} {w['category']:<18} {w['ai_assistance_score'] or 0:.2f}  {snippet}"
            )
        if len(flagged) > args.top:
            print(f"  … {len(flagged) - args.top} more (--top N or --json)")
    else:
        print("no AI-labelled windows.")
    if args.no_log:
        print("not logged (--no-log).")
    else:
        hint = (
            ""
            if args.provenance != "unknown"
            else "  (provenance unknown — pass --provenance to make this row useful)"
        )
        print(f"logged {record['id']} → {root}{hint}")
    print("screen only: one detector's opinion, not a verdict about who wrote this.")
    return EXIT_OK


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _import_items(path: pathlib.Path) -> list[dict]:
    """Normalise earlier Pangram outputs into {text, response, note, checked_at, model}.

    Accepts: a raw Pangram task response; a list (or single) of EUL4-style
    section results ({number, title, model, result}, with an optional sibling
    segments.json carrying the sent text); and JSONL ledgers whose lines carry
    {label, time, model, windows:[{label, confidence, words, text}]}.
    """
    items: list[dict] = []
    mtime = _dt.datetime.fromtimestamp(
        path.stat().st_mtime, _dt.timezone.utc
    ).isoformat(timespec="seconds")
    if path.suffix == ".jsonl":
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            wins = [
                {
                    "text": w.get("text", ""),
                    "label": w.get("label"),
                    "confidence": w.get("confidence"),
                    "word_count": w.get("words"),
                }
                for w in row.get("windows") or []
            ]
            response = {
                "windows": wins,
                "prediction_short": row.get("verdict"),
                "version": row.get("version"),
            }
            items.append(
                {
                    "text": "".join(w["text"] for w in wins).strip(),
                    "response": response,
                    "note": row.get("label"),
                    "checked_at": row.get("time") or mtime,
                    "model": row.get("model"),
                }
            )
        return items
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else [data]
    segments: dict[tuple, str] = {}
    seg_path = path.with_name("segments.json")
    if seg_path.exists():
        for seg in json.loads(seg_path.read_text(encoding="utf-8")):
            segments[(str(seg.get("number")), seg.get("title"))] = seg.get("text") or ""
    for row in rows:
        response = row.get("result", row)
        if not isinstance(response, dict) or "windows" not in response:
            continue
        key = (str(row.get("number")), row.get("title"))
        text = row.get("text") or response.get("text") or segments.get(key) or ""
        if not text:
            text = "".join(w.get("text") or "" for w in response["windows"])
        title = " ".join(
            str(x)
            for x in (row.get("number"), row.get("title") or row.get("section"))
            if x
        )
        items.append(
            {
                "text": text.strip(),
                "response": response,
                "note": title or path.stem,
                "checked_at": mtime,
                "model": row.get("model"),
            }
        )
    return items


def cmd_import(args: argparse.Namespace) -> int:
    root = ensure_corpus(corpus_dir())
    existing = read_records(root)
    seen = {(r.get("text_sha256"), r.get("model_requested")) for r in existing}
    by_note = {r.get("note"): r for r in existing if r.get("note")}
    added = skipped = 0
    for path in args.paths:
        path = pathlib.Path(path)
        try:
            items = _import_items(path)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"pangram: cannot import {path}: {exc}", file=sys.stderr)
            return EXIT_USAGE
        for item in items:
            text = item["text"]
            if not text:
                skipped += 1
                continue
            model = item.get("model") or DEFAULT_MODEL
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if (sha, model) in seen:
                skipped += 1
                continue
            response = item["response"]
            response_name = f"{sha}-{model}.json"
            note = (
                f"{args.note_prefix}{item['note']}"
                if args.note_prefix
                else item["note"]
            )
            pair_of = None
            if (
                args.pair_with_previous
                and note in by_note
                and by_note[note].get("text_sha256") != sha
            ):
                pair_of = by_note[note]["id"]
            cats = categories(response)
            record = {
                "schema": 1,
                "id": f"{re.sub(r'[^0-9TZ]', '', item['checked_at'][:19])}Z-{sha[:8]}",
                "checked_at": item["checked_at"],
                "text_sha256": sha,
                "words": word_count(text),
                "source_path": str(path.resolve()),
                "imported": True,
                "provenance": args.provenance,
                "genre": args.genre,
                "voice": None,
                "note": note,
                "pair_of": pair_of,
                "skill_version": skill_version(),
                "detector": "pangram",
                "model_requested": model,
                "version": response.get("version"),
                "prediction_short": response.get("prediction_short"),
                "headline": response.get("headline"),
                "fraction_ai": response.get("fraction_ai"),
                "fraction_ai_assisted": response.get("fraction_ai_assisted"),
                "fraction_human": response.get("fraction_human"),
                "num_windows": len(response.get("windows") or []),
                "categories": cats,
                "flagged_share": flagged_share(cats),
                "status": status_band(flagged_share(cats)),
                "cached": False,
                "response_file": response_name,
            }
            text_path = root / "texts" / f"{sha}.txt"
            if not text_path.exists():
                _write_private(text_path, text)
            if not (root / "responses" / response_name).exists():
                _write_private(
                    root / "responses" / response_name,
                    json.dumps(response, ensure_ascii=False),
                )
            append_record(root, record)
            seen.add((sha, model))
            by_note[note] = record
            added += 1
    print(
        f"imported {added} record(s), skipped {skipped} (duplicate or empty) → {root}"
    )
    return EXIT_OK


def _select(
    records: list[dict], refs: list[str], note_contains: str | None
) -> list[dict]:
    chosen = []
    for rec in records:
        rid, sha = rec.get("id", ""), rec.get("text_sha256", "")
        if any(rid == r or rid.startswith(r) or sha.startswith(r) for r in refs):
            chosen.append(rec)
        elif note_contains and note_contains.lower() in (rec.get("note") or "").lower():
            chosen.append(rec)
    return chosen


def cmd_label(args: argparse.Namespace) -> int:
    root = corpus_dir()
    targets = _select(read_records(root), args.ref, args.note_contains)
    if not targets:
        print("pangram: no matching records (see `corpus list`).", file=sys.stderr)
        return EXIT_USAGE
    fields = {
        k: getattr(args, k)
        for k in ("provenance", "genre", "note", "pair_of")
        if getattr(args, k) is not None
    }
    if not fields:
        print(
            "pangram: nothing to set (--provenance/--genre/--note/--pair-of).",
            file=sys.stderr,
        )
        return EXIT_USAGE
    for rec in targets:
        append_record(root, {"type": "label", "ref": rec["id"], "at": _now(), **fields})
    print(
        f"labelled {len(targets)} record(s): "
        + ", ".join(f"{k}={v}" for k, v in fields.items())
    )
    return EXIT_OK


def cmd_list(args: argparse.Namespace) -> int:
    records = read_records(corpus_dir())
    if args.json:
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return EXIT_OK
    for rec in records:
        flagged = rec.get("flagged_share")
        share = "  -" if flagged is None else f"{round(flagged * 100):>3}%"
        print(
            f"{rec.get('id', ''):<26} {rec.get('provenance', ''):<16} {rec.get('status', '-'):<13} {share} "
            f"{rec.get('words', 0):>5}w  {'↳' + rec['pair_of'][:15] + ' ' if rec.get('pair_of') else ''}{rec.get('note') or ''}"
        )
    return EXIT_OK


def cmd_balance(args: argparse.Namespace) -> int:
    try:
        result = _request("GET", "/balance", load_key())
    except DetectorError as exc:
        print(f"pangram: {exc}", file=sys.stderr)
        return exc.code
    print(json.dumps(result, indent=2))
    return EXIT_OK


def cmd_stats(args: argparse.Namespace) -> int:
    root = corpus_dir()
    records = latest_by_text(read_records(root), args.version)
    by_prov: dict[str, Counter] = defaultdict(Counter)
    frac: dict[str, list[float]] = defaultdict(list)
    genres: Counter = Counter()
    versions: Counter = Counter()
    for rec in records:
        prov = rec.get("provenance") or "unknown"
        by_prov[prov][rec.get("prediction_short") or "?"] += 1
        if record_flagged(rec) is not None:
            frac[prov].append(record_flagged(rec))
        genres[rec.get("genre") or "-"] += 1
        versions[rec.get("version") or "?"] += 1
    out = {
        "corpus": str(root),
        "texts": len(records),
        "by_provenance": {
            p: {
                "verdicts": dict(c),
                "mean_flagged_share": round(sum(frac[p]) / len(frac[p]), 3)
                if frac[p]
                else None,
            }
            for p, c in sorted(by_prov.items())
        },
        "by_genre": dict(genres.most_common()),
        "by_version": dict(versions.most_common()),
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return EXIT_OK
    print(f"{out['texts']} distinct texts in {root}")
    if not records:
        return EXIT_OK
    print("provenance          AI  Mixed  Human  mean flagged share")
    for p, row in out["by_provenance"].items():
        v = row["verdicts"]
        share = "-" if row["mean_flagged_share"] is None else f"{row['mean_flagged_share']:.2f}"
        print(
            f"  {p:<17} {v.get('AI', 0):>3} {v.get('Mixed', 0):>6} {v.get('Human', 0):>6}  {share}"
        )
    print("genres:   " + ", ".join(f"{g} {n}" for g, n in out["by_genre"].items()))
    print("versions: " + ", ".join(f"{g} {n}" for g, n in out["by_version"].items()))
    return EXIT_OK


def _read_text(root: pathlib.Path, rec: dict) -> str | None:
    try:
        return (root / "texts" / f"{rec['text_sha256']}.txt").read_text(encoding="utf-8")
    except (OSError, KeyError):
        return None


def _class_texts(
    root: pathlib.Path,
    records: list[dict],
    by: str,
    assisted_as: str,
    min_words: int = 0,
    all_records: list[dict] | None = None,
    min_drop: float = 0.0,
) -> tuple[list[str], list[str]]:
    """Texts on each side of a contrast.

    detector:   AI-Generated vs Human Written windows (topic-confounded in a
                single-document corpus; prefer `pairs` or `corpus style`).
    provenance: agent vs human texts.
    pairs:      the earlier vs the later text of each --pair-of revision pair,
                which holds topic roughly constant.
    """
    ai, human = [], []
    if by == "pairs":
        pool = {r.get("id"): r for r in (all_records or records)}
        for rec in records:
            before = pool.get(rec.get("pair_of"))
            if not before:
                continue
            drop = (before.get("flagged_share") or 0) - (rec.get("flagged_share") or 0)
            if drop < min_drop:
                continue
            a, b = _read_text(root, before), _read_text(root, rec)
            if a and b:
                ai.append(a)
                human.append(b)
        return ai, human
    for rec in records:
        if by == "provenance":
            prov = rec.get("provenance")
            if prov not in ("agent", "human"):
                continue
            try:
                text = (root / "texts" / f"{rec['text_sha256']}.txt").read_text(
                    encoding="utf-8"
                )
            except OSError:
                continue
            (ai if prov == "agent" else human).append(text)
            continue
        resp = load_response(root, rec)
        for win in (resp or {}).get("windows") or []:
            label = win.get("label")
            if label == "AI-Assisted":
                label = {"ai": "AI-Generated", "human": "Human Written"}.get(
                    assisted_as
                )
            text = win.get("text") or ""
            if len(text.split()) < min_words:
                continue
            if label == "AI-Generated":
                ai.append(text)
            elif label == "Human Written":
                human.append(text)
    return ai, human


# Topic-robust style features (after the EUL4 2026-11-17 style-delta note): counts
# that do not depend on what a section is about.
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(“‘])")
STYLE_FEATURES: list[tuple[str, str, re.Pattern | None]] = [
    ("commas", "per_sentence", re.compile(r",")),
    ("colons", "per_1k_words", re.compile(r":(?!//)")),
    ("semicolons", "per_1k_words", re.compile(r";")),
    ("parentheses", "per_1k_words", re.compile(r"\(")),
    ("dashes (— – --)", "per_1k_words", re.compile(r"—|–|(?<!-)--(?!-)| - ")),
    ("questions", "per_1k_words", re.compile(r"\?")),
    ("we / our / us", "per_1k_words", re.compile(r"\b(?:we|our|us|ours)\b", re.I)),
    ("I / my", "per_1k_words", re.compile(r"\b(?:I|my|me)\b")),
    ("possessive 's", "per_1k_words", re.compile(r"\b\w+['’]s\b")),
    ("-tion/-ment/-ness/-ity nouns", "per_1k_words", re.compile(r"\b\w{3,}(?:tions?|ments?|ness(?:es)?|ity|ities)\b", re.I)),
    ("elliptical back-refs", "per_1k_words", re.compile(r"\b(?:did so|do so|does so|the same|respectively)\b", re.I)),
    ("numbers", "per_1k_words", re.compile(r"(?<![\w.])\d[\d,.]*%?")),
    ("This/These/It openers", "per_1k_words", None),
]


def style_counts(text: str) -> dict:
    text = re.sub(r"https?://\S+", "", text)
    sentences = [x for x in SENT_SPLIT.split(text.strip()) if x.strip()]
    lengths = [len(x.split()) for x in sentences]
    counts = {"words": sum(lengths), "sentences": len(sentences), "lengths": lengths}
    for name, _unit, pattern in STYLE_FEATURES:
        if pattern is None:
            counts[name] = sum(1 for x in sentences if re.match(r"(?:This|These|It)\b", x.strip()))
        else:
            counts[name] = len(pattern.findall(text))
    return counts


def style_profile(texts: list[str]) -> dict:
    total: dict = {"words": 0, "sentences": 0, "lengths": []}
    for t in texts:
        c = style_counts(t)
        for k, v in c.items():
            total[k] = total.get(k, 0) + v if k != "lengths" else total["lengths"] + v
    words, sents = max(total["words"], 1), max(total["sentences"], 1)
    lengths = total["lengths"]
    mean = sum(lengths) / len(lengths) if lengths else 0.0
    sd = math.sqrt(sum((x - mean) ** 2 for x in lengths) / len(lengths)) if lengths else 0.0
    out = {"units": len(texts), "words": total["words"], "sentences": total["sentences"],
           "words per sentence": round(mean, 1), "sentence length SD": round(sd, 1)}
    for name, unit, _ in STYLE_FEATURES:
        out[name] = round(total.get(name, 0) / sents, 2) if unit == "per_sentence" else round(total.get(name, 0) / words * 1000, 1)
    return out


def ngrams(text: str, n_max: int) -> Counter:
    tokens = WORD_RE.findall(text.lower())
    counts: Counter = Counter()
    for n in range(1, n_max + 1):
        for i in range(len(tokens) - n + 1):
            gram = tokens[i : i + n]
            if all(t in STOPWORDS for t in gram) or (n == 1 and len(gram[0]) < 3):
                continue
            if gram[0] in STOPWORDS and gram[-1] in STOPWORDS:
                continue
            counts[" ".join(gram)] += 1
    return counts


def log_odds(
    ai: Counter, human: Counter, prior_scale: float
) -> list[tuple[str, float, int, int]]:
    """Monroe, Colaresi & Quinn (2008) log-odds with an informative Dirichlet prior.

    The prior is the pooled corpus itself, scaled to `prior_scale` pseudo-counts,
    which shrinks rare n-grams toward zero instead of letting a single hit in a
    small corpus top the list. Returns (gram, z, ai_count, human_count).
    """
    pooled = ai + human
    total = sum(pooled.values()) or 1
    n_ai, n_h = sum(ai.values()), sum(human.values())
    a0 = prior_scale
    out = []
    for gram, pc in pooled.items():
        alpha = a0 * pc / total
        y_a, y_h = ai.get(gram, 0), human.get(gram, 0)
        la = math.log((y_a + alpha) / (n_ai + a0 - y_a - alpha))
        lh = math.log((y_h + alpha) / (n_h + a0 - y_h - alpha))
        var = 1 / (y_a + alpha) + 1 / (y_h + alpha)
        out.append((gram, (la - lh) / math.sqrt(var), y_a, y_h))
    return out


def cmd_mine(args: argparse.Namespace) -> int:
    root = corpus_dir()
    all_records = read_records(root)
    records = _filter(latest_by_text(all_records, args.version), args)
    ai_texts, human_texts = _class_texts(
        root, records, args.by, args.assisted_as, getattr(args, "min_words", 0), all_records,
        getattr(args, "min_drop", 0.0),
    )
    ai_c, h_c = Counter(), Counter()
    for t in ai_texts:
        ai_c.update(ngrams(t, args.ngram))
    for t in human_texts:
        h_c.update(ngrams(t, args.ngram))
    ai_words = sum(len(WORD_RE.findall(t)) for t in ai_texts)
    h_words = sum(len(WORD_RE.findall(t)) for t in human_texts)
    scored = [
        s for s in log_odds(ai_c, h_c, args.prior) if s[2] + s[3] >= args.min_count
    ]
    toward_ai = sorted((s for s in scored if s[1] > 0), key=lambda s: -s[1])[: args.top]
    toward_h = sorted((s for s in scored if s[1] < 0), key=lambda s: s[1])[: args.top]
    sides = {
        "provenance": ("agent", "human"),
        "pairs": ("before", "after"),
        "detector": ("AI-Generated", "Human Written"),
    }[args.by]
    out = {
        "contrast": f"{sides[0]} vs {sides[1]} ({args.by})",
        "segments": {sides[0]: len(ai_texts), sides[1]: len(human_texts)},
        "words": {sides[0]: ai_words, sides[1]: h_words},
        "toward_ai": [
            {"gram": g, "z": round(z, 2), "ai": a, "human": h}
            for g, z, a, h in toward_ai
        ],
        "toward_human": [
            {"gram": g, "z": round(z, 2), "ai": a, "human": h}
            for g, z, a, h in toward_h
        ],
        "note": "candidates for review, not tells: |z| >= 1.96 is the usual bar; check each in context before it enters ai-tells.md",
    }
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return EXIT_OK
    print(
        f"contrast: {out['contrast']} — segments {len(ai_texts)}/{len(human_texts)}, words {ai_words}/{h_words}"
    )
    if not ai_texts or not human_texts:
        print(
            "need text on both sides before mining; keep logging checks with --provenance."
        )
        return EXIT_OK
    for title, rows in (
        ("toward AI", out["toward_ai"]),
        ("toward human", out["toward_human"]),
    ):
        print(f"{title}:   z      AI  human  n-gram")
        for r in rows:
            print(f"        {r['z']:>6.2f} {r['ai']:>6} {r['human']:>6}  {r['gram']}")
    print(out["note"])
    return EXIT_OK


def cmd_style(args: argparse.Namespace) -> int:
    root = corpus_dir()
    all_records = read_records(root)
    records = _filter(latest_by_text(all_records, args.version), args)
    a_texts, b_texts = _class_texts(
        root, records, args.by, args.assisted_as, args.min_words, all_records, args.min_drop
    )
    sides = {"detector": ("AI-labelled", "human-labelled"), "provenance": ("agent", "human"),
             "pairs": ("before", "after")}[args.by]
    pa, pb = style_profile(a_texts), style_profile(b_texts)
    rows = []
    for key in pa:
        if key in ("units", "words", "sentences"):
            continue
        va, vb = pa[key], pb[key]
        ratio = round((va + 0.05) / (vb + 0.05), 2)
        rows.append({"feature": key, sides[0]: va, sides[1]: vb, "ratio": ratio})
    out = {"contrast": f"{sides[0]} vs {sides[1]} ({args.by})",
           "units": {sides[0]: pa["units"], sides[1]: pb["units"]},
           "words": {sides[0]: pa["words"], sides[1]: pb["words"]},
           "features": rows,
           "note": "pooled rates (per sentence or per 1,000 words); descriptive, not a test. "
                   "Units are not independent when they come from one document."}
    if args.json:
        print(json.dumps(out, indent=2))
        return EXIT_OK
    print(f"contrast: {out['contrast']} — units {pa['units']}/{pb['units']}, words {pa['words']}/{pb['words']}")
    if not a_texts or not b_texts:
        print("need text on both sides; for pairs, log revisions with --pair-of (or import --pair-with-previous).")
        return EXIT_OK
    print(f"  {'feature':<30} {sides[0]:>13} {sides[1]:>15}  ratio")
    for r in rows:
        print(f"  {r['feature']:<30} {r[sides[0]]:>13} {r[sides[1]]:>15}  {r['ratio']:.2f}")
    print(out["note"])
    return EXIT_OK


def _filter(records: list[dict], args: argparse.Namespace) -> list[dict]:
    note = (getattr(args, "note_contains", None) or "").lower()
    src = getattr(args, "source_contains", None) or ""
    return [r for r in records
            if (not note or note in (r.get("note") or "").lower())
            and (not src or src in (r.get("source_path") or ""))]


def default_terms() -> list[str]:
    """Italic watch-list phrases from the 'Lexical tells' section of ai-tells.md."""
    try:
        doc = AI_TELLS.read_text(encoding="utf-8")
    except OSError:
        return []
    match = re.search(r"^## Lexical tells.*?(?=^## )", doc, re.MULTILINE | re.DOTALL)
    section = match.group(0) if match else ""
    terms: list[str] = []
    for span in re.findall(r"_([^_]+)_", section):
        for part in re.split(r"[;,]", span):
            part = re.sub(r"\s+", " ", part.strip().rstrip(".")).lower()
            if part and len(part.split()) <= 6 and "/" not in part:
                terms.append(part)
            elif "/" in part:
                terms.extend(p.strip() for p in part.split("/") if p.strip())
    seen: dict[str, None] = {}
    for t in terms:
        seen.setdefault(t, None)
    return list(seen)


def cmd_terms(args: argparse.Namespace) -> int:
    root = corpus_dir()
    terms = list(args.term or [])
    if args.terms_file:
        terms += [
            t.strip().lower()
            for t in pathlib.Path(args.terms_file)
            .read_text(encoding="utf-8")
            .splitlines()
            if t.strip()
        ]
    if not terms:
        terms = default_terms()
    all_records = read_records(root)
    records = _filter(latest_by_text(all_records, args.version), args)
    ai_texts, human_texts = _class_texts(
        root, records, args.by, args.assisted_as, getattr(args, "min_words", 0), all_records,
        getattr(args, "min_drop", 0.0),
    )
    ai_blob = "\n".join(ai_texts).lower().replace("’", "'")
    h_blob = "\n".join(human_texts).lower().replace("’", "'")
    ai_words = max(len(WORD_RE.findall(ai_blob)), 1)
    h_words = max(len(WORD_RE.findall(h_blob)), 1)
    rows = []
    for term in terms:
        pattern = re.compile(
            r"(?<!\w)" + re.escape(term).replace(r"\ ", r"\s+") + r"(?!\w)"
        )
        a, h = len(pattern.findall(ai_blob)), len(pattern.findall(h_blob))
        rate_a, rate_h = a / ai_words * 10000, h / h_words * 10000
        ratio = ((a + 0.5) / ai_words) / ((h + 0.5) / h_words)
        if a + h < args.min_count:
            verdict = "insufficient data"
        elif ratio >= 2:
            verdict = "toward AI"
        elif ratio <= 0.5:
            verdict = "toward human"
        else:
            verdict = "no clear signal"
        rows.append(
            {
                "term": term,
                "ai": a,
                "human": h,
                "ai_per_10k": round(rate_a, 2),
                "human_per_10k": round(rate_h, 2),
                "ratio": round(ratio, 2),
                "verdict": verdict,
            }
        )
    rows.sort(key=lambda r: (r["verdict"] == "insufficient data", -r["ratio"]))
    if args.json:
        print(
            json.dumps(
                {
                    "by": args.by,
                    "words": {"ai": ai_words, "human": h_words},
                    "terms": rows,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return EXIT_OK
    print(
        f"{len(terms)} terms vs corpus ({args.by}); words AI-side {ai_words}, human-side {h_words}"
    )
    print("  ratio    AI  human  verdict            term")
    for r in rows:
        print(
            f"  {r['ratio']:>5.2f} {r['ai']:>5} {r['human']:>6}  {r['verdict']:<18} {r['term']}"
        )
    return EXIT_OK


def cmd_pairs(args: argparse.Namespace) -> int:
    root = corpus_dir()
    records = read_records(root)
    index: dict[str, dict] = {}
    for rec in records:
        index[rec.get("id", "")] = rec

    def resolve(ref: str) -> dict | None:
        if ref in index:
            return index[ref]
        for rec in reversed(records):
            if rec.get("text_sha256", "").startswith(ref) or rec.get(
                "id", ""
            ).startswith(ref):
                return rec
        return None

    pairs = []
    for rec in records:
        if rec.get("pair_of"):
            before = resolve(rec["pair_of"])
            if before:
                pairs.append((before, rec))

    def share(r):
        return record_flagged(r)

    out = [
        {
            "before": b["id"],
            "after": a["id"],
            "provenance": f"{b.get('provenance')} -> {a.get('provenance')}",
            "verdict": f"{b.get('prediction_short')} -> {a.get('prediction_short')}",
            "flagged_delta": round(share(a) - share(b), 3),
            "note": a.get("note"),
        }
        for b, a in pairs
    ]
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return EXIT_OK
    if not out:
        print(
            "no pairs yet: log a revision with `check AFTER.md --pair-of <before-id>`."
        )
        return EXIT_OK
    for p in out:
        print(
            f"{p['before']} -> {p['after']}  {p['provenance']:<28} {p['verdict']:<16} Δ flagged {p['flagged_delta']:+.2f}  {p['note'] or ''}"
        )
    return EXIT_OK


# ---------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pangram.py",
        description="Opt-in Pangram detector screen + calibration corpus (ADR 0006/0009). "
        "A screen, never a gate; never a verdict about who wrote a text.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="check a draft and log it to the corpus")
    check.add_argument("file", help="markdown/text file, or - for stdin")
    check.add_argument(
        "--provenance",
        choices=PROVENANCES,
        default="unknown",
        help="who actually wrote this text (ground truth)",
    )
    check.add_argument("--genre", help="genre label, e.g. report, talk, email")
    check.add_argument("--voice", help="voice module applied, e.g. model-report-voice")
    check.add_argument(
        "--pair-of", help="record id (or text-sha prefix) of the version this revises"
    )
    check.add_argument("--note", help="free-text note stored with the record")
    check.add_argument("--model", default=DEFAULT_MODEL)
    check.add_argument(
        "--raw",
        action="store_true",
        help="send the file as-is (keep frontmatter and code)",
    )
    check.add_argument(
        "--dry-run",
        action="store_true",
        help="report words and estimated cost; send nothing",
    )
    check.add_argument(
        "--no-log",
        action="store_true",
        help="do not store text or result in the corpus",
    )
    check.add_argument(
        "--refresh",
        action="store_true",
        help="ignore the cached response for this text",
    )
    check.add_argument(
        "--top", type=int, default=8, help="AI-like windows to list (default 8)"
    )
    check.add_argument("--timeout", type=float, default=300)
    check.add_argument("--poll", type=float, default=1.0, help=argparse.SUPPRESS)
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_check)

    balance = sub.add_parser("balance", help="credit balance (free)")
    balance.set_defaults(func=cmd_balance)

    corpus = sub.add_parser("corpus", help="analyse the logged corpus (offline)")
    csub = corpus.add_subparsers(dest="corpus_command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--version",
            help="only records whose detector version starts with this, e.g. 4.1",
        )
        p.add_argument("--note-contains", help="only records whose note contains this")
        p.add_argument("--source-contains", help="only records whose source path contains this")
        p.add_argument("--json", action="store_true")

    def contrast(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--by",
            choices=("detector", "provenance", "pairs"),
            default="detector",
            help="detector: AI-Generated vs Human Written windows (topic-confounded within one document); "
            "provenance: agent vs human texts; pairs: before vs after of each revision pair (topic held)",
        )
        p.add_argument("--min-words", type=int, default=0, help="ignore detector windows shorter than this")
        p.add_argument("--min-drop", type=float, default=0.0,
                       help="pairs only: keep pairs whose flagged share fell by at least this (e.g. 0.3)")
        p.add_argument(
            "--assisted-as",
            choices=("skip", "ai", "human"),
            default="skip",
            help="how to treat AI-Assisted windows (default skip)",
        )

    style = csub.add_parser(
        "style", help="topic-robust style features (punctuation, 'we', rhythm, back-refs) per side"
    )
    common(style)
    contrast(style)
    style.set_defaults(func=cmd_style)

    stats = csub.add_parser("stats", help="counts by provenance x verdict")
    common(stats)
    stats.set_defaults(func=cmd_stats)

    mine = csub.add_parser(
        "mine", help="contrastive log-odds n-grams -> candidate tells"
    )
    common(mine)
    contrast(mine)
    mine.add_argument("--ngram", type=int, choices=(1, 2, 3), default=2)
    mine.add_argument("--min-count", type=int, default=5)
    mine.add_argument(
        "--prior",
        type=float,
        default=500.0,
        help="Dirichlet prior pseudo-count total (default 500)",
    )
    mine.add_argument("--top", type=int, default=25)
    mine.set_defaults(func=cmd_mine)

    terms = csub.add_parser(
        "terms", help="measure watch-list terms (default: ai-tells.md lexical lists)"
    )
    common(terms)
    contrast(terms)
    terms.add_argument("term", nargs="*", help="terms to test (default: ai-tells.md)")
    terms.add_argument("--terms-file", help="one term per line")
    terms.add_argument("--min-count", type=int, default=3)
    terms.set_defaults(func=cmd_terms)

    pairs = csub.add_parser("pairs", help="before/after revision pairs")
    common(pairs)
    pairs.set_defaults(func=cmd_pairs)

    imp = csub.add_parser(
        "import",
        help="import earlier Pangram results (raw responses, section results.json, JSONL ledgers); no API call",
    )
    imp.add_argument("paths", nargs="+")
    imp.add_argument("--provenance", choices=PROVENANCES, default="unknown")
    imp.add_argument("--genre")
    imp.add_argument(
        "--note-prefix", help="prefix for each record's note, e.g. 'eul4 '"
    )
    imp.add_argument(
        "--pair-with-previous",
        action="store_true",
        help="link a record to an earlier one with the same note but different text (a revision)",
    )
    imp.set_defaults(func=cmd_import)

    label = csub.add_parser(
        "label", help="annotate records after the fact (append-only)"
    )
    label.add_argument("ref", nargs="*", help="record id or text-sha prefix")
    label.add_argument(
        "--note-contains", help="select every record whose note contains this"
    )
    label.add_argument("--provenance", choices=PROVENANCES)
    label.add_argument("--genre")
    label.add_argument("--note")
    label.add_argument("--pair-of")
    label.set_defaults(func=cmd_label)

    lst = csub.add_parser(
        "list", help="list records (id, provenance, status, flagged share, note)"
    )
    lst.add_argument("--json", action="store_true")
    lst.set_defaults(func=cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
