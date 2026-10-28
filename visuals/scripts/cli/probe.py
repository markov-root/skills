"""Cold-reader comprehension probes. Findings are advisory, never gates."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import discovery


class ProbeUnavailable(Exception):
    """The instrument cannot run; no comprehension verdict exists."""


def brief_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        match = re.match(r"^\s*#+\s+(.*\S)\s*$", line)
        if match:
            current = match.group(1).strip().casefold()
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def parse_intent(brief: str) -> tuple[str, list[dict[str, str]]]:
    sections = brief_sections(brief)
    claim = next(
        (value for key, value in sections.items() if "one thing" in key and value), ""
    )
    claim = re.sub(r"<!--.*?-->", "", claim, flags=re.S).strip()
    if not claim or claim.casefold() == "undecided":
        raise ProbeUnavailable("BRIEF.md has no filled 'one thing' claim")
    criteria = "\n".join(
        value for key, value in sections.items() if "acceptance" in key
    )
    # Explicit question/answer pairs are criterion-backed, reproducible checks.
    # Other acceptance bullets are context for the independent evaluator but
    # cannot safely be turned into a factual question by a heuristic.
    questions = []
    for line in criteria.splitlines():
        match = re.match(r"^\s*[-*]\s*Q:\s*(.+?)\s*\|\s*A:\s*(.+?)\s*$", line, re.I)
        if match:
            question, expected = match.group(1).strip(), match.group(2).strip()
            questions.append(
                {
                    "id": hashlib.sha256(question.encode()).hexdigest()[:12],
                    "question": question,
                    "expected": expected,
                }
            )
    return claim, questions


def untestable_acceptance(brief: str) -> list[dict[str, str]]:
    """Keep prose acceptance bullets visible without inventing expected answers."""
    sections = brief_sections(brief)
    criteria = "\n".join(value for key, value in sections.items() if "acceptance" in key)
    result = []
    for line in criteria.splitlines():
        match = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if match and not re.match(r"^Q:\s*.+?\s*\|\s*A:\s*.+?\s*$", match[1], re.I):
            result.append({"criterion": match[1], "outcome": "not-determinable",
                           "reason": "declare an explicit Q: … | A: … pair for a factual probe"})
    return result


def resolve_visual(root: Path, slug: str) -> Path:
    matches = [
        path
        for path in discovery.discover_visuals(root)
        if path.name == slug or path.relative_to(root).as_posix() == slug
    ]
    if len(matches) != 1:
        raise ProbeUnavailable(
            f"visual {slug!r} resolves to {len(matches)} directories"
        )
    return matches[0]


def delivery_previews(visual_dir: Path, version_name: str | None = None) -> tuple[str, list[tuple[str, Path]]]:
    if version_name is None:
        latest = visual_dir / "latest"
        if not latest.is_symlink() or not latest.resolve().is_dir():
            raise ProbeUnavailable(f"{latest} is missing or dangling")
        version = latest.resolve()
    else:
        from store import VERSION_RE
        if not VERSION_RE.fullmatch(version_name):
            raise ProbeUnavailable(f"invalid version {version_name!r} (expected vX.Y.Z)")
        version = visual_dir / version_name
        if not version.is_dir() or version.is_symlink():
            raise ProbeUnavailable(f"version {version_name!r} is absent or is a symlink")
    receipt_path = version / "receipt.json"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        frames = receipt["frames"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ProbeUnavailable(
            f"cannot read frame receipt at {receipt_path}: {exc}"
        ) from exc
    previews = []
    for frame in frames:
        name = frame["name"]
        stem = Path(name).stem
        candidates = sorted((version / "previews").glob(f"{stem}-*.png"))
        if len(candidates) != 1:
            raise ProbeUnavailable(
                f"expected one delivery preview for {name} in {version / 'previews'}"
            )
        previews.append((stem, candidates[0]))
    if not previews:
        raise ProbeUnavailable(f"no frames in {receipt_path}")
    return version.name, previews


def cold_prompt(questions: list[dict[str, str]]) -> str:
    lines = [
        "Look only at the attached graphic. Do not use tools or inspect files.",
        "What does this graphic say? Answer as JSON with keys claim and answers.",
        "answers is an object keyed by question ID. State only what you can read; "
        "use 'unreadable' when needed.",
    ]
    for item in questions:
        lines.append(f"{item['id']}: {item['question']}")
    return "\n".join(lines)


def evaluator_prompt(
    claim: str, questions: list[dict[str, str]], cold: dict, criteria: str = ""
) -> str:
    return (
        "Compare a cold reader's description against the intended claim and factual "
        "questions. Judge comprehension only. Do not assess graphic quality. "
        'Return JSON: {"open": {"status": "pass|fail|uncertain", '
        '"reason": string}, "targeted": {question_id: '
        '{"status": "pass|fail|uncertain", "reason": string}}. '
        "A failure requires a clear contradiction or missed load-bearing fact; "
        "otherwise use uncertain.\n"
        f"Intended claim: {claim}\n"
        f"Acceptance criteria from brief: {criteria}\n"
        f"Acceptance questions and expected answers: {json.dumps(questions, ensure_ascii=False)}\n"
        f"Cold response: {json.dumps(cold, ensure_ascii=False)}"
    )


def dispatch(prompt: str, *, image: Path | None = None, binary: str = "codex") -> dict:
    """Each call is a fresh, ephemeral agent in an empty cwd."""
    if shutil.which(binary) is None:
        raise ProbeUnavailable(f"{binary} exec unavailable on PATH")
    with tempfile.TemporaryDirectory(prefix="visuals-probe-") as scratch:
        output = Path(scratch) / "response.json"
        command = [
            binary,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--sandbox",
            "read-only",
            "-C",
            scratch,
            "-o",
            str(output),
        ]
        if image is not None:
            command += ["--image", str(image)]
        command += ["--", prompt]  # --image accepts multiple files; terminate its list
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, "CI": "1"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProbeUnavailable(f"agent dispatch failed: {exc}") from exc
        if result.returncode != 0 or not output.is_file():
            raise ProbeUnavailable(
                f"agent dispatch failed (exit {result.returncode}): "
                f"{(result.stderr or result.stdout)[-500:]}"
            )
        try:
            return json.loads(output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProbeUnavailable(f"agent did not return JSON: {exc}") from exc


def load_checks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or not isinstance(data.get("checks"), list):
            raise ValueError("unsupported persisted probe format")
        return data["checks"]
    except (OSError, ValueError, TypeError) as exc:
        raise ProbeUnavailable(f"cannot read persisted probes {path}: {exc}") from exc


def reconcile(
    checks: list[dict], *, claim: str, questions: list[dict], frames: list[str]
) -> list[dict]:
    expected = {item["id"]: item["expected"] for item in questions}
    for check in checks:
        if check["frame"] not in frames:
            check["state"] = "stale"
            check["reason"] = "frame missing or renamed"
        elif check["id"] == "open" and check.get("expected") != claim:
            check["state"] = "stale"
            check["reason"] = "brief claim changed"
        elif check["id"] != "open" and expected.get(check["id"]) != check.get(
            "expected"
        ):
            check["state"] = "stale"
            check["reason"] = "acceptance question or expected answer changed"
    return checks


def save_checks(path: Path, checks: list[dict]) -> None:
    payload = {"schema_version": 1, "checks": checks}
    fd, name = tempfile.mkstemp(prefix=".probes-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def run(visual_dir: Path, *, execute: bool = False, binary: str = "codex",
        version: str | None = None) -> dict:
    brief_path = visual_dir / "BRIEF.md"
    try:
        brief = brief_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProbeUnavailable(f"cannot read {brief_path}: {exc}") from exc
    claim, questions = parse_intent(brief)
    criteria = "\n".join(
        value for key, value in brief_sections(brief).items() if "acceptance" in key
    )
    version, previews = delivery_previews(visual_dir, version)
    checks_path = visual_dir / "probes.json"
    checks = reconcile(
        load_checks(checks_path),
        claim=claim,
        questions=questions,
        frames=[name for name, _ in previews],
    )
    report = {
        "schema_version": 1,
        "visual": visual_dir.name,
        "version": version,
        "mode": "execute" if execute else "dry-run",
        "claim": claim,
        "questions": questions,
        "not_determinable": untestable_acceptance(brief),
        "frames": [],
        "persisted": checks,
        "cost": "two fresh Codex agent calls per frame; quota usage varies and exact amount is unavailable"
        if execute
        else "none",
    }
    if not execute:
        for name, preview in previews:
            report["frames"].append(
                {
                    "frame": name,
                    "preview": str(preview),
                    "cold_prompt": cold_prompt(questions),
                }
            )
        return report
    now = datetime.now(timezone.utc).isoformat()
    for name, preview in previews:
        cold = dispatch(cold_prompt(questions), image=preview, binary=binary)
        verdict = dispatch(
            evaluator_prompt(claim, questions, cold, criteria), binary=binary
        )
        report["frames"].append(
            {
                "frame": name,
                "preview": str(preview),
                "cold": cold,
                "comparison": verdict,
            }
        )
        entries = [("open", claim, verdict.get("open", {}))]
        entries += [
            (
                item["id"],
                item["expected"],
                verdict.get("targeted", {}).get(item["id"], {}),
            )
            for item in questions
        ]
        for check_id, expected, result in entries:
            state = result.get("status", "uncertain")
            if state not in ("pass", "fail", "uncertain"):
                state = "uncertain"
            # A changed brief is a new assertion. Keep the old failed assertion
            # visibly stale rather than replacing its history with a new one.
            prior = next(
                (
                    c
                    for c in checks
                    if c["frame"] == name
                    and c["id"] == check_id
                    and c.get("expected") == expected
                    and c.get("state") != "stale"
                ),
                None,
            )
            if state == "fail":
                entry = {
                    "frame": name,
                    "id": check_id,
                    "expected": expected,
                    "state": "failing",
                    "reason": result.get("reason", ""),
                    "observed": cold.get("claim")
                    if check_id == "open"
                    else cold.get("answers", {}).get(check_id),
                    "last_run": now,
                }
                if prior is None:
                    checks.append(entry)
                else:
                    prior.update(entry)
            elif prior is not None and prior["state"] != "stale":
                prior.update(
                    state="recovered" if state == "pass" else "uncertain",
                    reason=result.get("reason", ""),
                    last_run=now,
                )
    report["persisted"] = checks
    save_checks(checks_path, checks)
    return report
