"""Agent-skill publication repository hygiene checks."""

from __future__ import annotations

from pathlib import Path

from ..execution import run_process
from ..policy.path_matching import matches_any
from .models import ActiveFinding, InspectionLayer, fingerprint

MAX_GITIGNORE_BYTES = 1_000_000
MAX_TRACKED_BYTES = 5_000_000
PRIVATE_PATH_PREFIXES = (
    ".private",
    "tests",
    "scratch",
    "tasks",
    "adr",
    "audits",
    "research",
    "lessons",
    "feedback",
    "handoffs",
    "docs/tasks",
    "docs/adr",
    "docs/audits",
    "docs/research",
    "docs/lessons",
    "docs/feedback",
    "docs/handoffs",
)


def _skill_repository(root: Path) -> bool:
    return any(root.glob("*/SKILL.md")) or any(root.glob("skills/*/SKILL.md"))


def _finding(finding_id: str, message: str, path: str) -> ActiveFinding:
    return ActiveFinding(
        finding_id,
        "publication",
        "error",
        message,
        fingerprint(finding_id, path, path),
        ".gitignore",
        path,
    )


def run_gitignore_hygiene(root: Path) -> InspectionLayer:
    """Require portable ignore coverage and an unpolluted index for skill publication roots."""
    root = root.resolve()
    scope = tuple(f"{prefix}/" for prefix in PRIVATE_PATH_PREFIXES)
    if not _skill_repository(root):
        return InspectionLayer(
            "publication-gitignore-hygiene",
            "publication",
            "not_applicable",
            False,
            scope,
            (),
            None,
            0,
            reason="no nested Agent Skill artifact was detected",
            limitations=("This layer applies only to Agent Skill publication repositories.",),
        )

    ignore = root / ".gitignore"
    try:
        raw = ignore.read_bytes()
    except OSError:
        raw = b""
    if len(raw) > MAX_GITIGNORE_BYTES:
        return InspectionLayer(
            "publication-gitignore-hygiene",
            "publication",
            "unavailable",
            True,
            scope,
            (),
            None,
            0,
            truncated=True,
            reason=f".gitignore exceeds {MAX_GITIGNORE_BYTES} bytes",
        )
    try:
        patterns = tuple(raw.decode("utf-8").splitlines())
    except UnicodeDecodeError:
        return InspectionLayer(
            "publication-gitignore-hygiene",
            "publication",
            "unavailable",
            True,
            scope,
            (),
            None,
            0,
            reason=".gitignore is not valid UTF-8",
        )

    findings = [
        _finding(
            "publication.private-path-not-ignored",
            f"{prefix}/ is not excluded by the repository .gitignore",
            f"{prefix}/",
        )
        for prefix in PRIVATE_PATH_PREFIXES
        if not matches_any(f"{prefix}/.publication-probe", patterns)
    ]

    tracked = run_process(
        ("git", "-C", str(root), "ls-files", "-z"),
        root=root,
        timeout_seconds=30,
        max_output_bytes=MAX_TRACKED_BYTES,
    )
    if tracked.status == "unavailable" or tracked.exit_code != 0 or tracked.stdout_truncated:
        return InspectionLayer(
            "publication-gitignore-hygiene",
            "publication",
            "unavailable",
            True,
            scope,
            tuple(findings),
            None,
            tracked.duration_ms,
            truncated=tracked.stdout_truncated,
            reason="Git index inspection was unavailable or incomplete",
        )
    tracked_paths = {
        item.decode("utf-8", "surrogateescape") for item in tracked.stdout.split(b"\0") if item
    }
    for prefix in PRIVATE_PATH_PREFIXES:
        if any(path == prefix or path.startswith(f"{prefix}/") for path in tracked_paths):
            findings.append(
                _finding(
                    "publication.private-path-tracked",
                    f"the Git index contains private publication path {prefix}/",
                    f"{prefix}/",
                )
            )

    return InspectionLayer(
        "publication-gitignore-hygiene",
        "publication",
        "failed" if findings else "passed",
        True,
        scope,
        tuple(findings),
        None,
        tracked.duration_ms,
        limitations=(
            "Only the repository .gitignore and current Git index are authoritative here; global excludes are not portable publication evidence.",
            "A pass does not inspect artifact contents or grant publication permission.",
        ),
    )
