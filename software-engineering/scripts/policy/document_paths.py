"""Shared two-domain containment for multi-project document operations."""

from __future__ import annotations

import glob
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .manifest import DocumentProjectScope

_PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


class DocumentContainmentError(ValueError):
    """A document path escaped, aliased, or ambiguously re-entered its domain."""


def _is_within(path: Path, boundary: Path) -> bool:
    try:
        path.relative_to(boundary)
    except ValueError:
        return False
    return True


def _contains_symlink_component(path: Path, boundary: Path) -> bool:
    try:
        relative = path.relative_to(boundary)
    except ValueError:
        return True
    candidate = boundary
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            return True
    return False


def _samefile(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return False


@dataclass(frozen=True)
class DocumentContainment:
    """Canonical repository, project-workspace, and project-docs boundaries."""

    repository_root: Path
    workspace_root: Path | None
    docs_root: Path | None
    project_id: str | None

    @classmethod
    def for_global(cls, repository_root: str | Path) -> DocumentContainment:
        repository_lexical = Path(repository_root).absolute()
        if not repository_lexical.is_dir():
            raise DocumentContainmentError("repository_root must be an existing directory")
        repository = repository_lexical.resolve()
        if not _samefile(repository_lexical, repository):
            raise DocumentContainmentError(
                "repository_root does not identify its resolved directory"
            )
        return cls(repository, None, None, None)

    @classmethod
    def for_project_docs(
        cls,
        repository_root: str | Path,
        docs_root: str | Path,
    ) -> DocumentContainment:
        """Build the project-document boundary used by flat capability consumers."""
        repository_lexical = Path(repository_root).absolute()
        docs_lexical = Path(docs_root).absolute()
        if not repository_lexical.is_dir():
            raise DocumentContainmentError("repository_root must be an existing directory")
        if not docs_lexical.is_dir():
            raise DocumentContainmentError("docs_root must be an existing directory")
        if _contains_symlink_component(docs_lexical, repository_lexical):
            raise DocumentContainmentError("docs_root must not contain a symlink component")

        repository = repository_lexical.resolve()
        docs = docs_lexical.resolve()
        if docs == repository or not _is_within(docs, repository):
            raise DocumentContainmentError("docs_root must resolve strictly inside repository_root")
        if not _samefile(repository_lexical, repository):
            raise DocumentContainmentError(
                "repository_root does not identify its resolved directory"
            )
        if not _samefile(docs_lexical, docs):
            raise DocumentContainmentError("docs_root does not identify its resolved directory")
        return cls(repository, None, docs, None)

    @classmethod
    def for_scope(
        cls, repository_root: str | Path, scope: DocumentProjectScope
    ) -> DocumentContainment:
        return cls.for_project_roots(
            repository_root,
            scope.root,
            scope.docs_root,
            project_id=scope.id,
        )

    @classmethod
    def for_project_boundaries(
        cls,
        repository_root: str | Path,
        workspace_root: str | Path,
        docs_root: str | Path,
    ) -> DocumentContainment:
        """Build project boundaries for capabilities that do not own identity."""
        return cls._for_project_roots(
            repository_root,
            workspace_root,
            docs_root,
            project_id=None,
        )

    @classmethod
    def for_project_roots(
        cls,
        repository_root: str | Path,
        workspace_root: str | Path,
        docs_root: str | Path,
        *,
        project_id: str,
    ) -> DocumentContainment:
        return cls._for_project_roots(
            repository_root,
            workspace_root,
            docs_root,
            project_id=project_id,
        )

    @classmethod
    def _for_project_roots(
        cls,
        repository_root: str | Path,
        workspace_root: str | Path,
        docs_root: str | Path,
        *,
        project_id: str | None,
    ) -> DocumentContainment:
        if project_id is not None and not _PROJECT_ID_PATTERN.fullmatch(project_id):
            raise DocumentContainmentError(
                f"project id {project_id!r} is not a lowercase ASCII slug"
            )

        repository_lexical = Path(repository_root).absolute()
        workspace_lexical = Path(workspace_root).absolute()
        docs_lexical = Path(docs_root).absolute()
        if not repository_lexical.is_dir():
            raise DocumentContainmentError("repository_root must be an existing directory")
        if not workspace_lexical.is_dir():
            raise DocumentContainmentError("workspace_root must be an existing directory")
        if not docs_lexical.is_dir():
            raise DocumentContainmentError("docs_root must be an existing directory")
        if _contains_symlink_component(workspace_lexical, repository_lexical):
            raise DocumentContainmentError("workspace_root must not contain a symlink component")
        if _contains_symlink_component(docs_lexical, workspace_lexical):
            raise DocumentContainmentError("docs_root must not contain a symlink component")

        repository = repository_lexical.resolve()
        workspace = workspace_lexical.resolve()
        docs = docs_lexical.resolve()
        if workspace == repository or not _is_within(workspace, repository):
            raise DocumentContainmentError(
                "workspace_root must resolve strictly inside repository_root"
            )
        if docs == workspace or not _is_within(docs, workspace):
            raise DocumentContainmentError("docs_root must resolve strictly inside workspace_root")
        if not _samefile(repository_lexical, repository):
            raise DocumentContainmentError(
                "repository_root does not identify its resolved directory"
            )
        if not _samefile(workspace_lexical, workspace):
            raise DocumentContainmentError(
                "workspace_root does not identify its resolved directory"
            )
        if not _samefile(docs_lexical, docs):
            raise DocumentContainmentError("docs_root does not identify its resolved directory")
        return cls(repository, workspace, docs, project_id)

    def require_project_path(
        self,
        value: str | Path,
        *,
        purpose: str,
        must_exist: bool = True,
    ) -> Path:
        docs_root = self._require_project_docs("project path")
        return self._require_path(
            value,
            boundary=docs_root,
            boundary_name="project docs_root",
            purpose=purpose,
            must_exist=must_exist,
        )

    def require_workspace_path(
        self,
        value: str | Path,
        *,
        purpose: str,
        must_exist: bool = True,
    ) -> Path:
        workspace_root = self._require_project_boundary("workspace path")[0]
        return self._require_path(
            value,
            boundary=workspace_root,
            boundary_name="project workspace_root",
            purpose=purpose,
            must_exist=must_exist,
        )

    def require_global_path(
        self,
        value: str | Path,
        *,
        purpose: str,
        must_exist: bool = True,
    ) -> Path:
        return self._require_path(
            value,
            boundary=self.repository_root,
            boundary_name="repository root",
            purpose=purpose,
            must_exist=must_exist,
        )

    def require_project_cache_path(
        self,
        value: str | Path,
        *,
        purpose: str,
        must_exist: bool = True,
    ) -> Path:
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise DocumentContainmentError(
                f"{purpose} must be relative to the project cache namespace"
            )
        _workspace_root, _docs_root, project_id = self._require_project_identity("cache path")
        namespace = self.repository_root / ".engineering" / "projects" / project_id
        return self._require_path(
            namespace / relative,
            boundary=namespace,
            boundary_name="project cache namespace",
            purpose=purpose,
            must_exist=must_exist,
            reject_symlinks=True,
        )

    def expand_project_glob(self, pattern: str, *, purpose: str) -> tuple[Path, ...]:
        docs_root = self._require_project_docs("project glob")
        return self._expand_glob(
            pattern,
            boundary=docs_root,
            boundary_name="project docs_root",
            purpose=purpose,
        )

    def expand_global_glob(self, pattern: str, *, purpose: str) -> tuple[Path, ...]:
        return self._expand_glob(
            pattern,
            boundary=self.repository_root,
            boundary_name="repository root",
            purpose=purpose,
        )

    def require_unique_resolved(
        self, candidates: Iterable[Path], *, purpose: str
    ) -> tuple[Path, ...]:
        found: dict[Path, Path] = {}
        ordered: list[Path] = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if previous := found.get(resolved):
                raise DocumentContainmentError(
                    f"{purpose}: same resolved candidate {resolved} was selected twice "
                    f"via {previous} and {candidate}"
                )
            found[resolved] = candidate
            ordered.append(resolved)
        return tuple(ordered)

    def relative_to_repository(self, path: str | Path, *, purpose: str) -> str:
        resolved = self.require_global_path(path, purpose=purpose)
        return resolved.relative_to(self.repository_root).as_posix()

    def _require_project_boundary(self, purpose: str) -> tuple[Path, Path]:
        docs_root = self._require_project_docs(purpose)
        if self.workspace_root is None:
            raise DocumentContainmentError(f"{purpose} requires a selected project boundary")
        return self.workspace_root, docs_root

    def _require_project_docs(self, purpose: str) -> Path:
        if self.docs_root is None:
            raise DocumentContainmentError(f"{purpose} requires a selected project boundary")
        return self.docs_root

    def _require_project_identity(self, purpose: str) -> tuple[Path, Path, str]:
        workspace_root, docs_root = self._require_project_boundary(purpose)
        if self.project_id is None:
            raise DocumentContainmentError(f"{purpose} requires a selected project identity")
        return workspace_root, docs_root, self.project_id

    def _expand_glob(
        self,
        pattern: str,
        *,
        boundary: Path,
        boundary_name: str,
        purpose: str,
    ) -> tuple[Path, ...]:
        pattern_path = Path(pattern)
        if pattern_path.is_absolute() or ".." in pattern_path.parts:
            raise DocumentContainmentError(
                f"{purpose} glob must be repository-relative without '..': {pattern!r}"
            )
        lexical_pattern = self.repository_root / pattern_path
        if not _is_within(lexical_pattern, boundary):
            raise DocumentContainmentError(
                f"{purpose} glob is outside {boundary_name}: {pattern!r}"
            )
        candidates = []
        for raw in sorted(glob.glob(str(lexical_pattern), recursive=True)):
            candidate = Path(raw)
            if not candidate.is_file():
                continue
            candidates.append(
                self._require_path(
                    candidate,
                    boundary=boundary,
                    boundary_name=boundary_name,
                    purpose=purpose,
                    must_exist=True,
                )
            )
        return self.require_unique_resolved(candidates, purpose=purpose)

    def _require_path(
        self,
        value: str | Path,
        *,
        boundary: Path,
        boundary_name: str,
        purpose: str,
        must_exist: bool,
        reject_symlinks: bool = False,
    ) -> Path:
        raw = Path(value)
        if ".." in raw.parts:
            raise DocumentContainmentError(
                f"{purpose} contains a forbidden '..' component: {value!s}"
            )
        lexical = raw.absolute() if raw.is_absolute() else self.repository_root / raw
        if not _is_within(lexical, boundary):
            raise DocumentContainmentError(f"{purpose} is outside {boundary_name}: {value!s}")
        if reject_symlinks and _contains_symlink_component(lexical, self.repository_root):
            raise DocumentContainmentError(f"{purpose} contains a symlink component: {value!s}")
        if must_exist and not lexical.exists():
            raise DocumentContainmentError(f"{purpose} does not exist: {value!s}")
        resolved = lexical.resolve(strict=must_exist)
        if not _is_within(resolved, boundary):
            raise DocumentContainmentError(
                f"{purpose} resolves outside {boundary_name}: {value!s} -> {resolved}"
            )
        if lexical.exists() and not _samefile(lexical, resolved):
            raise DocumentContainmentError(
                f"{purpose} does not identify its resolved candidate: {value!s}"
            )
        return resolved
