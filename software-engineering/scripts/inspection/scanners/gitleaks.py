"""Gitleaks invocation and privacy-safe report normalization."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from ...execution import run_process
from ..models import (
    ActiveFinding,
    InspectionLayer,
    finding_status,
    fingerprint,
    reportable_path,
    safe_path,
)
from ..tooling import is_git_work_tree, tool_evidence

MAX_FINDINGS = 1_000
MAX_REPORT_BYTES = 5_000_000
TOOL_TIMEOUT_SECONDS = 180


def parse_gitleaks(
    root: Path, report_path: Path, source: str
) -> tuple[tuple[ActiveFinding, ...], bool, str | None]:
    try:
        with report_path.open("rb") as handle:
            raw = handle.read(MAX_REPORT_BYTES + 1)
    except OSError as exc:
        return (), False, f"malformed Gitleaks JSON: {type(exc).__name__}"
    if len(raw) > MAX_REPORT_BYTES:
        return (), True, f"Gitleaks JSON exceeded the {MAX_REPORT_BYTES} byte bound"
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (), False, f"malformed Gitleaks JSON: {type(exc).__name__}"
    if not isinstance(payload, list):
        return (), False, "malformed Gitleaks JSON: expected a list"
    findings: list[ActiveFinding] = []
    for item in payload[:MAX_FINDINGS]:
        if not isinstance(item, dict):
            return (), False, "malformed Gitleaks JSON: finding is not an object"
        rule = str(item.get("RuleID") or "unknown")
        path = reportable_path(safe_path(root, item.get("File")))
        line = item.get("StartLine")
        if not isinstance(line, int) or line < 1:
            line = None
        upstream = str(item.get("Fingerprint") or f"{rule}:{path}:{line}")
        findings.append(
            ActiveFinding(
                "security.secret",
                "security",
                "error",
                f"potential secret detected by Gitleaks rule {rule}; matched value redacted",
                fingerprint(f"gitleaks:{rule}", path, upstream),
                source,
                path,
                line,
            )
        )
    return tuple(findings), len(payload) > MAX_FINDINGS, None


def run_gitleaks(root: Path) -> InspectionLayer:
    started = time.monotonic()
    git_history = is_git_work_tree(root)
    scope = ("git-history", "current-directory") if git_history else ("current-directory",)
    tool = tool_evidence("gitleaks", ("gitleaks", "version"), network="none", root=root)
    if tool.executable is None:
        return InspectionLayer(
            "secrets",
            "security",
            "unavailable",
            True,
            scope,
            (),
            tool,
            round((time.monotonic() - started) * 1000),
            reason="Gitleaks is unavailable",
            limitations=("No secret scanning was executed.",),
        )
    scans = [("dir", "current-directory")]
    if git_history:
        scans.insert(0, ("git", "git-history"))
    scope = tuple(source for _, source in scans)
    findings: list[ActiveFinding] = []
    errors: list[str] = []
    truncated = False
    with tempfile.TemporaryDirectory(prefix="engineering-gitleaks-") as temporary:
        for mode, source in scans:
            report = Path(temporary) / f"{mode}.json"
            command = (
                tool.executable,
                mode,
                "--no-banner",
                "--no-color",
                "--redact=100",
                "--report-format",
                "json",
                "--report-path",
                str(report),
                str(root),
            )
            result = run_process(
                command,
                root=root,
                timeout_seconds=TOOL_TIMEOUT_SECONDS,
                max_output_bytes=4_096,
            )
            if result.status == "timed_out":
                errors.append(f"{mode} scan timed out")
                continue
            if result.status == "unavailable":
                errors.append(f"{mode} scan could not start")
                continue
            if result.exit_code not in {0, 1}:
                errors.append(f"{mode} scan exited {result.exit_code}")
                continue
            parsed, scan_truncated, error = parse_gitleaks(root, report, source)
            if error:
                errors.append(error)
            else:
                findings.extend(parsed)
                truncated = truncated or scan_truncated
    deduplicated = {item.fingerprint: item for item in findings}
    status = "unavailable" if errors or truncated else finding_status(tuple(deduplicated.values()))
    if truncated:
        errors.append(f"Gitleaks findings exceeded the {MAX_FINDINGS} finding bound")
    return InspectionLayer(
        "secrets",
        "security",
        status,
        True,
        scope,
        tuple(deduplicated.values()),
        tool,
        round((time.monotonic() - started) * 1000),
        truncated=truncated,
        reason="; ".join(errors),
        limitations=(
            "Pattern/entropy scanning cannot prove that every credential form is covered.",
            "No credential verification or network validation was performed.",
        ),
    )
