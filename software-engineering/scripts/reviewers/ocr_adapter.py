#!/usr/bin/env python3
"""Semantic-reviewer adapter that runs alibaba/open-code-review (`ocr`) on a review packet.

Reads one reviewer packet (schema v1) on stdin, scans the packet's changed paths with
`ocr scan`, and prints one reviewer response on stdout. Standard library only, so a project
can declare it directly:

    reviewers:
      ocr:
        adapter: reviewer-json
        command: ["python3", "<skill-root>/scripts/reviewers/ocr_adapter.py",
                  "--provider", "chatgpt", "--model", "<model from ocr llm models>"]
        version_command: ["ocr", "--version"]
        network: required
        timeout_seconds: 1800
        profiles: [risk, intent-diff]

The provider and model are always passed explicitly so `ocr` never falls back to saved
config or ambient credentials, and a provider outside the allowlist is refused before any
code is sent. Any failure exits non-zero, which the lifecycle reports as unavailable, never
as a pass.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SUPPORTED_PROFILES = {"risk", "intent-diff"}
DEFAULT_ALLOWED_PROVIDERS = ("chatgpt",)
EXIT_UNAVAILABLE = 3
EXIT_REFUSED = 4


class AdapterError(Exception):
    def __init__(self, message: str, code: int = EXIT_UNAVAILABLE) -> None:
        super().__init__(message)
        self.code = code


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ocr_adapter")
    parser.add_argument("--provider", required=True, help="ocr LLM provider, passed explicitly")
    parser.add_argument("--model", required=True, help="ocr model, passed explicitly")
    parser.add_argument(
        "--allow-provider",
        action="append",
        default=None,
        help=f"allowlisted provider (repeatable; default: {', '.join(DEFAULT_ALLOWED_PROVIDERS)})",
    )
    parser.add_argument("--ocr", default="ocr", help="ocr executable")
    parser.add_argument("--timeout-minutes", type=int, default=15)
    return parser.parse_args(argv)


def _changed_paths(packet: dict[str, Any], root: Path) -> tuple[list[str], list[str]]:
    scanned: list[str] = []
    omitted: list[str] = []
    for change in packet.get("actual_changes") or ():
        path = str(change.get("path") or "")
        if not path:
            continue
        if change.get("status") in {"deleted", "D"} or not (root / path).is_file():
            omitted.append(f"{path}: not present in the review copy")
            continue
        scanned.append(path)
    return scanned, omitted


def _run_ocr(args: argparse.Namespace, paths: list[str]) -> dict[str, Any]:
    executable = shutil.which(args.ocr)
    if executable is None:
        raise AdapterError(f"ocr executable {args.ocr!r} is not installed")
    command = [
        executable,
        "scan",
        "--path",
        ",".join(paths),
        "--format",
        "json",
        "--audience",
        "agent",
        "--provider",
        args.provider,
        "--model",
        args.model,
        "--timeout",
        str(args.timeout_minutes),
    ]
    completed = subprocess.run(command, capture_output=True, check=False)
    if completed.returncode != 0:
        tail = completed.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise AdapterError(f"ocr exited {completed.returncode}: {' | '.join(tail)}")
    try:
        report = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterError(f"ocr returned non-JSON output: {exc}") from exc
    if not isinstance(report, dict):
        raise AdapterError("ocr JSON output is not an object")
    return report


def _finding(index: int, comment: dict[str, Any]) -> dict[str, Any] | None:
    path = comment.get("path")
    content = comment.get("content")
    if not isinstance(path, str) or not path or not isinstance(content, str) or not content:
        return None
    citation: dict[str, Any] = {"path": path}
    line = comment.get("start_line")
    if isinstance(line, int) and not isinstance(line, bool) and line >= 1:
        citation["line"] = line
    suggestion = comment.get("suggestion_code")
    return {
        "id": f"ocr-{index}",
        "severity": "warning",
        "basis": "observed",
        "observation": content.strip(),
        "recommendation": (
            f"Consider: {suggestion.strip()}"
            if isinstance(suggestion, str) and suggestion.strip()
            else None
        ),
        "evidence": [citation],
    }


def build_response(
    packet: dict[str, Any],
    report: dict[str, Any] | None,
    *,
    provider: str,
    model: str,
    scanned: list[str],
    omitted: list[str],
) -> dict[str, Any]:
    profile = packet["profile"]
    findings: list[dict[str, Any]] = []
    status = None if report is None else report.get("status")
    if report is not None:
        for index, comment in enumerate(report.get("comments") or (), start=1):
            if isinstance(comment, dict) and (finding := _finding(index, comment)):
                findings.append(finding)
            else:
                omitted.append(f"ocr comment {index}: missing path or content")
        for warning in report.get("warnings") or ():
            omitted.append(f"ocr warning: {warning}")
    llm = (report or {}).get("llm") or {}
    complete = status in {"success", "complete"} and not omitted
    if not complete:
        verdict = "incomplete"  # omissions or a non-success status keep it partial, findings or not
    elif findings:
        verdict = "concern"
    else:
        verdict = "pass"
    if verdict == "incomplete" and not omitted:
        omitted.append(f"ocr status {status!r}: {(report or {}).get('message') or 'no review'}")
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": profile,
        "completion": "complete" if verdict != "incomplete" else "partial",
        "verdict": verdict,
        "confidence": "medium" if verdict != "incomplete" else "low",
        "provider": str(llm.get("provider") or provider),
        "model": str(llm.get("model") or model),
        "findings": findings,
        "dismissed_findings": [],
        "examined": scanned,
        "omitted": omitted,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    allowed = tuple(args.allow_provider or DEFAULT_ALLOWED_PROVIDERS)
    try:
        if args.provider not in allowed:
            raise AdapterError(
                f"provider {args.provider!r} is not allowlisted ({', '.join(allowed)}); "
                "refusing to send code",
                EXIT_REFUSED,
            )
        packet = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        profile = packet.get("profile")
        if profile not in SUPPORTED_PROFILES:
            raise AdapterError(f"ocr reviews code defects; profile {profile!r} is unsupported")
        scanned, omitted = _changed_paths(packet, Path.cwd())
        report = _run_ocr(args, scanned) if scanned else None
        response = build_response(
            packet,
            report,
            provider=args.provider,
            model=args.model,
            scanned=scanned,
            omitted=omitted,
        )
    except AdapterError as exc:
        print(f"ocr_adapter: {exc}", file=sys.stderr)
        return exc.code
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
        print(f"ocr_adapter: invalid review packet: {exc}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    print(json.dumps(response, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
