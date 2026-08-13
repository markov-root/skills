"""Deterministic subprocess execution for declared checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ..execution import ExecutableIdentity, inspect_executable, run_process
from ..policy.manifest import Check, Manifest


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    command: tuple[str, ...]
    cwd: str
    exit_code: int | None
    signal: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def select_checks(manifest: Manifest, selector: str) -> tuple[Check, ...]:
    if selector in manifest.checks:
        return (manifest.checks[selector],)
    if selector == "full":
        return tuple(manifest.checks.values())
    profile = manifest.profiles.get(selector)
    if profile is None:
        raise KeyError(f"unknown check or profile: {selector}")
    return tuple(manifest.checks[name] for name in profile.checks)


def run_check(check: Check, project_root: str | Path) -> CheckResult:
    root = Path(project_root).resolve()
    cwd = (root / check.cwd).resolve()
    try:
        cwd.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"check {check.name!r} working directory escapes project root") from exc
    if not cwd.is_dir():
        return _result(check, root, "unavailable", None, None, 0, b"", b"working directory missing")
    execution = run_process(
        check.command,
        root=root,
        cwd=check.cwd,
        timeout_seconds=check.timeout_seconds,
        max_output_bytes=check.max_output_bytes,
        redact=check.redact,
    )
    return_code = execution.exit_code
    term_signal = -return_code if return_code is not None and return_code < 0 else None
    return CheckResult(
        name=check.name,
        status=execution.status,
        command=check.command,
        cwd=str(cwd.relative_to(root)) or ".",
        exit_code=return_code,
        signal=term_signal,
        duration_seconds=round(execution.duration_ms / 1000, 6),
        stdout=execution.stdout.decode("utf-8", errors="replace"),
        stderr=execution.stderr.decode("utf-8", errors="replace"),
        stdout_truncated=execution.stdout_truncated,
        stderr_truncated=execution.stderr_truncated,
    )


def inspect_check_executable(check: Check, project_root: str | Path) -> ExecutableIdentity:
    """Capture the bounded executable identity used by one adopted check."""

    return inspect_executable(
        check.command[0],
        root=Path(project_root).resolve(),
        cwd=check.cwd,
        version_command=check.version_command,
        timeout_seconds=min(check.timeout_seconds, 10),
        max_output_bytes=4096,
        redact=check.redact,
    )


def _result(
    check: Check,
    root: Path,
    status: str,
    exit_code: int | None,
    term_signal: int | None,
    duration: float,
    stdout: bytes,
    stderr: bytes,
) -> CheckResult:
    stdout_text = stdout.decode("utf-8", errors="replace")
    stderr_text = stderr.decode("utf-8", errors="replace")
    cwd = str((root / check.cwd).resolve().relative_to(root)) or "."
    return CheckResult(
        check.name,
        status,
        check.command,
        cwd,
        exit_code,
        term_signal,
        round(duration, 6),
        stdout_text,
        stderr_text,
        len(stdout) > check.max_output_bytes,
        len(stderr) > check.max_output_bytes,
    )


def run_checks(
    manifest: Manifest, selector: str, project_root: str | Path
) -> tuple[CheckResult, ...]:
    return tuple(run_check(check, project_root) for check in select_checks(manifest, selector))
