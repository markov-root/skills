"""Exact traversal-root resolution shared by explicit ``--project-root`` consumers."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest, ManifestError, load_manifest


@dataclass(frozen=True)
class ExplicitProjectRoot:
    requested: Path
    root: Path
    requested_has_manifest: bool

    @property
    def changed(self) -> bool:
        return self.requested != self.root

    def to_dict(self) -> dict[str, object]:
        return {
            "requested": str(self.requested),
            "resolved": str(self.root),
            "promoted": self.changed,
            "requested_has_manifest": self.requested_has_manifest,
            "strategy": "explicit",
        }


def git_root_boundary(start: Path) -> Path | None:
    """The enclosing Git repository root, or ``None`` when Git does not answer.

    Mirrors the ``runs.workflow`` Git probe (argument vector, bounded output, no
    shell) so ancestor walks share one traversal boundary instead of a second
    opinion about where a repository ends.
    """

    try:
        result = subprocess.run(
            ("git", "-C", str(start), "rev-parse", "--show-toplevel"),
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or len(result.stdout) > 16_384:
        return None
    value = result.stdout.decode(errors="replace").strip()
    return Path(value).resolve() if value else None


def resolve_explicit_project_root(start: str | Path) -> ExplicitProjectRoot:
    """Resolve one supplied directory without substituting an ancestor repository."""

    requested = Path(start).absolute()
    if requested.is_file():
        raise ManifestError(
            [
                (
                    f"project root is a file, not a directory: {requested}; "
                    f"pass its parent with `--project-root {shlex.quote(str(requested.parent))}`"
                )
            ]
        )
    if not requested.is_dir():
        raise ManifestError([f"project root is not a directory: {requested}"])
    root = requested.resolve()
    return ExplicitProjectRoot(
        requested=requested,
        root=root,
        requested_has_manifest=(requested / "engineering.yaml").is_file(),
    )


def load_explicit_manifest(
    resolution: ExplicitProjectRoot,
    *,
    required: bool,
) -> Manifest | None:
    """Load only the manifest at the exact traversal root, with actionable absence."""

    path = resolution.root / "engineering.yaml"
    if path.is_file():
        try:
            return load_manifest(path)
        except ManifestError as exc:
            command = (
                "engineering suggest-manifest --markdown --project-root "
                f"{shlex.quote(str(resolution.root))}"
            )
            raise ManifestError(
                [*exc.issues, f"next: run `{command}` to obtain review candidates"]
            ) from exc
    if not required:
        return None
    command = f"engineering init --project-root {shlex.quote(str(resolution.root))}"
    raise ManifestError(
        [
            (
                "missing prerequisite manifest file `engineering.yaml` at the explicit project "
                f"root {resolution.root} (`$.engineering.yaml`); run `{command}` to preview the "
                "exact manifest to adopt"
            )
        ]
    )
