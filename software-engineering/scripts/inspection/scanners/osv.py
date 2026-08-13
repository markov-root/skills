"""OSV-Scanner invocation, normalization, and dependency evidence projection."""

from __future__ import annotations

import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from ...execution import run_process
from ..dependencies import DependencyAdvisory, DependencyEvidence, DependencySource
from ..models import (
    ActiveFinding,
    InspectionLayer,
    ToolEvidence,
    dependency_identifier,
    finding_status,
    fingerprint,
    reportable_path,
    safe_path,
)
from ..tooling import tool_evidence

MAX_FINDINGS = 1_000
MAX_REPORT_BYTES = 10_000_000
TOOL_TIMEOUT_SECONDS = 180


def _read_report(report_path: Path) -> tuple[object | None, bool, str | None]:
    try:
        with report_path.open("rb") as handle:
            raw = handle.read(MAX_REPORT_BYTES + 1)
    except OSError as exc:
        return None, False, f"malformed OSV JSON: {type(exc).__name__}"
    if len(raw) > MAX_REPORT_BYTES:
        return None, True, f"OSV JSON exceeded the {MAX_REPORT_BYTES} byte bound"
    try:
        return json.loads(raw), False, None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, False, f"malformed OSV JSON: {type(exc).__name__}"


def parse_osv_details(
    root: Path, report_path: Path
) -> tuple[
    tuple[ActiveFinding, ...],
    int,
    bool,
    str | None,
    tuple[DependencyAdvisory, ...],
    tuple[str, ...],
]:
    payload, report_truncated, report_error = _read_report(report_path)
    if report_error:
        return (), 0, report_truncated, report_error, (), ()
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return (), 0, False, "malformed OSV JSON: expected results list", (), ()
    findings: list[ActiveFinding] = []
    advisories: list[DependencyAdvisory] = []
    source_artifacts: set[str] = set()
    package_count = 0
    for result in results:
        if not isinstance(result, dict):
            continue
        source = result.get("source")
        source_path = (
            reportable_path(safe_path(root, source.get("path")))
            if isinstance(source, dict)
            else None
        )
        if source_path is not None:
            source_artifacts.add(source_path)
        packages = result.get("packages")
        if not isinstance(packages, list):
            continue
        for item in packages:
            if not isinstance(item, dict):
                continue
            package = item.get("package")
            if not isinstance(package, dict):
                continue
            name = dependency_identifier(package.get("name"))
            version = dependency_identifier(package.get("version") or package.get("commit"))
            ecosystem = dependency_identifier(package.get("ecosystem"))
            package_count += 1
            vulnerabilities = item.get("vulnerabilities")
            if not isinstance(vulnerabilities, list):
                continue
            for vulnerability in vulnerabilities:
                if not isinstance(vulnerability, dict):
                    continue
                advisory = dependency_identifier(vulnerability.get("id"))
                if len(advisories) < MAX_FINDINGS:
                    advisories.append(
                        DependencyAdvisory(
                            advisory,
                            ecosystem,
                            name,
                            version,
                            "affected",
                            None,
                            None,
                            None,
                        )
                    )
                if len(findings) <= MAX_FINDINGS:
                    findings.append(
                        ActiveFinding(
                            "security.dependency-vulnerability",
                            "security",
                            "error",
                            f"known dependency vulnerability {advisory}",
                            fingerprint("osv", source_path, f"{name}:{version}:{advisory}"),
                            "dependency-artifact",
                            source_path,
                            advisory=advisory,
                            package=name,
                            version=version,
                        )
                    )
    return (
        tuple(findings[:MAX_FINDINGS]),
        package_count,
        len(findings) > MAX_FINDINGS,
        None,
        tuple(advisories),
        tuple(sorted(source_artifacts)),
    )


def parse_osv(
    root: Path, report_path: Path
) -> tuple[tuple[ActiveFinding, ...], int, bool, str | None]:
    findings, package_count, truncated, error, _advisories, _artifacts = parse_osv_details(
        root, report_path
    )
    return findings, package_count, truncated, error


