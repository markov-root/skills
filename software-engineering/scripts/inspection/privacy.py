"""Current-tree and Git-history privacy inspection policy."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath

from ..execution import run_process
from .models import (
    EMAIL_RE,
    HIGH_RISK_NAMES,
    HIGH_RISK_SUFFIXES,
    HOME_PATH_RE,
    INTERNAL_HOST_RE,
    MEDIA_SUFFIXES,
    PRIVATE_IPV4_RE,
    ActiveFinding,
    InspectionLayer,
    finding_status,
    fingerprint,
    privacy_finding,
    reportable_path,
    safe_path,
)
from .scanners.media import run_media_metadata
from .tooling import is_git_work_tree, tool_evidence

MAX_FILES = 20_000
MAX_FILE_BYTES = 5_000_000
MAX_HISTORY_BYTES = 100_000_000
MAX_FINDINGS = 1_000
MAX_IDENTITY_BYTES = 5_000_000
TOOL_TIMEOUT_SECONDS = 180


def _stdout(
    command: tuple[str, ...], *, root: Path, byte_limit: int, timeout: int
) -> tuple[bytes, bool, int | None, str]:
    result = run_process(
        command,
        root=root,
        timeout_seconds=timeout,
        max_output_bytes=byte_limit,
    )
    if result.status == "timed_out":
        return result.stdout, result.stdout_truncated, result.exit_code, "timed out"
    if result.status == "unavailable":
        return result.stdout, result.stdout_truncated, result.exit_code, "could not start"
    return result.stdout, result.stdout_truncated, result.exit_code, ""


def _list_candidate_files(root: Path, git_available: bool) -> tuple[list[str], bool]:
    if git_available:
        result = run_process(
            (
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ),
            root=root,
            timeout_seconds=30,
            max_output_bytes=MAX_IDENTITY_BYTES,
        )
        if result.exit_code == 0:
            values = [
                item.decode("utf-8", "surrogateescape")
                for item in result.stdout.split(b"\0")
                if item
            ]
            truncated = result.stdout_truncated or len(values) > MAX_FILES
            return sorted(set(values))[:MAX_FILES], truncated
    values = []
    for path in root.rglob("*"):
        if ".git" in path.parts or ".engineering" in path.parts:
            continue
        if path.is_file() or path.is_symlink():
            try:
                values.append(path.relative_to(root).as_posix())
            except ValueError:
                continue
        if len(values) > MAX_FILES:
            return sorted(values[:MAX_FILES]), True
    return sorted(values), False


def _email_allowed(value: str, target: str) -> bool:
    lowered = value.casefold()
    if lowered.endswith(("@example.com", "@example.org", "@example.net", "@example.invalid")):
        return True
    if target == "github":
        return lowered.endswith("@users.noreply.github.com")
    if target == "forgejo":
        return lowered.endswith("@noreply.localhost")
    return lowered.endswith(("@users.noreply.github.com", "@noreply.localhost"))


def _privacy_matches(text: str, *, target: str) -> Iterable[tuple[str, str, str]]:
    for match in EMAIL_RE.finditer(text):
        value = match.group(1)
        if not _email_allowed(value, target):
            yield "privacy.email", "email-address candidate", value
    for match in PRIVATE_IPV4_RE.finditer(text):
        yield "privacy.private-network", "private-network address candidate", match.group(0)
    for match in INTERNAL_HOST_RE.finditer(text):
        yield "privacy.internal-host", "internal-hostname candidate", match.group(0)
    for match in HOME_PATH_RE.finditer(text):
        yield "privacy.home-path", "user-home path candidate", match.group(0)


def current_privacy_findings(
    root: Path, paths: Sequence[str], *, target: str
) -> tuple[list[ActiveFinding], list[str]]:
    findings: list[ActiveFinding] = []
    media: list[str] = []
    for relative in paths:
        if len(findings) >= MAX_FINDINGS:
            break
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts:
            continue
        path = root / pure
        reported_path = reportable_path(relative)
        for finding_id, message, value in _privacy_matches(relative, target=target):
            findings.append(
                privacy_finding(
                    finding_id,
                    f"{message} in a repository path",
                    value,
                    source="current-directory",
                    path=None,
                )
            )
        if path.is_symlink():
            try:
                path.resolve().relative_to(root)
            except (OSError, ValueError):
                findings.append(
                    privacy_finding(
                        "privacy.symlink-escape",
                        "symlink target escapes the repository",
                        relative,
                        source="current-directory",
                        path=reported_path,
                    )
                )
            continue
        name = path.name.casefold()
        suffix = path.suffix.casefold()
        if (
            name in HIGH_RISK_NAMES
            or (
                name.startswith(".env.") and not name.endswith((".example", ".sample", ".template"))
            )
            or suffix in HIGH_RISK_SUFFIXES
        ):
            findings.append(
                privacy_finding(
                    "privacy.sensitive-path",
                    "sensitive-file path candidate",
                    relative,
                    source="current-directory",
                    path=reported_path,
                )
            )
        if suffix in MEDIA_SUFFIXES:
            media.append(relative)
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES:
            findings.append(
                privacy_finding(
                    "privacy.file-unscanned",
                    "file exceeds the bounded content-inspection size",
                    relative,
                    source="current-directory",
                    path=reported_path,
                )
            )
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if b"\0" in content:
            continue
        text = content.decode("utf-8", "replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            for finding_id, message, value in _privacy_matches(line, target=target):
                findings.append(
                    privacy_finding(
                        finding_id,
                        message,
                        value,
                        source="current-directory",
                        path=reported_path,
                        line=line_number,
                    )
                )
                if len(findings) >= MAX_FINDINGS:
                    break
            if len(findings) >= MAX_FINDINGS:
                break
    return findings, media


def git_identity_findings(root: Path, *, target: str) -> tuple[list[ActiveFinding], bool, str]:
    findings: list[ActiveFinding] = []
    configured = run_process(
        ("git", "-C", str(root), "config", "--local", "--get", "user.email"),
        root=root,
        timeout_seconds=10,
        max_output_bytes=500,
    )
    if configured.status == "unavailable":
        return findings, False, "Git identity inspection could not start"
    if configured.exit_code == 0:
        email = configured.stdout.decode("utf-8", "replace").strip()
        if email and not _email_allowed(email, target):
            findings.append(
                privacy_finding(
                    "privacy.git-config-email",
                    f"repository-local Git email is not privacy-safe for target {target}",
                    email,
                    source="git-config",
                )
            )
    data, truncated, returncode, reason = _stdout(
        ("git", "-C", str(root), "log", "--all", "--format=%ae%x00%ce%x00"),
        root=root,
        byte_limit=MAX_IDENTITY_BYTES,
        timeout=30,
    )
    if reason:
        return findings, truncated, f"Git identity inspection {reason}"
    if returncode != 0:
        return findings, truncated, f"Git identity inspection exited {returncode}"
    seen: set[tuple[str, str]] = set()
    fields = data.split(b"\0")
    for index in range(0, len(fields) - 1, 2):
        for identity_kind, raw_email in (
            ("author", fields[index]),
            ("committer", fields[index + 1]),
        ):
            email = raw_email.decode("utf-8", "replace").strip()
            identity = (identity_kind, email)
            if not email or identity in seen or _email_allowed(email, target):
                continue
            seen.add(identity)
            findings.append(
                privacy_finding(
                    "privacy.git-history-email",
                    f"Git history contains a {identity_kind} email not privacy-safe for target {target}",
                    email,
                    source="git-history",
                )
            )
    return findings, truncated, ""


def history_privacy_findings(root: Path, *, target: str) -> tuple[list[ActiveFinding], bool, str]:
    data, truncated, returncode, reason = _stdout(
        (
            "git",
            "-C",
            str(root),
            "log",
            "-p",
            "--all",
            "--no-ext-diff",
            "--no-textconv",
            "--format=@@ENGINEERING_COMMIT@@%H",
        ),
        root=root,
        byte_limit=MAX_HISTORY_BYTES,
        timeout=TOOL_TIMEOUT_SECONDS,
    )
    if reason:
        return [], truncated, f"Git history privacy scan {reason}"
    if returncode != 0:
        return [], truncated, f"Git history privacy scan exited {returncode}"
    findings: list[ActiveFinding] = []
    path: str | None = None
    seen: set[str] = set()
    for raw_line in data.splitlines():
        if raw_line.startswith(b"+++ b/"):
            path = reportable_path(safe_path(root, raw_line[6:].decode("utf-8", "replace")))
            continue
        if not raw_line.startswith((b"+", b"-")) or raw_line.startswith((b"+++", b"---")):
            continue
        line = raw_line[1:].decode("utf-8", "replace")
        for finding_id, message, _value in _privacy_matches(line, target=target):
            identity = fingerprint(f"history:{finding_id}", path, f"git-history:{message}")
            if identity in seen:
                continue
            seen.add(identity)
            findings.append(
                ActiveFinding(
                    finding_id,
                    "privacy",
                    "warning",
                    f"{message} exists in Git history; matched value redacted",
                    identity,
                    "git-history",
                    path,
                )
            )
            if len(findings) >= MAX_FINDINGS:
                return findings, True, ""
    return findings, truncated, ""


def run_privacy(root: Path, *, target: str) -> tuple[InspectionLayer, InspectionLayer]:
    import time

    started = time.monotonic()
    git_available = is_git_work_tree(root)
    paths, file_list_truncated = _list_candidate_files(root, git_available)
    findings, media = current_privacy_findings(root, paths, target=target)
    current_truncated = len(findings) >= MAX_FINDINGS
    history_truncated = False
    history_reason = ""
    if git_available:
        identity_findings, identity_truncated, identity_reason = git_identity_findings(
            root, target=target
        )
        findings.extend(identity_findings)
        history_findings, history_truncated, history_reason = history_privacy_findings(
            root, target=target
        )
        findings.extend(history_findings)
        history_truncated = history_truncated or identity_truncated
        history_reason = history_reason or identity_reason
    deduplicated = {item.fingerprint: item for item in findings}
    truncated = (
        file_list_truncated
        or current_truncated
        or history_truncated
        or len(deduplicated) > MAX_FINDINGS
    )
    status = (
        "unavailable"
        if history_reason or file_list_truncated or current_truncated or history_truncated
        else finding_status(tuple(deduplicated.values())[:MAX_FINDINGS])
    )
    content = InspectionLayer(
        "privacy-exposure",
        "privacy",
        status,
        True,
        (
            "tracked and unignored current files",
            "Git author/config identity" if git_available else "Git identity not applicable",
            "Git patch history" if git_available else "Git history not applicable",
        ),
        tuple(deduplicated.values())[:MAX_FINDINGS],
        tool_evidence("git", ("git", "--version"), network="none", root=root)
        if git_available
        else None,
        round((time.monotonic() - started) * 1000),
        truncated=truncated,
        reason=history_reason,
        limitations=(
            "Matches are privacy candidates, not confirmed personal data.",
            "Binary content other than selected media metadata is not semantically inspected.",
            "No legal or jurisdictional privacy determination was made.",
        ),
    )
    return content, run_media_metadata(root, media)
