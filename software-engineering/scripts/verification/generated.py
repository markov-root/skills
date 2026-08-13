"""Generated artifact declarations and read-only verification."""

from __future__ import annotations

import filecmp
import glob
import shlex
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..execution import run_process
from ..policy.manifest import Manifest


@dataclass(frozen=True)
class GeneratedDeclaration:
    name: str
    sources: tuple[str, ...]
    outputs: tuple[str, ...]
    command: tuple[str, ...]
    cwd: str = "."


@dataclass(frozen=True)
class GeneratedFinding:
    declaration: str
    code: str
    path: str | None
    message: str


def from_manifest(manifest: Manifest) -> tuple[GeneratedDeclaration, ...]:
    """Project adopted generated declarations into the verification model."""

    return tuple(
        GeneratedDeclaration(item.name, item.sources, item.outputs, item.command, item.cwd)
        for item in manifest.generated
    )


def run_generator(copy_cwd: Path, command: Sequence[str]) -> int:
    """Run a declared generator through the shared bounded execution contract."""

    result = run_process(
        tuple(command),
        root=copy_cwd,
        timeout_seconds=300,
        max_output_bytes=1_000_000,
    )
    return result.exit_code if result.exit_code is not None else 127


def validate_declaration(root: Path, item: GeneratedDeclaration) -> tuple[GeneratedFinding, ...]:
    findings: list[GeneratedFinding] = []
    if not item.sources:
        findings.append(
            GeneratedFinding(item.name, "missing-sources", None, "sources are required")
        )
    if not item.outputs:
        findings.append(
            GeneratedFinding(item.name, "missing-outputs", None, "outputs are required")
        )
    if not item.command or any(not isinstance(arg, str) or not arg for arg in item.command):
        findings.append(
            GeneratedFinding(item.name, "invalid-command", None, "argument-vector command required")
        )
    cwd = (root / item.cwd).resolve()
    try:
        cwd.relative_to(root.resolve())
    except ValueError:
        findings.append(
            GeneratedFinding(item.name, "unsafe-cwd", item.cwd, "cwd escapes project root")
        )
    else:
        if not cwd.is_dir():
            findings.append(
                GeneratedFinding(item.name, "missing-cwd", item.cwd, "cwd does not exist")
            )
    for relative in (*item.sources, *item.outputs):
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            findings.append(
                GeneratedFinding(item.name, "unsafe-path", relative, "path escapes project root")
            )
    return tuple(findings)


def _expand(
    root: Path, patterns: Sequence[str]
) -> tuple[dict[str, tuple[str, ...]], list[GeneratedFinding]]:
    expanded: dict[str, tuple[str, ...]] = {}
    findings: list[GeneratedFinding] = []
    resolved_root = root.resolve()
    for pattern in patterns:
        matches: list[str] = []
        for value in glob.glob(str(root / pattern), recursive=True):
            candidate = Path(value)
            if not candidate.is_file():
                continue
            try:
                relative = candidate.resolve().relative_to(resolved_root).as_posix()
            except ValueError:
                findings.append(
                    GeneratedFinding(
                        "",
                        "unsafe-path",
                        pattern,
                        "expanded path escapes project root",
                    )
                )
                continue
            matches.append(relative)
        expanded[pattern] = tuple(sorted(set(matches)))
    return expanded, findings


def _canonical_command(item: GeneratedDeclaration) -> str:
    command = shlex.join(item.command)
    return command if item.cwd == "." else f"cd {shlex.quote(item.cwd)} && {command}"


def inspect_generated(root: Path, item: GeneratedDeclaration) -> tuple[GeneratedFinding, ...]:
    """Validate declaration paths and current source/output presence without execution."""
    invalid = validate_declaration(root, item)
    if invalid:
        return invalid
    source_map, unsafe_sources = _expand(root, item.sources)
    output_map, unsafe_outputs = _expand(root, item.outputs)
    findings = [
        GeneratedFinding(item.name, finding.code, finding.path, finding.message)
        for finding in (*unsafe_sources, *unsafe_outputs)
    ]
    findings.extend(
        GeneratedFinding(item.name, "missing-source", pattern, "source pattern matched no files")
        for pattern, matches in source_map.items()
        if not matches
    )
    findings.extend(
        GeneratedFinding(item.name, "missing-output", pattern, "output pattern matched no files")
        for pattern, matches in output_map.items()
        if not matches
    )
    return tuple(findings)


def verify_generated(
    root: Path,
    item: GeneratedDeclaration,
    runner: Callable[[Path, Sequence[str]], int],
) -> tuple[GeneratedFinding, ...]:
    invalid = validate_declaration(root, item)
    if invalid:
        return invalid
    source_map, unsafe_sources = _expand(root, item.sources)
    output_map, unsafe_outputs = _expand(root, item.outputs)
    unsafe = [
        GeneratedFinding(item.name, finding.code, finding.path, finding.message)
        for finding in (*unsafe_sources, *unsafe_outputs)
    ]
    if unsafe:
        return tuple(unsafe)
    missing_sources = [
        GeneratedFinding(item.name, "missing-source", pattern, "source pattern matched no files")
        for pattern, matches in source_map.items()
        if not matches
    ]
    if missing_sources:
        return tuple(missing_sources)
    with tempfile.TemporaryDirectory(prefix="engineering-generated-") as temporary:
        copy = Path(temporary) / "project"
        shutil.copytree(root, copy, symlinks=True)
        copy_cwd = (copy / item.cwd).resolve()
        try:
            copy_cwd.relative_to(copy.resolve())
        except ValueError:
            return (
                GeneratedFinding(item.name, "unsafe-cwd", item.cwd, "copied cwd escapes project"),
            )
        if runner(copy_cwd, item.command) != 0:
            return (
                GeneratedFinding(
                    item.name,
                    "generation-failed",
                    None,
                    f"generator returned failure; run: {_canonical_command(item)}",
                ),
            )
        copy_output_map, unsafe_copy = _expand(copy, item.outputs)
        if unsafe_copy:
            return tuple(
                GeneratedFinding(item.name, finding.code, finding.path, finding.message)
                for finding in unsafe_copy
            )
        findings: list[GeneratedFinding] = []
        for pattern in item.outputs:
            relatives = sorted(set(output_map[pattern]) | set(copy_output_map[pattern]))
            if not relatives:
                findings.append(
                    GeneratedFinding(
                        item.name,
                        "missing-output",
                        pattern,
                        f"output pattern matched no files; run: {_canonical_command(item)}",
                    )
                )
                continue
            for relative in relatives:
                original, regenerated = root / relative, copy / relative
                if not regenerated.exists():
                    findings.append(
                        GeneratedFinding(
                            item.name,
                            "missing-output",
                            relative,
                            f"generator did not create output; run: {_canonical_command(item)}",
                        )
                    )
                elif not original.exists() or not filecmp.cmp(original, regenerated, shallow=False):
                    findings.append(
                        GeneratedFinding(
                            item.name,
                            "generated-drift",
                            relative,
                            f"run: {_canonical_command(item)}",
                        )
                    )
        return tuple(findings)