def _dependency_evidence(
    tool: ToolEvidence,
    *,
    status: str,
    truncated: bool = False,
    package_count: int = 0,
    advisories: tuple[DependencyAdvisory, ...] = (),
    artifacts: tuple[str, ...] = (),
) -> DependencyEvidence:
    return DependencyEvidence(
        population="local-full",
        status=status,
        required=True,
        truncated=truncated,
        package_count=package_count,
        source=DependencySource(
            "live-local-scanner",
            tool.name,
            tool.version,
            datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            None,
        ),
        source_artifacts=artifacts,
        advisories=advisories,
        limitations=(
            "Only dependencies represented by OSV-Scanner-supported artifacts were checked.",
            "Database absence is not proof that a dependency is safe.",
        ),
    )


def _unavailable(
    started: float, tool: ToolEvidence, reason: str, *, limitations: tuple[str, ...] = ()
) -> InspectionLayer:
    return InspectionLayer(
        "dependency-vulnerabilities",
        "security",
        "unavailable",
        True,
        ("supported source manifests and lockfiles",),
        (),
        tool,
        round((time.monotonic() - started) * 1000),
        reason=reason,
        limitations=limitations,
        dependency_evidence=(_dependency_evidence(tool, status="unavailable"),),
    )


def run_osv(root: Path, *, offline: bool) -> InspectionLayer:
    started = time.monotonic()
    tool = tool_evidence(
        "osv-scanner",
        ("osv-scanner", "--version"),
        network="none" if offline else "required",
        root=root,
    )
    if tool.executable is None:
        return _unavailable(
            started,
            tool,
            "OSV-Scanner is unavailable",
            limitations=("No dependency vulnerability matching was executed.",),
        )
    with tempfile.TemporaryDirectory(prefix="engineering-osv-") as temporary:
        report = Path(temporary) / "osv.json"
        command = [
            tool.executable,
            "scan",
            "source",
            "--format",
            "json",
            "--verbosity",
            "error",
            "--recursive",
            "--all-packages",
            "--output-file",
            str(report),
        ]
        if offline:
            command.extend(("--offline", "--offline-vulnerabilities"))
        command.append(str(root))
        result = run_process(
            tuple(command),
            root=root,
            timeout_seconds=TOOL_TIMEOUT_SECONDS,
            max_output_bytes=4_096,
        )
        if result.status == "timed_out":
            return _unavailable(started, tool, "OSV-Scanner timed out")
        if result.status == "unavailable":
            return _unavailable(started, tool, "OSV-Scanner could not start")
        if result.exit_code not in {0, 1}:
            stderr = result.stderr.decode("utf-8", errors="replace").lower()
            network_failure = any(
                marker in stderr
                for marker in (
                    "temporary failure in name resolution",
                    "network is unreachable",
                    "operation not permitted",
                    "no such host",
                    "lookup api.osv.dev",
                )
            )
            reason = (
                "OSV-Scanner offline vulnerability data is unavailable or unusable; "
                "refresh the offline database before retrying"
                if offline
                else (
                    "OSV-Scanner could not reach its vulnerability service; retry with network "
                    "access or use --offline after downloading the offline vulnerability database"
                    if network_failure
                    else f"OSV-Scanner exited {result.exit_code}"
                )
            )
            return _unavailable(started, tool, reason)
        findings, package_count, truncated, error, advisories, artifacts = parse_osv_details(
            root, report
        )
    if error:
        return _unavailable(started, tool, error)
    status = (
        "unavailable"
        if truncated
        else ("not_applicable" if package_count == 0 else finding_status(findings))
    )
    evidence = _dependency_evidence(
        tool,
        status=status,
        truncated=truncated,
        package_count=package_count,
        advisories=advisories,
        artifacts=artifacts,
    )
    return InspectionLayer(
        "dependency-vulnerabilities",
        "security",
        status,
        True,
        ("supported source manifests and lockfiles",),
        findings,
        tool,
        round((time.monotonic() - started) * 1000),
        truncated=truncated,
        reason=(
            f"OSV findings exceeded the {MAX_FINDINGS} finding bound"
            if truncated
            else ("no supported dependency packages were found" if package_count == 0 else "")
        ),
        limitations=(
            "Only dependencies represented by OSV-Scanner-supported artifacts were checked.",
            "Database absence is not proof that a dependency is safe.",
        ),
        dependency_evidence=(evidence,),
    )
