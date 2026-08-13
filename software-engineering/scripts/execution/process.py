"""Bounded, project-contained subprocess execution primitives."""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExecutableIdentity:
    executable: str
    resolved_executable: str | None
    executable_sha256: str | None
    version_command: tuple[str, ...] | None
    version_status: str
    version_output: str


@dataclass(frozen=True)
class ProcessResult:
    status: str
    exit_code: int | None
    duration_ms: int
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool = False
    stderr_truncated: bool = False


def inspect_executable(
    executable: str,
    *,
    root: Path,
    cwd: str = ".",
    version_command: tuple[str, ...] | None = None,
    timeout_seconds: float = 10,
    max_output_bytes: int = 4096,
    redact: tuple[str, ...] = (),
) -> ExecutableIdentity:
    """Resolve and fingerprint an executable without inferring availability."""
    resolved = resolve_executable(executable, root=root, cwd=cwd)
    if version_command is None:
        version_status, version_output = "not_declared", ""
    else:
        result = run_process(
            version_command,
            root=root,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            redact=redact,
        )
        version_status = result.status
        version_output = (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()
    return ExecutableIdentity(
        executable=executable,
        resolved_executable=str(resolved) if resolved else None,
        executable_sha256=hash_file(resolved) if resolved else None,
        version_command=version_command,
        version_status=version_status,
        version_output=version_output,
    )


def run_process(
    command: tuple[str, ...],
    *,
    root: Path,
    cwd: str = ".",
    timeout_seconds: float,
    max_output_bytes: int,
    redact: tuple[str, ...] = (),
    stdin: bytes | None = None,
) -> ProcessResult:
    """Run one fixed argument vector inside a contained project working directory."""
    if not command:
        return ProcessResult("unavailable", None, 0, b"", b"empty command")
    root = root.resolve()
    working_directory = (root / cwd).resolve()
    try:
        working_directory.relative_to(root)
    except ValueError:
        return ProcessResult("unavailable", None, 0, b"", b"cwd escapes project root")
    if not working_directory.is_dir():
        return ProcessResult("unavailable", None, 0, b"", b"cwd is missing")

    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                list(command),
                cwd=working_directory,
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            return ProcessResult(
                "unavailable",
                None,
                round((time.monotonic() - started) * 1000),
                b"",
                redact_bytes(str(exc).encode(), redact),
            )
        try:
            process.communicate(input=stdin, timeout=timeout_seconds)
            status = "passed" if process.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            status = "timed_out"
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout_raw = stdout_file.read(max_output_bytes + 1)
        stderr_raw = stderr_file.read(max_output_bytes + 1)
        stdout_truncated = len(stdout_raw) > max_output_bytes
        stderr_truncated = len(stderr_raw) > max_output_bytes
        stdout = redact_bytes(stdout_raw, redact)[:max_output_bytes]
        stderr = redact_bytes(stderr_raw, redact)[:max_output_bytes]
    return ProcessResult(
        status,
        process.returncode,
        round((time.monotonic() - started) * 1000),
        stdout,
        stderr,
        stdout_truncated,
        stderr_truncated,
    )


def resolve_executable(executable: str, *, root: Path, cwd: str = ".") -> Path | None:
    if "/" in executable:
        candidate = (root / cwd / executable).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return None
        return candidate if candidate.is_file() and os.access(candidate, os.X_OK) else None
    located = shutil.which(executable)
    return Path(located).resolve() if located else None


def hash_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def redact_bytes(value: bytes, literals: tuple[str, ...]) -> bytes:
    for literal in literals:
        if literal:
            value = value.replace(literal.encode(), b"[REDACTED]")
    return value
