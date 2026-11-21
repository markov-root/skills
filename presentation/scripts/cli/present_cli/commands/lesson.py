"""`present lesson new|route|list`: the improvement loop (task 0020; ADR 0012; specification §9).

A proven finding is recorded once as an SE `lesson` record in `<talk>/docs/lessons/`, then routed
to the single layer that owns it. Skill-owned targets are routed through `skill-feedback` (the
shared transport); consumer-owned targets (tokens, library) become a consumer repository task.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from ..console import Effects, Result, leaf
from ..context import (
    Repo,
    engineering_cli,
    require_repo,
    require_talk,
    skill_feedback_cli,
)

# --------------------------------------------------------------------------- the ownership table

# ADR 0012 §3. Key = the `--target` value. `skill` is the skill-feedback recipient; `consumer`
# targets are changed by a task in the consumer repository; `talk` has nothing to route.
OWNERS: dict[str, dict[str, Any]] = {
    "presentation": {
        "about": "the standard: protocol, artifact contract, script format, claims, generic deck rules",
        "owner": "presentation knowledge",
        "ships": "a skill release",
        "skill": "presentation",
        "feature": "knowledge",
    },
    "components": {
        "about": "how a component draws, or a new generic component",
        "owner": "presentation component library",
        "ships": "a COMPONENTS_VERSION bump, gallery diff",
        "skill": "presentation",
        "feature": "components",
    },
    "tokens": {
        "about": "a brand value: colour, font, size, logo",
        "owner": "consumer _shared/brand/tokens.json",
        "ships": "a token version bump",
        "consumer": True,
    },
    "library": {
        "about": "a recurring slide or visual",
        "owner": "consumer library/",
        "ships": "present library promote",
        "consumer": True,
    },
    "visuals": {
        "about": "graphic craft: encoding, annotation, composition",
        "owner": "visuals knowledge",
        "ships": "a visuals release",
        "skill": "visuals",
        "feature": "knowledge",
    },
    "writing-voice": {
        "about": "the speaker's voice, register, tone, wording habits",
        "owner": "writing presentation-voice (private)",
        "ships": "a writing release",
        "skill": "writing",
        "feature": "presentation-voice",
    },
    "writing": {
        "about": "prose craft in general, or the re-voice check",
        "owner": "writing knowledge or scripts",
        "ships": "a writing release",
        "skill": "writing",
        "feature": "knowledge",
    },
    "software-engineering": {
        "about": "records, handoffs, validation",
        "owner": "software-engineering",
        "ships": "an SE release",
        "skill": "software-engineering",
        "feature": "document-system",
    },
    "talk": {
        "about": "only this talk",
        "owner": "the talk itself",
        "ships": "nothing to route",
    },
}

PROOFS = {
    "explicit_user": ("explicit_user", "the maintainer's explicit verdict"),
    "deterministic": ("deterministic", "a deterministic measurement"),
    "agent": (
        "agent_judgment",
        "an agent's judgment only: filed as an idea, never a rule change",
    ),
}
KINDS = ("idea", "friction", "praise")

LESSON_FILE = re.compile(r"^(\d{4})-.+\.md$")
ROUTING_PENDING = "Routing: not routed yet (`present lesson route`)."

LESSON_ROLE_BLOCK = """      - name: lesson
        include: ["lessons/[0-9][0-9][0-9][0-9]-*.md"]
        index: "lessons/README.md"
        id_prefix_digits: 4
        contract: { version: 1, role: lesson }
"""

LESSONS_README = """# Lessons

Proven findings from this talk, each routed to the layer that owns it (`present lesson`). Open
lessons are listed by `present talk status`.

