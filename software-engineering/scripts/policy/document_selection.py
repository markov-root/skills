"""Version-aware document project selection without CLI/parser dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .manifest import (
    DocumentProjectRegistry,
    DocumentProjectScope,
    Manifest,
    ManifestError,
    ManifestV2,
    load_manifest,
)
from .project_root import load_explicit_manifest, resolve_explicit_project_root

IDENTITY_DOCUMENT_VERBS = frozenset(
    {
        "new",
        "backfill",
        "query",
        "list",
        "show",
        "index",
        "graph",
        "trace",
        "roles",
        "explain",
    }
)
AGGREGATE_DOCUMENT_VERBS = frozenset({"validate", "docs", "doctor", "finish"})
MANIFEST_OPTIONAL_DOCUMENT_VERBS = frozenset({"query", "roles", "validate"})


class DocumentSelectionError(ManifestError):
    """A document verb could not resolve one safe v1/v2 execution scope."""


class DocumentVerbClass(StrEnum):
    IDENTITY = "identity"
    AGGREGATE = "aggregate"


class DocumentExecutionDomain(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"


@dataclass(frozen=True)
class RegistryProjectSelection:
    projects: tuple[DocumentProjectScope, ...]
    selected_project: DocumentProjectScope | None
    strategy: str


@dataclass(frozen=True)
class DocumentExecutionScope:
    domain: DocumentExecutionDomain
    project: DocumentProjectScope | None = None


@dataclass(frozen=True)
class DocumentSelection:
    requested_root: Path
    resolved_requested_root: Path
    repository_root: Path
    manifest: Manifest | None
    verb_class: DocumentVerbClass
    projects: tuple[DocumentProjectScope, ...] = ()
    selected_project: DocumentProjectScope | None = None
    strategy: str = "manifestless-exact"

    @property
    def execution_scopes(self) -> tuple[DocumentExecutionScope, ...]:
        if not isinstance(self.manifest, ManifestV2):
            return ()
        return (
            DocumentExecutionScope(DocumentExecutionDomain.GLOBAL),
            *(
                DocumentExecutionScope(DocumentExecutionDomain.PROJECT, project)
                for project in self.projects
            ),
        )

    @property
    def aggregate_scopes(self) -> tuple[DocumentExecutionScope, ...]:
        if self.verb_class is not DocumentVerbClass.AGGREGATE:
            return ()
        return self.execution_scopes

    def to_dict(self) -> dict[str, object]:
        requested_has_manifest = (self.requested_root / "engineering.yaml").is_file()
        if not isinstance(self.manifest, ManifestV2):
            return {
                "requested": str(self.requested_root),
                "resolved": str(self.resolved_requested_root),
                "promoted": self.requested_root != self.resolved_requested_root,
                "requested_has_manifest": requested_has_manifest,
                "strategy": "explicit",
            }
        return {
            "requested": str(self.requested_root),
            "resolved": str(self.repository_root),
            "promoted": self.requested_root != self.repository_root,
            "requested_has_manifest": requested_has_manifest,
            "strategy": self.strategy,
            "selected_project": (
                None if self.selected_project is None else self.selected_project.id
            ),
        }


def classify_document_verb(action: str) -> DocumentVerbClass:
    if action in IDENTITY_DOCUMENT_VERBS:
        return DocumentVerbClass.IDENTITY
    if action in AGGREGATE_DOCUMENT_VERBS:
        return DocumentVerbClass.AGGREGATE
    raise DocumentSelectionError([f"unknown document verb {action!r}"])


def _contains(scope: DocumentProjectScope, requested: Path) -> bool:
    return requested == scope.root or scope.root in requested.parents


def select_document_projects(
    registry: DocumentProjectRegistry,
    requested: str | Path,
    *,
    project_id: str | None,
    verb_class: DocumentVerbClass,
) -> RegistryProjectSelection:
    requested_path = Path(requested).resolve()
    containing = tuple(
        project for project in registry.projects if _contains(project, requested_path)
    )
    candidates = ", ".join(project.id for project in registry.projects)

    if project_id is not None:
        try:
            selected = registry.select(project_id)
        except ManifestError as exc:
            raise DocumentSelectionError(list(exc.issues)) from exc
        conflicting = tuple(project for project in containing if project.id != selected.id)
        if conflicting:
            containing_ids = ", ".join(repr(project.id) for project in conflicting)
            raise DocumentSelectionError(
                [
                    (
                        "selector conflict: requested path is inside project "
                        f"{containing_ids}, but --project selected {selected.id!r}"
                    )
                ]
            )
        return RegistryProjectSelection((selected,), selected, "explicit-project")

    if verb_class is DocumentVerbClass.AGGREGATE:
        return RegistryProjectSelection(registry.projects, None, "aggregate-projects")

    if len(containing) == 1:
        selected = containing[0]
        return RegistryProjectSelection((selected,), selected, "inferred-project")
    if not containing:
        raise DocumentSelectionError(
            [
                (
                    "cannot infer one project from the requested path; pass --project <id>; "
                    f"candidates: {candidates or 'none'}"
                )
            ]
        )
    matched = ", ".join(project.id for project in containing)
    raise DocumentSelectionError(
        [
            (
                "requested path matched multiple projects, so identity is ambiguous: "
                f"{matched}; pass --project <id>"
            )
        ]
    )


def _selection_from_manifest(
    requested_root: Path,
    resolved_requested_root: Path,
    manifest: Manifest,
    *,
    verb_class: DocumentVerbClass,
    project_id: str | None,
) -> DocumentSelection:
    repository_root = manifest.path.parent
    if not isinstance(manifest, ManifestV2):
        if project_id is not None:
            raise DocumentSelectionError(
                ["--project is unsupported for manifest v1; use its exact project root"]
            )
        return DocumentSelection(
            requested_root=requested_root,
            resolved_requested_root=resolved_requested_root,
            repository_root=repository_root,
            manifest=manifest,
            verb_class=verb_class,
            strategy="legacy-exact",
        )

    registry_selection = select_document_projects(
        manifest.document_projects,
        resolved_requested_root,
        project_id=project_id,
        verb_class=verb_class,
    )
    return DocumentSelection(
        requested_root=requested_root,
        resolved_requested_root=resolved_requested_root,
        repository_root=repository_root,
        manifest=manifest,
        verb_class=verb_class,
        projects=registry_selection.projects,
        selected_project=registry_selection.selected_project,
        strategy=registry_selection.strategy,
    )


def resolve_document_selection(
    start: str | Path,
    *,
    action: str,
    project_id: str | None = None,
) -> DocumentSelection:
    """Resolve an exact legacy root or the nearest ancestor v2 registry."""

    verb_class = classify_document_verb(action)
    try:
        explicit = resolve_explicit_project_root(start)
    except ManifestError as exc:
        raise DocumentSelectionError(list(exc.issues)) from exc
    requested_root = explicit.requested
    resolved_requested_root = explicit.root

    exact_manifest = resolved_requested_root / "engineering.yaml"
    if exact_manifest.is_file():
        try:
            manifest = load_explicit_manifest(explicit, required=True)
        except ManifestError as exc:
            raise DocumentSelectionError(list(exc.issues)) from exc
        assert manifest is not None
        return _selection_from_manifest(
            requested_root,
            resolved_requested_root,
            manifest,
            verb_class=verb_class,
            project_id=project_id,
        )

    for directory in resolved_requested_root.parents:
        candidate = directory / "engineering.yaml"
        if not candidate.is_file():
            continue
        try:
            manifest = load_manifest(candidate)
        except ManifestError as exc:
            raise DocumentSelectionError(list(exc.issues)) from exc
        if isinstance(manifest, ManifestV2):
            return _selection_from_manifest(
                requested_root,
                resolved_requested_root,
                manifest,
                verb_class=verb_class,
                project_id=project_id,
            )
        if project_id is not None:
            raise DocumentSelectionError(
                [
                    (
                        "--project is unsupported for manifest v1; "
                        "the resolver will not climb past that manifest"
                    )
                ]
            )
        break

    if action in MANIFEST_OPTIONAL_DOCUMENT_VERBS and project_id is None:
        return DocumentSelection(
            requested_root=requested_root,
            resolved_requested_root=resolved_requested_root,
            repository_root=resolved_requested_root,
            manifest=None,
            verb_class=verb_class,
        )

    try:
        load_explicit_manifest(explicit, required=True)
    except ManifestError as exc:
        raise DocumentSelectionError(list(exc.issues)) from exc
    raise AssertionError("required exact manifest loader did not fail")