| # | Status | Record |
| --- | --- | --- |
"""


def owners_table() -> str:
    rows = [f"{k}: {v['about']} → {v['owner']}" for k, v in OWNERS.items()]
    return "--target one of: " + "; ".join(rows)


# --------------------------------------------------------------------------- reading lessons


def split_record(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.index("\n---\n", 4)
    return (yaml.safe_load(text[4:end]) or {}), text[end + 5 :]


def sections(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", body, re.M | re.S):
        out[m.group(1).strip()] = m.group(2).strip()
    return out


def lesson_paths(talk: Path) -> list[Path]:
    d = talk / "docs" / "lessons"
    return (
        sorted(p for p in d.glob("*.md") if LESSON_FILE.match(p.name))
        if d.is_dir()
        else []
    )


def read_lesson(path: Path) -> dict[str, Any]:
    fm, _ = split_record(path.read_text(encoding="utf-8"))
    pl = fm.get("present_lesson") or {}
    target = pl.get("target")
    routed = pl.get("routed")
    return {
        "talk": path.parents[2].name,
        "id": str(fm.get("id", path.name[:4])),
        "title": fm.get("title", ""),
        "state": (fm.get("engineering_document") or {}).get("state", fm.get("status")),
        "target": target,
        "proof": pl.get("proof"),
        "routed": routed,
        "open": bool(target) and target != "talk" and not routed,
        "path": path,
    }


def open_lessons(talk: Path) -> tuple[int, int]:
    """(open, total) lessons of one talk; `talk status` shows this."""
    recs = [read_lesson(p) for p in lesson_paths(talk)]
    return sum(r["open"] for r in recs), len(recs)


# --------------------------------------------------------------------------- lesson new


def _configure_new(p):
    p.add_argument(
        "talk",
        nargs="?",
        help="talk folder; default the talk containing the working directory",
    )
    p.add_argument("--title", required=True, help="the lesson in a few words")
    p.add_argument(
        "--target",
        required=True,
        help="the owning layer (ADR 0012 table; `present explain lesson new`)",
    )
    p.add_argument(
        "--proof",
        required=True,
        choices=sorted(PROOFS),
        help="explicit_user (maintainer's verdict), deterministic (a measurement) or agent (an idea only)",
    )
    p.add_argument(
        "--evidence",
        action="append",
        default=[],
        metavar="PATH",
        help="evidence file inside the repository (repeatable; required unless --proof agent)",
    )
    p.add_argument("--observation", required=True, help="what happened in this talk")
    p.add_argument("--generalisation", required=True, help="the transferable inference")
    p.add_argument(
        "--boundary", required=True, help="where it applies, and where it does not"
    )
    p.add_argument("--consequence", help="what changes once the owner ships it")


def _evidence(res: Result, repo: Repo, talk: Path, raw: list[str]) -> list[str] | None:
    out = []
    for item in raw:
        p = Path(item)
        cands = [p] if p.is_absolute() else [Path.cwd() / p, talk / p, repo.root / p]
        hit = next((c for c in cands if c.exists()), None)
        if hit is None:
            res.error(
                "evidence_not_found",
                f"evidence {item!r} does not exist.",
                repairable=True,
                next="pass a file inside the repository (correspondence, a check report, a diff)",
            )
            return None
        try:
            out.append(repo.rel(hit))
        except ValueError:
            res.error(
                "evidence_outside_repository",
                f"evidence {item!r} is outside {repo.root.name}.",
                repairable=True,
                next="copy the evidence into the talk (e.g. materials/) first",
            )
            return None
    return out


def _declare_role(eng_yaml: Path) -> str | None:
    """Text of engineering.yaml with the lesson role declared, or None if it cannot be done safely."""
    text = eng_yaml.read_text(encoding="utf-8")
    if re.search(r"^\s*- name: lesson\s*$", text, re.M):
        return text
    m = re.search(
        r"^      # - name: lesson\n(?:      #.*\n)*?      #   contract: \{ version: 1, role: lesson \}\n",
        text,
        re.M,
    )
    if not m:
        return None
    return text[: m.start()] + LESSON_ROLE_BLOCK + text[m.end() :]


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _lesson_body(num: str, ns, target: str, evidence: list[str]) -> str:
    o = OWNERS[target]
    proof_text = PROOFS[ns.proof][1]
    ev = "\n".join(f"- `{e}`" for e in evidence) or "- none recorded (agent judgment)"
    if target == "talk":
        default_consequence = "Applies to this talk only; nothing to route."
    else:
        default_consequence = (
            f"Routed to **{o['owner']}**, which ships it as {o['ships']}; later talks "
            "pick it up through their pins."
        )
    routing = (
        "Routing: this talk only; nothing to route."
        if target == "talk"
        else ROUTING_PENDING
    )
    return (
        f"# Lesson {num}: {ns.title}\n\n"
        f"## Context\n\n{ns.observation.strip()}\n\n"
        f"## Durable lesson\n\n{ns.generalisation.strip()}\n\n"
        f"## Boundary\n\n{ns.boundary.strip()}\n\n"
        f"## Evidence\n\nProof: `{ns.proof}`, {proof_text}.\n\n{ev}\n\n"
        f"## Consequence\n\n{(ns.consequence or default_consequence).strip()}\n\n"
        f"Target: `{target}` ({o['owner']}).\n\n{routing}\n"
    )


def _fill_lesson(path: Path, ns, target: str, evidence: list[str], owner: str) -> None:
    text = path.read_text(encoding="utf-8")
    end = text.index("\n---\n", 4) + 5
    front = text[:end]
    one_line = " ".join(ns.boundary.split())
    front = front.replace("LESSON OWNER", owner)
    front = front.replace("scope: APPLICABILITY BOUNDARY", f"scope: {_q(one_line)}")
    front = front.replace(
        "boundary: WHEN THIS INFERENCE APPLIES", f"boundary: {_q(one_line)}"
    )
    front = re.sub(
        r"^summary: .*$",
        lambda _m: f"summary: {_q(' '.join(ns.generalisation.split())[:200])}",
        front,
        count=1,
        flags=re.M,
    )
    block = yaml.safe_dump(
        {
            "present_lesson": {
                "target": target,
                "proof": ns.proof,
                "evidence": evidence,
                "routed": None,
            }
        },
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    front = front.replace('superseded_by: ""\n', 'superseded_by: ""\n' + block, 1)
    leftover = [
        p
        for p in (
            "LESSON OWNER",
            "APPLICABILITY BOUNDARY",
            "WHEN THIS INFERENCE APPLIES",
        )
        if p in front
    ]
    if leftover or "present_lesson:" not in front:
        raise RuntimeError(
            f"lesson template changed; cannot fill {leftover or 'present_lesson'}"
        )
    num = path.name[:4]
    path.write_text(
        front + "\n" + _lesson_body(num, ns, target, evidence), encoding="utf-8"
    )
    split_record(path.read_text(encoding="utf-8"))  # must still parse


@leaf(
    "lesson",
    "new",
    summary="record a proven finding as a talk lesson with its owner (ADR 0012)",
    task="0020",
    configure=_configure_new,
    effects=Effects(
        writes=True,
        description="Writes <talk>/docs/lessons/NNNN-*.md and its index; declares "
        "the lesson role in docs/engineering.yaml on first use. Runs `engineering document new` "
        "and `validate`; rolls every write back if either fails.",
    ),
)
def lesson_new(ns, res: Result) -> Result:
    from .talk import _allocate, _owner, _validate_docs

    repo = require_repo(res)
    if repo is None:
        return res
    talk = require_talk(res, repo, ns.talk)
    if talk is None:
        return res
    target = ns.target.strip().lower()
    if target not in OWNERS:
        res.data = {
            "owners": {
                k: {"about": v["about"], "owner": v["owner"]} for k, v in OWNERS.items()
            }
        }
        return res.error(
            "target_unknown",
            f"unknown owner {ns.target!r}.",
            repairable=True,
            next=owners_table(),
        )
    if ns.proof != "agent" and not ns.evidence:
        return res.error(
            "evidence_missing",
            f"--proof {ns.proof} needs at least one --evidence file.",
            repairable=True,
            next="pass --evidence <path> (or --proof agent to file an idea)",
        )
    evidence = _evidence(res, repo, talk, ns.evidence)
    if evidence is None:
        return res
    eng = engineering_cli()
    if eng is None:
        return res.error(
            "capability_unavailable",
            "software-engineering `engineering` not found; a lesson "
            "is an SE record and is allocated only through it. Nothing was written.",
            repairable=True,
            next="install the software-engineering skill, then rerun",
        )
    docs = talk / "docs"
    eng_yaml = docs / "engineering.yaml"
    if not eng_yaml.is_file():
        return res.error(
            "records_missing",
            f"{repo.rel(docs)}/engineering.yaml does not exist.",
            repairable=True,
            next="scaffold the talk with `present talk new`",
        )
    declared = _declare_role(eng_yaml)
    if declared is None:
        return res.error(
            "lesson_role_undeclared",
            "docs/engineering.yaml has no lesson role and no "
            "commented block to enable.",
            repairable=True,
            next="add to docs.currency.roles:\n" + LESSON_ROLE_BLOCK,
        )

    # Every write below is undone if any step fails: never a half-written record.
    eng_before = eng_yaml.read_text(encoding="utf-8")
    ldir = docs / "lessons"
    readme = ldir / "README.md"
    dir_existed, readme_before = (
        ldir.is_dir(),
        (readme.read_text(encoding="utf-8") if readme.is_file() else None),
    )
    baseline = set(_validate_docs(eng, docs))
    lesson: Path | None = None

    def rollback() -> None:
        if lesson is not None and lesson.exists():
            lesson.unlink()
        eng_yaml.write_text(eng_before, encoding="utf-8")
        if readme_before is None:
            readme.unlink(missing_ok=True)
        else:
            readme.write_text(readme_before, encoding="utf-8")
        if not dir_existed and ldir.is_dir() and not any(ldir.iterdir()):
            ldir.rmdir()

    try:
        eng_yaml.write_text(declared, encoding="utf-8")
        ldir.mkdir(exist_ok=True)
        if readme_before is None:
            readme.write_text(LESSONS_README, encoding="utf-8")
        before = {p.name for p in ldir.iterdir()}
        try:
            lesson = _allocate(eng, docs, "lesson", ns.title)
        finally:
            if lesson is None:  # allocation failed: remove anything it may have left
                for p in ldir.iterdir():
                    if p.name not in before:
                        p.unlink()
        _fill_lesson(lesson, ns, target, evidence, _owner())
        with readme.open("a", encoding="utf-8") as fh:
            fh.write(f"| [{lesson.name[:4]}]({lesson.name}) | draft | {ns.title} |\n")
        findings = [f for f in _validate_docs(eng, docs) if f not in baseline]
    except Exception as exc:
        rollback()
        return res.error(
            "lesson_not_written", f"{exc}. Nothing was written.", repairable=False
        )
    if findings:
        rollback()
        return res.error(
            "records_invalid",
            f"engineering document validate: {findings[0]}. Nothing was written.",
            repairable=True,
            next=f"engineering document validate --project-root {repo.rel(docs)}",
        )
    rel = repo.rel(lesson)
    res.data = {
        "lesson": rel,
        "id": lesson.name[:4],
        "target": target,
        "proof": ns.proof,
        "evidence": evidence,
        "routable": target != "talk",
    }
    res.text.append(f"created {rel}  (target {target}, proof {ns.proof})")
    if target == "talk":
        res.text.append("this talk only: nothing to route.")
    else:
        res.text.append(f"next: present lesson route {rel}")
    return res


# --------------------------------------------------------------------------- lesson route


def _configure_route(p):
    p.add_argument("lesson", help="lesson file, `<talk>/NNNN`, or `NNNN` inside a talk")
    p.add_argument(
        "--kind",
        choices=KINDS,
        help="skill-feedback kind (default idea; --proof agent lessons route only as idea)",
    )
    p.add_argument(
        "--consumer-task",
        metavar="NNNN",
        help="for tokens/library: the consumer repository task you opened; records the routing",
    )
    p.add_argument(
        "--feedback-dir",
        metavar="PATH",
        help="pass --dir PATH to skill-feedback (write under PATH/docs/feedback)",
    )


def _resolve_lesson(res: Result, repo: Repo, ref: str) -> Path | None:
    for c in (Path.cwd() / ref, repo.root / ref):
        if c.is_file():
            return c.resolve()
    parts = Path(ref).parts
    num = parts[-1] if parts else ""
    if re.fullmatch(r"\d{1,4}", num):
        talk = require_talk(
            res, repo, str(Path(*parts[:-1])) if len(parts) > 1 else None
        )
        if talk is None:
            return None
        hits = [p for p in lesson_paths(talk) if p.name[:4] == num.zfill(4)]
        if hits:
            return hits[0]
    res.error(
        "lesson_not_found",
        f"no lesson {ref!r}.",
        repairable=True,
        next="present lesson list --all",
    )
    return None


def _routed_text(
    text: str, routed: dict[str, Any], transition: bool, day: str
) -> tuple[str, bool]:
    end = text.index("\n---\n", 4) + 5
    front, body = text[:end], text[end:]
    block = yaml.safe_dump(
        {"routed": routed}, sort_keys=False, allow_unicode=True, width=100
    )
    block = "".join("  " + ln + "\n" for ln in block.splitlines())
    if front.count("\n  routed: null\n") != 1:
        raise RuntimeError(
            "present_lesson.routed is not `null`; the lesson was edited by hand"
        )
    front = front.replace("  routed: null\n", block, 1)
    front = re.sub(
        r'^(\s*)updated: "\d{4}-\d{2}-\d{2}"$',
        lambda m: f'{m.group(1)}updated: "{day}"',
        front,
        flags=re.M,
    )
    moved = False
    if (
        transition
        and re.search(r"^status: draft$", front, re.M)
        and "  transitions: []\n" in front
    ):
        front = re.sub(
            r"^status: draft$", "status: standing", front, count=1, flags=re.M
        )
        front = re.sub(
            r"^  state: draft$", "  state: standing", front, count=1, flags=re.M
        )
        front = front.replace(
            "  transition_history: unverified\n", "  transition_history: complete\n", 1
        )
        reason = f"Proven ({routed['proof']}) and routed to {routed['owner']}."
        front = front.replace(
            "  transitions: []\n",
            "  transitions:\n  - from: draft\n    to: standing\n"
            f'    at: "{day}"\n    reason: {_q(reason)}\n',
            1,
        )
        moved = True
    ref = routed.get("feedback") or (
        f"consumer task {routed['consumer_task']}"
        if routed.get("consumer_task")
        else ""
    )
    line = (
        f"Routing: routed {day} to `{routed['owner']}`"
        + (f" as `{routed['kind']}`" if routed.get("kind") else "")
        + (f" ({ref})." if ref else ".")
    )
    body = (
        body.replace(ROUTING_PENDING, line)
        if ROUTING_PENDING in body
        else body.rstrip("\n") + f"\n\n{line}\n"
    )
    return front + body, moved


def _note(fm: dict[str, Any], body: str, rel: str) -> str:
    s = sections(body)
    pl = fm["present_lesson"]
    return (
        f"Lesson routed from a talk (present lesson; presentation ADR 0012): {fm.get('title', '')}\n\n"
        f"Observation: {s.get('Context', '')}\n\n"
        f"Generalisation: {s.get('Durable lesson', '')}\n\n"
        f"Boundary: {s.get('Boundary', '')}\n\n"
        f"Proof: {pl.get('proof')}. Lesson record: {rel}.\n"
    )


@leaf(
    "lesson",
    "route",
    summary="route a lesson to its owner through skill-feedback, or name the consumer task to open",
    task="0020",
    configure=_configure_route,
    effects=Effects(
        writes=True,
        description="Skill-owned targets: files one skill-feedback note (the owner's "
        "docs/feedback and the shared event ledger), then records the routing in the lesson file "
        "and its index. Consumer-owned targets: files nothing; records the routing only with "
        "--consumer-task. Refuses to route a lesson twice.",
    ),
)
def lesson_route(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    path = _resolve_lesson(res, repo, ns.lesson)
    if path is None:
        return res
    rel = repo.rel(path)
    text = path.read_text(encoding="utf-8")
    fm, body = split_record(text)
    pl = fm.get("present_lesson")
    if not isinstance(pl, dict) or pl.get("target") not in OWNERS:
        return res.error(
            "lesson_unmanaged",
            f"{rel} has no present_lesson target.",
            repairable=True,
            next="record it with `present lesson new`",
        )
    target, proof = pl["target"], pl.get("proof")
    o = OWNERS[target]
    res.data = {"lesson": rel, "target": target, "owner": o["owner"], "proof": proof}
    if pl.get("routed"):
        res.data["routed"] = pl["routed"]
        return res.error(
            "already_routed",
            f"{rel} was routed on {pl['routed'].get('date')} to "
            f"{pl['routed'].get('owner')}; a lesson is routed once.",
            repairable=False,
            next="a misrouted note is re-filed by its owner, not routed again (ADR 0012)",
        )
    if target == "talk":
        res.data["filed"] = False
        res.text.append(f"{rel}: this talk only; nothing to route.")
        return res
    kind = ns.kind or "idea"
    if proof == "agent" and kind != "idea":
        return res.error(
            "proof_insufficient",
            f"{rel} rests on agent judgment; it routes only as an idea, "
            "never as a rule change (ADR 0012).",
            repairable=True,
            next=f"present lesson route {rel} --kind idea",
        )
    # Records are dated by the real clock (the SE validator checks `updated` against it), not PRESENT_TODAY.
    day = _dt.date.today().isoformat()

    if o.get("consumer"):
        if not ns.consumer_task:
            title = f"Lesson {fm.get('id')}: {fm.get('title')} ({target})"
            task_cmd = (
                f"engineering document new task --title {_q(title)} --project-root docs"
            )
            res.data.update(
                {
                    "filed": False,
                    "consumer_task": {
                        "command": task_cmd,
                        "evidence": rel,
                        "ships": o["ships"],
                    },
                }
            )
            res.text.append(
                f"{rel} is owned by the consumer repository ({o['owner']}); nothing was filed."
            )
            res.text.append(
                f"open a repository task (from {repo.root.name}/): {task_cmd}"
            )
            res.text.append(f"  cite {rel} as its evidence; it ships as {o['ships']}.")
            res.text.append(
                f"then record it: present lesson route {rel} --consumer-task NNNN"
            )
            return res
        num = ns.consumer_task.zfill(4)
        if not list((repo.root / "docs" / "tasks").glob(f"{num}-*.md")):
            return res.error(
                "consumer_task_not_found",
                f"no docs/tasks/{num}-*.md in {repo.root.name}.",
                repairable=True,
                next="open the task first (rerun without --consumer-task)",
            )
        routed = {"date": day, "owner": target, "proof": proof, "consumer_task": num}
        new_text, moved = _routed_text(text, routed, proof != "agent", day)
        _write_routed(path, new_text, moved)
        res.data.update({"filed": False, "routed": routed})
        res.text.append(f"recorded: {rel} → consumer task {num}")
        return res

    fb = skill_feedback_cli()
    if fb is None:
        return res.error(
            "capability_unavailable",
            "`skill-feedback` not found; it is the lesson transport. "
            "Nothing was filed or written.",
            repairable=True,
            next="install the skill-feedback skill, then rerun",
        )
    source = PROOFS[proof][0] if proof in PROOFS else "agent_judgment"
    cmd = [
        fb,
        o["skill"],
        "-",
        "--kind",
        kind,
        "--source",
        source,
        "--feature",
        o["feature"],
        "--impact",
        "high" if proof == "explicit_user" else "unknown",
        "--evidence",
        rel,
        *sum((["--evidence", e] for e in pl.get("evidence") or []), []),
        "--tag",
        "present-lesson",
        "--json",
    ]
    if ns.feedback_dir:
        cmd += ["--dir", str(Path(ns.feedback_dir).resolve())]
    try:
        proc = subprocess.run(
            cmd,
            input=_note(fm, body, rel),
            capture_output=True,
            text=True,
            timeout=120,
            cwd=repo.root,
        )
    except OSError as exc:
        return res.error(
            "capability_unavailable",
            f"skill-feedback could not run: {exc}. Nothing was written.",
            repairable=True,
            next="check the skill-feedback install",
        )
    reply: dict[str, Any] = {}
    try:
        reply = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        pass
    if proc.returncode != 0 or not reply.get("ok"):
        msg = (proc.stderr or proc.stdout).strip()[:400]
        return res.error(
            "feedback_failed",
            f"skill-feedback refused the note: {msg}. The lesson is unchanged.",
            repairable=True,
            next="fix the lesson text (no home paths or private data), then rerun",
        )
    routed = {
        "date": day,
        "owner": target,
        "skill": o["skill"],
        "kind": kind,
        "proof": proof,
        "feedback": reply.get("id"),
    }
    new_text, moved = _routed_text(text, routed, proof != "agent", day)
    _write_routed(path, new_text, moved)
    res.data.update(
        {"filed": True, "routed": routed, "feedback_file": reply.get("file")}
    )
    res.text.append(
        f"filed {kind} for {o['skill']} ({reply.get('id')}); recorded in {rel}"
    )
    return res


def _write_routed(path: Path, text: str, moved: bool) -> None:
    path.write_text(text, encoding="utf-8")
    if moved:
        readme = path.parent / "README.md"
        if readme.is_file():
            t = readme.read_text(encoding="utf-8")
            t = t.replace(
                f"| [{path.name[:4]}]({path.name}) | draft |",
                f"| [{path.name[:4]}]({path.name}) | standing |",
            )
            readme.write_text(t, encoding="utf-8")


# --------------------------------------------------------------------------- lesson list


def _configure_list(p):
    p.add_argument(
        "talk",
        nargs="?",
        help="talk folder; default the talk containing the working directory",
    )
    p.add_argument(
        "--all", action="store_true", help="every standard-1 talk in the repository"
    )
    p.add_argument("--open", action="store_true", help="only lessons still to route")


@leaf(
    "lesson",
    "list",
    summary="list a talk's lessons (or every talk's), with their owner and routing",
    task="0020",
    configure=_configure_list,
    effects=Effects(description="Reads lesson records."),
)
def lesson_list(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    if ns.all:
        talks = repo.talks()
    else:
        talk = require_talk(res, repo, ns.talk)
        if talk is None:
            return res
        talks = [talk]
    rows = [read_lesson(p) for t in talks for p in lesson_paths(t)]
    if ns.open:
        rows = [r for r in rows if r["open"]]
    out = []
    for r in rows:
        r = {**r, "path": repo.rel(r["path"])}
        out.append(r)
        status = (
            "open"
            if r["open"]
            else (
                "local"
                if r["target"] == "talk"
                else f"routed {r['routed'].get('date')}"
                if r["routed"]
                else "-"
            )
        )
        res.text.append(
            f"{r['talk']}/{r['id']}  {str(r['state']):<9} {str(r['target']):<21} "
            f"{str(r['proof']):<14} {status:<17} {r['title']}"
        )
    res.data = {"lessons": out, "open": sum(r["open"] for r in out)}
    if not out:
        res.text.append("no lessons" + (" open" if ns.open else "") + ".")
    return res
