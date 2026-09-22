"""Strict, side-effect-free loading of versioned ``engineering.yaml`` policies."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import jsonschema
import pathspec
import yaml
from pathspec.patterns.gitwildmatch import GitWildMatchPatternError

from ..resources import schema_path as bundled_schema_path
from .documents import HANDOFF_STATES, DocumentContractPolicy

SUPPORTED_MANIFEST_VERSION = 2

_PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_RECORD_ROLE_FOLDERS = {
    "task": "tasks",
    "adr": "adr",
    "audit": "audits",
    "research": "research",
    "lesson": "lessons",
    "handoff": "handoffs",
    "plan": "plans",
}
_RECORD_ID_GLOB = "[0-9][0-9][0-9][0-9]-*.md"


@dataclass(frozen=True)
class ProjectPolicy:
    risk: str
    core_outcome: str
    documents: tuple[str, ...] = ()


@dataclass(frozen=True)
class PathPolicy:
    generated: tuple[str, ...] = ()
    vendored: tuple[str, ...] = ()
    sensitive: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    version_command: tuple[str, ...] | None = None
    applies_to: tuple[str, ...] = ()
    cwd: str = "."
    timeout_seconds: float = 300.0
    max_output_bytes: int = 1_000_000
    redact: tuple[str, ...] = ()


@dataclass(frozen=True)
class Profile:
    name: str
    checks: tuple[str, ...]


@dataclass(frozen=True)
class FitnessException:
    path: str
    reason: str
    expires: str


@dataclass(frozen=True)
class FitnessDeclaration:
    name: str
    check: str
    rationale: str
    references: tuple[str, ...] = ()
    applies_to: tuple[str, ...] = ()
    exceptions: tuple[FitnessException, ...] = ()


@dataclass(frozen=True)
class GeneratedPolicy:
    name: str
    sources: tuple[str, ...]
    outputs: tuple[str, ...]
    command: tuple[str, ...]
    cwd: str = "."


@dataclass(frozen=True)
class DocumentRolePolicy:
    name: str
    include: tuple[str, ...]
    index: str
    id_prefix_digits: int
    states: tuple[str, ...] = ()
    current_state: str | None = None
    contract: DocumentContractPolicy | None = None


@dataclass(frozen=True)
class DoneTaskEvidencePolicy:
    include: tuple[str, ...]
    headings: tuple[str, ...]


@dataclass(frozen=True)
class DocsCurrencyPolicy:
    roles: tuple[DocumentRolePolicy, ...] = ()
    required_current_truth: tuple[str, ...] = ()
    done_task_evidence: DoneTaskEvidencePolicy | None = None


@dataclass(frozen=True)
class DocsPolicy:
    include: tuple[str, ...] = ()
    required_headings: tuple[str, ...] = ()
    forbid_legacy_links: bool = False
    currency: DocsCurrencyPolicy | None = None


@dataclass(frozen=True)
class TaskPlanningFieldPolicy:
    values: tuple[str, ...]
    order: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskPlanningPolicy:
    fields: dict[str, TaskPlanningFieldPolicy]
    default_order: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskInventoryPolicy:
    include: tuple[str, ...] = ("docs/tasks/*.md",)
    handoffs: tuple[str, ...] = ("docs/handoffs/*.md",)
    decisions: tuple[str, ...] = ("docs/adr/*.md", "docs/decisions/*.md")
    planning: TaskPlanningPolicy | None = None


@dataclass(frozen=True)
class ReviewerDeclaration:
    name: str
    adapter: str
    command: tuple[str, ...]
    network: str
    blocking: bool = False
    profiles: tuple[str, ...] = ()
    owner: str | None = None
    expected_provider: str | None = None
    expected_model: str | None = None
    exception_reason: str | None = None
    exception_expires: str | None = None
    version_command: tuple[str, ...] | None = None
    cwd: str = "."
    timeout_seconds: float = 60.0
    max_output_bytes: int = 1_000_000
    redact: tuple[str, ...] = ()
    applies_to: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manifest:
    path: Path
    version: int
    project: ProjectPolicy
    paths: PathPolicy
    checks: dict[str, Check]
    profiles: dict[str, Profile]
    classifiers: dict[str, tuple[str, ...]]
    fitness: tuple[FitnessDeclaration, ...]
    generated: tuple[GeneratedPolicy, ...]
    docs: DocsPolicy
    task_inventory: TaskInventoryPolicy
    reviewers: dict[str, ReviewerDeclaration]
    approval_required: tuple[str, ...]
    raw: dict[str, Any]


@dataclass(frozen=True)
class DocumentProjectScope:
    """One v2 project's resolved roots and normalized record policy."""

    id: str
    root: Path
    docs_root: Path
    currency: DocsCurrencyPolicy
    task_inventory: TaskInventoryPolicy


@dataclass(frozen=True)
class DocumentProjectRegistry:
    """The ordered, immutable v2 project registry."""

    projects: tuple[DocumentProjectScope, ...]

    def select(self, project_id: str) -> DocumentProjectScope:
        for project in self.projects:
            if project.id == project_id:
                return project
        raise ManifestError([f"$.docs.currency.projects: unknown project id {project_id!r}"])


@dataclass(frozen=True)
class SizeGateThresholds:
    """Per-project-tunable warning thresholds for the advisory task-size gate (ADR 0025 §4/§10).

    These bound only advisory oversize smells; they never hard-block. Defaults are conservative
    starting points that a project is expected to tune before relying on them.
    """

    max_acceptance_criteria: int = 7
    max_touched_dirs: int = 4


@dataclass(frozen=True)
class ManifestV2(Manifest):
    """Manifest v2 data kept beside, rather than inside, the legacy model."""

    document_projects: DocumentProjectRegistry
    agent_scheduling: bool = False
    # A frozen (immutable) instance is a safe shared default; no default_factory needed.
    size_gate: SizeGateThresholds = SizeGateThresholds()


class ManifestError(ValueError):
    """An invalid policy, with stable path-oriented diagnostics."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = tuple(issues)
        super().__init__("invalid engineering policy:\n" + "\n".join(f"- {x}" for x in issues))


class _StrictSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_mapping(
    loader: _StrictSafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _display_path(parts: list[Any]) -> str:
    result = "$"
    for part in parts:
        result += f"[{part}]" if isinstance(part, int) else f".{part}"
    return result


def _valid_relative_path(value: object, *, glob: bool = False) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    path_value = value
    if glob:
        path_value = path_value.removeprefix("!").removeprefix("/")
    if not path_value:
        return False
    path = PurePosixPath(path_value)
    if path.is_absolute() or ".." in path.parts:
        return False
    if not glob and any(char in value for char in "*?["):
        return False
    if glob:
        try:
            pathspec.PathSpec.from_lines("gitwildmatch", [value])
        except (GitWildMatchPatternError, ValueError, TypeError):
            return False
        # pathspec accepts malformed-looking character classes; reject them explicitly.
        if value.count("[") != value.count("]"):
            return False
    return True


def _schema_path(version: int = 1) -> Path:
    filename = "engineering-v2.schema.json" if version == 2 else "engineering.schema.json"
    return bundled_schema_path(filename)


def _schema_issues(
    validator: jsonschema.Draft202012Validator, instance: dict[str, Any]
) -> list[str]:
    issues: list[str] = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path)):
        path = list(error.absolute_path)
        if (
            error.validator == "additionalProperties"
            and isinstance(error.instance, dict)
            and isinstance(error.schema.get("properties"), dict)
        ):
            allowed = set(error.schema["properties"])
            issues.extend(
                f"{_display_path([*path, key])}: unknown key"
                for key in sorted(set(error.instance) - allowed)
            )
        else:
            issues.append(f"{_display_path(path)}: {error.message}")
    return issues


def _is_within(path: Path, parent: Path, *, strict: bool = False) -> bool:
    if strict and path == parent:
        return False
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _same_existing_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return False


def _has_symlink_component(path: Path, boundary: Path) -> bool:
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


def _normalized_project_value(repo_root: Path, docs_root: Path, value: str) -> str:
    docs_relative = docs_root.relative_to(repo_root).as_posix()
    return (PurePosixPath(docs_relative) / PurePosixPath(value)).as_posix()


def _planning_issues(planning: dict[str, Any], path: str) -> list[str]:
    issues: list[str] = []
    fields_value = planning.get("fields", {})
    fields = fields_value if isinstance(fields_value, dict) else {}
    for name, spec in fields.items():
        if not isinstance(spec, dict):
            continue
        values = spec.get("values", [])
        order = spec.get("order", [])
        if order and set(order) != set(values):
            issues.append(
                f"{path}.fields.{name}.order: must contain every allowed value exactly once"
            )
    for index, name in enumerate(planning.get("default_order", [])):
        spec = fields.get(name)
        if not isinstance(spec, dict):
            issues.append(f"{path}.default_order[{index}]: unknown planning field {name!r}")
        elif not spec.get("order"):
            issues.append(
                f"{path}.default_order[{index}]: planning field {name!r} has no explicit order"
            )
    return issues


def _v2_project_issues(loaded: dict[str, Any], repo_root: Path) -> list[str]:
    currency = loaded["docs"]["currency"]
    projects = currency["projects"]
    issues: list[str] = []
    ids: set[str] = set()
    resolved_roots: list[tuple[int, Path]] = []
    resolved_docs_roots: list[tuple[int, Path]] = []

    for role_index, role in enumerate(currency.get("roles", ())):
        if role.get("name") in _RECORD_ROLE_FOLDERS:
            issues.append(
                f"$.docs.currency.roles[{role_index}].name: record roles must be project-scoped"
            )

    for role_name, spec in currency.get("role_defaults", {}).items():
        contract = spec.get("contract", {})
        if contract.get("role") != role_name:
            issues.append(
                f"$.docs.currency.role_defaults.{role_name}.contract.role: "
                "must equal the enclosing role name"
            )
        if bool(spec.get("states")) != bool(spec.get("current_state")):
            issues.append(
                f"$.docs.currency.role_defaults.{role_name}: "
                "states and current_state must be declared together"
            )
        elif spec.get("current_state") and spec["current_state"] not in spec["states"]:
            issues.append(
                f"$.docs.currency.role_defaults.{role_name}.current_state: "
                "must be one of the declared states"
            )
        if role_name == "handoff":
            if tuple(spec.get("states", ())) != HANDOFF_STATES:
                issues.append(
                    "$.docs.currency.role_defaults.handoff.states: handoff contract requires "
                    f"{list(HANDOFF_STATES)!r}"
                )
            if spec.get("current_state") != "current":
                issues.append(
                    "$.docs.currency.role_defaults.handoff.current_state: "
                    "handoff contract requires 'current'"
                )

    for index, project in enumerate(projects):
        project_path = f"$.docs.currency.projects[{index}]"
        project_id = project["id"]
        folded_id = project_id.casefold()
        if not _PROJECT_ID_PATTERN.fullmatch(project_id):
            issues.append(f"{project_path}.id: expected a lowercase ASCII slug")
        if folded_id in ids:
            issues.append(f"{project_path}.id: duplicate project id {project_id!r}")
        ids.add(folded_id)

        root_value = project["root"]
        docs_root_value = project.get("docs_root", "dev/docs")
        if not _valid_relative_path(root_value):
            issues.append(f"{project_path}.root: invalid repository-relative path")
            continue
        if not _valid_relative_path(docs_root_value):
            issues.append(f"{project_path}.docs_root: invalid project-relative path")
            continue

        lexical_root = repo_root / root_value
        if _has_symlink_component(lexical_root, repo_root):
            issues.append(f"{project_path}.root: project root must not be a symlink")
            continue
        if not lexical_root.is_dir():
            issues.append(f"{project_path}.root: project root must be an existing directory")
            continue
        resolved_root = lexical_root.resolve()
        if not _is_within(resolved_root, repo_root, strict=True):
            issues.append(f"{project_path}.root: project root must resolve inside repository root")
            continue

        lexical_docs_root = lexical_root / docs_root_value
        if _has_symlink_component(lexical_docs_root, lexical_root):
            issues.append(f"{project_path}.docs_root: docs_root must not be a symlink")
            continue
        if not lexical_docs_root.is_dir():
            issues.append(f"{project_path}.docs_root: docs_root must be an existing directory")
            continue
        resolved_docs_root = lexical_docs_root.resolve()
        if not _is_within(resolved_docs_root, resolved_root, strict=True):
            issues.append(f"{project_path}.docs_root: docs_root must resolve inside project root")
            continue

        resolved_roots.append((index, resolved_root))
        resolved_docs_roots.append((index, resolved_docs_root))

        for pointer_index, pointer in enumerate(project.get("required_current_truth", ())):
            if not _valid_relative_path(pointer):
                issues.append(
                    f"{project_path}.required_current_truth[{pointer_index}]: "
                    "invalid project-relative path"
                )
        evidence = project.get("done_task_evidence", {})
        for include_index, pattern in enumerate(evidence.get("include", ())):
            if not _valid_relative_path(pattern, glob=True):
                issues.append(
                    f"{project_path}.done_task_evidence.include[{include_index}]: "
                    "invalid project-relative glob"
                )
        inventory = project.get("task_inventory", {})
        for field in ("include", "handoffs", "decisions"):
            for pattern_index, pattern in enumerate(inventory.get(field, ())):
                if not _valid_relative_path(pattern, glob=True):
                    issues.append(
                        f"{project_path}.task_inventory.{field}[{pattern_index}]: "
                        "invalid project-relative glob"
                    )
        planning = inventory.get("planning")
        if isinstance(planning, dict):
            issues.extend(_planning_issues(planning, f"{project_path}.task_inventory.planning"))

    for offset, (left_index, left) in enumerate(resolved_roots):
        for right_index, right in resolved_roots[offset + 1 :]:
            if (
                _same_existing_path(left, right)
                or _is_within(left, right)
                or _is_within(right, left)
            ):
                issues.append(
                    f"$.docs.currency.projects[{right_index}].root: project roots must not be "
                    f"equal or nested (overlaps project {left_index})"
                )
    for offset, (left_index, left) in enumerate(resolved_docs_roots):
        for right_index, right in resolved_docs_roots[offset + 1 :]:
            if (
                _same_existing_path(left, right)
                or _is_within(left, right)
                or _is_within(right, left)
            ):
                issues.append(
                    f"$.docs.currency.projects[{right_index}].docs_root: docs roots must not be "
                    f"equal or nested (overlaps project {left_index})"
                )
    return issues


def _planning_policy(value: dict[str, Any] | None) -> TaskPlanningPolicy | None:
    if not value:
        return None
    return TaskPlanningPolicy(
        fields={
            name: TaskPlanningFieldPolicy(
                values=tuple(spec["values"]), order=tuple(spec.get("order", ()))
            )
            for name, spec in value.get("fields", {}).items()
        },
        default_order=tuple(value.get("default_order", ())),
    )


def _v2_project_registry(loaded: dict[str, Any], repo_root: Path) -> DocumentProjectRegistry:
    currency = loaded["docs"]["currency"]
    role_defaults = currency.get("role_defaults", {})
    scopes: list[DocumentProjectScope] = []
    for project in currency["projects"]:
        root = (repo_root / project["root"]).resolve()
        docs_root = (root / project.get("docs_root", "dev/docs")).resolve()
        roles: list[DocumentRolePolicy] = []
        for role_name in project["roles"]:
            folder = _RECORD_ROLE_FOLDERS[role_name]
            role_default = role_defaults.get(role_name, {})
            contract_value = role_default.get(
                "contract",
                {
                    "version": 1,
                    "role": role_name,
                    "carrier": "frontmatter",
                    "metadata_key": "engineering_document",
                },
            )
            states = tuple(role_default.get("states", ()))
            current_state = role_default.get("current_state")
            if role_name == "handoff" and not role_default:
                states = HANDOFF_STATES
                current_state = "current"
            roles.append(
                DocumentRolePolicy(
                    name=role_name,
                    include=(
                        _normalized_project_value(
                            repo_root, docs_root, f"{folder}/{_RECORD_ID_GLOB}"
                        ),
                    ),
                    index=_normalized_project_value(repo_root, docs_root, f"{folder}/README.md"),
                    id_prefix_digits=role_default.get("id_prefix_digits", 4),
                    states=states,
                    current_state=current_state,
                    contract=DocumentContractPolicy(**contract_value),
                )
            )

        required_truth = project.get("required_current_truth")
        if required_truth is None:
            required_truth = [
                f"{_RECORD_ROLE_FOLDERS[name]}/README.md" for name in project["roles"]
            ]
        evidence_value = project.get("done_task_evidence")
        if evidence_value is None and "task" in project["roles"]:
            evidence_value = {
                "include": [f"tasks/{_RECORD_ID_GLOB}"],
                "headings": ["Completion evidence", "Evidence"],
            }
        evidence = (
            DoneTaskEvidencePolicy(
                include=tuple(
                    _normalized_project_value(repo_root, docs_root, item)
                    for item in evidence_value["include"]
                ),
                headings=tuple(evidence_value["headings"]),
            )
            if evidence_value
            else None
        )
        inventory_value = project.get("task_inventory", {})
        default_include = ["tasks/*.md"] if "task" in project["roles"] else []
        default_handoffs = ["handoffs/*.md"] if "handoff" in project["roles"] else []
        default_decisions = ["adr/*.md"] if "adr" in project["roles"] else []
        scopes.append(
            DocumentProjectScope(
                id=project["id"],
                root=root,
                docs_root=docs_root,
                currency=DocsCurrencyPolicy(
                    roles=tuple(roles),
                    required_current_truth=tuple(
                        _normalized_project_value(repo_root, docs_root, item)
                        for item in required_truth
                    ),
                    done_task_evidence=evidence,
                ),
                task_inventory=TaskInventoryPolicy(
                    include=tuple(
                        _normalized_project_value(repo_root, docs_root, item)
                        for item in inventory_value.get("include", default_include)
                    ),
                    handoffs=tuple(
                        _normalized_project_value(repo_root, docs_root, item)
                        for item in inventory_value.get("handoffs", default_handoffs)
                    ),
                    decisions=tuple(
                        _normalized_project_value(repo_root, docs_root, item)
                        for item in inventory_value.get("decisions", default_decisions)
                    ),
                    planning=_planning_policy(inventory_value.get("planning")),
                ),
            )
        )
    return DocumentProjectRegistry(tuple(scopes))


def load_manifest(path: str | Path, *, schema_path: str | Path | None = None) -> Manifest:
    """Load and validate a manifest without executing commands or changing files."""
    manifest_path = Path(path).resolve()
    try:
        loaded = yaml.load(manifest_path.read_text(encoding="utf-8"), Loader=_StrictSafeLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ManifestError([f"$: cannot read YAML: {exc}"]) from exc
    if not isinstance(loaded, dict):
        raise ManifestError(["$: expected a mapping"])

    version = loaded.get("version")
    if (
        isinstance(version, int)
        and not isinstance(version, bool)
        and version > SUPPORTED_MANIFEST_VERSION
    ):
        raise ManifestError(
            [
                (
                    f"$.version: unsupported manifest version {version}; "
                    f"maximum supported version is {SUPPORTED_MANIFEST_VERSION}"
                )
            ]
        )
    selected_version = version if version in (1, 2) else 1

    try:
        schema = json.loads(
            Path(schema_path or _schema_path(selected_version)).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load bundled engineering schema: {exc}") from exc

    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    issues = _schema_issues(validator, loaded)
    if selected_version == 2 and not issues:
        issues.extend(_v2_project_issues(loaded, manifest_path.parent))
    for index, document in enumerate(loaded.get("project", {}).get("documents", [])):
        if not _valid_relative_path(document):
            issues.append(f"$.project.documents[{index}]: invalid repository-relative path")
    for section in ("generated", "vendored", "sensitive", "forbidden"):
        for index, pattern in enumerate(loaded.get("paths", {}).get(section, [])):
            if not _valid_relative_path(pattern, glob=True):
                issues.append(f"$.paths.{section}[{index}]: invalid repository-relative glob")
    for name, spec in loaded.get("checks", {}).items():
        if not _valid_relative_path(spec.get("cwd", ".")):
            issues.append(f"$.checks.{name}.cwd: invalid repository-relative path")
        for index, pattern in enumerate(spec.get("applies_to", [])):
            if not _valid_relative_path(pattern, glob=True):
                issues.append(
                    f"$.checks.{name}.applies_to[{index}]: invalid repository-relative glob"
                )
    known_checks = set(loaded.get("checks", {}))
    for name, spec in loaded.get("profiles", {}).items():
        for index, reference in enumerate(spec.get("checks", [])):
            if reference not in known_checks:
                issues.append(f"$.profiles.{name}.checks[{index}]: unknown check {reference!r}")
    for name, patterns in loaded.get("classifiers", {}).items():
        for index, pattern in enumerate(patterns):
            if not _valid_relative_path(pattern, glob=True):
                issues.append(f"$.classifiers.{name}[{index}]: invalid repository-relative glob")
    fitness_names: set[str] = set()
    for index, item in enumerate(loaded.get("fitness", [])):
        name = item.get("name")
        if name in fitness_names:
            issues.append(f"$.fitness[{index}].name: duplicate name {name!r}")
        fitness_names.add(name)
        if "check" in item and item["check"] not in known_checks:
            issues.append(f"$.fitness[{index}].check: unknown check {item['check']!r}")
        for subindex, reference in enumerate(item.get("references", [])):
            if not _valid_relative_path(reference):
                issues.append(
                    f"$.fitness[{index}].references[{subindex}]: invalid repository-relative path"
                )
        for subindex, pattern in enumerate(item.get("applies_to", [])):
            if not _valid_relative_path(pattern, glob=True):
                issues.append(
                    f"$.fitness[{index}].applies_to[{subindex}]: invalid repository-relative glob"
                )
        for subindex, exception in enumerate(item.get("exceptions", [])):
            if not _valid_relative_path(exception.get("path", ""), glob=True):
                issues.append(
                    f"$.fitness[{index}].exceptions[{subindex}].path: "
                    "invalid repository-relative glob"
                )
    generated_names: set[str] = set()
    for index, item in enumerate(loaded.get("generated", [])):
        name = item.get("name")
        if name in generated_names:
            issues.append(f"$.generated[{index}].name: duplicate name {name!r}")
        generated_names.add(name)
        if not _valid_relative_path(item.get("cwd", ".")):
            issues.append(f"$.generated[{index}].cwd: invalid repository-relative path")
        for field in ("sources", "outputs"):
            for subindex, pattern in enumerate(item.get(field, [])):
                if not _valid_relative_path(pattern, glob=True):
                    issues.append(
                        f"$.generated[{index}].{field}[{subindex}]: "
                        "invalid repository-relative glob"
                    )
    for index, pattern in enumerate(loaded.get("docs", {}).get("include", [])):
        if not _valid_relative_path(pattern, glob=True):
            issues.append(f"$.docs.include[{index}]: invalid repository-relative glob")
    currency_value = loaded.get("docs", {}).get("currency", {})
    currency = currency_value if isinstance(currency_value, dict) else {}
    role_names: set[str] = set()
    roles = currency.get("roles", [])
    for index, role in enumerate(roles if isinstance(roles, list) else []):
        if not isinstance(role, dict):
            continue
        name = role.get("name")
        if isinstance(name, str):
            if name in role_names:
                issues.append(f"$.docs.currency.roles[{index}].name: duplicate name {name!r}")
            role_names.add(name)
        include = role.get("include", [])
        for subindex, pattern in enumerate(include if isinstance(include, list) else []):
            if not _valid_relative_path(pattern, glob=True):
                issues.append(
                    f"$.docs.currency.roles[{index}].include[{subindex}]: "
                    "invalid repository-relative glob"
                )
        if not _valid_relative_path(role.get("index", "")):
            issues.append(f"$.docs.currency.roles[{index}].index: invalid repository-relative path")
        if bool(role.get("states")) != bool(role.get("current_state")):
            issues.append(
                f"$.docs.currency.roles[{index}]: states and current_state must be declared together"
            )
        elif role.get("current_state") and role["current_state"] not in role["states"]:
            issues.append(
                f"$.docs.currency.roles[{index}].current_state: must be one of the declared states"
            )
        contract = role.get("contract")
        if isinstance(contract, dict):
            contract_role = contract.get("role")
            if contract_role != name:
                issues.append(
                    f"$.docs.currency.roles[{index}].contract.role: "
                    "must equal the enclosing role name"
                )
            if contract_role == "handoff":
                expected_states = HANDOFF_STATES
                if tuple(role.get("states", ())) != expected_states:
                    issues.append(
                        f"$.docs.currency.roles[{index}].states: handoff contract requires "
                        f"{list(expected_states)!r}"
                    )
                if role.get("current_state") != "current":
                    issues.append(
                        f"$.docs.currency.roles[{index}].current_state: "
                        "handoff contract requires 'current'"
                    )
    pointers = currency.get("required_current_truth", [])
    for index, pointer in enumerate(pointers if isinstance(pointers, list) else []):
        if not _valid_relative_path(pointer):
            issues.append(
                f"$.docs.currency.required_current_truth[{index}]: invalid repository-relative path"
            )
    done_evidence_value = currency.get("done_task_evidence", {})
    done_evidence = done_evidence_value if isinstance(done_evidence_value, dict) else {}
    done_includes = done_evidence.get("include", [])
    for index, pattern in enumerate(done_includes if isinstance(done_includes, list) else []):
        if not _valid_relative_path(pattern, glob=True):
            issues.append(
                f"$.docs.currency.done_task_evidence.include[{index}]: "
                "invalid repository-relative glob"
            )
    for field in ("include", "handoffs", "decisions"):
        for index, pattern in enumerate(loaded.get("task_inventory", {}).get(field, [])):
            if not _valid_relative_path(pattern, glob=True):
                issues.append(
                    f"$.task_inventory.{field}[{index}]: invalid repository-relative glob"
                )
    planning_value = loaded.get("task_inventory", {}).get("planning", {})
    planning = planning_value if isinstance(planning_value, dict) else {}
    planning_fields_value = planning.get("fields", {})
    planning_fields = planning_fields_value if isinstance(planning_fields_value, dict) else {}
    for name, spec in planning_fields.items():
        if not isinstance(spec, dict):
            continue
        values = spec.get("values", [])
        order = spec.get("order", [])
        if order and set(order) != set(values):
            issues.append(
                f"$.task_inventory.planning.fields.{name}.order: "
                "must contain every allowed value exactly once"
            )
    for index, name in enumerate(planning.get("default_order", [])):
        spec = planning_fields.get(name)
        if not isinstance(spec, dict):
            issues.append(
                f"$.task_inventory.planning.default_order[{index}]: unknown planning field {name!r}"
            )
        elif not spec.get("order"):
            issues.append(
                f"$.task_inventory.planning.default_order[{index}]: "
                f"planning field {name!r} has no explicit order"
            )
    for name, spec in loaded.get("reviewers", {}).items():
        if not _valid_relative_path(spec.get("cwd", ".")):
            issues.append(f"$.reviewers.{name}.cwd: invalid repository-relative path")
        for index, pattern in enumerate(spec.get("applies_to", [])):
            if not _valid_relative_path(pattern, glob=True):
                issues.append(
                    f"$.reviewers.{name}.applies_to[{index}]: invalid repository-relative glob"
                )
        if not spec.get("profiles"):
            issues.append(f"$.reviewers.{name}.profiles: reviewers require at least one profile")
        if spec.get("blocking") and not spec.get("owner"):
            issues.append(f"$.reviewers.{name}.owner: blocking reviewers require an owner")
        if spec.get("blocking") and (
            not spec.get("expected_provider") or not spec.get("expected_model")
        ):
            issues.append(
                f"$.reviewers.{name}: blocking reviewers require expected_provider and expected_model"
            )
        if bool(spec.get("exception_reason")) != bool(spec.get("exception_expires")):
            issues.append(
                f"$.reviewers.{name}: exception_reason and exception_expires must be declared together"
            )
    if issues:
        raise ManifestError(sorted(set(issues)))

    checks = {
        name: Check(
            name=name,
            command=tuple(spec["command"]),
            version_command=(tuple(spec["version_command"]) if "version_command" in spec else None),
            applies_to=tuple(spec.get("applies_to", ())),
            cwd=spec.get("cwd", "."),
            timeout_seconds=float(spec.get("timeout_seconds", 300)),
            max_output_bytes=spec.get("max_output_bytes", 1_000_000),
            redact=tuple(spec.get("redact", ())),
        )
        for name, spec in loaded["checks"].items()
    }
    profiles = {
        name: Profile(name, tuple(spec["checks"]))
        for name, spec in loaded.get("profiles", {}).items()
    }
    if loaded["version"] == 2:
        global_roles = tuple(
            DocumentRolePolicy(
                name=item["name"],
                include=tuple(item["include"]),
                index=item["index"],
                id_prefix_digits=item["id_prefix_digits"],
                contract=(
                    DocumentContractPolicy(**item["contract"]) if "contract" in item else None
                ),
                states=tuple(item.get("states", ())),
                current_state=item.get("current_state"),
            )
            for item in currency.get("roles", ())
        )
        return ManifestV2(
            path=manifest_path,
            version=loaded["version"],
            project=ProjectPolicy(
                risk=loaded["project"]["risk"],
                core_outcome=loaded["project"]["core_outcome"],
                documents=tuple(loaded["project"].get("documents", ())),
            ),
            paths=PathPolicy(
                **{key: tuple(value) for key, value in loaded.get("paths", {}).items()}
            ),
            checks=checks,
            profiles=profiles,
            classifiers={key: tuple(value) for key, value in loaded.get("classifiers", {}).items()},
            fitness=tuple(
                FitnessDeclaration(
                    name=item["name"],
                    check=item["check"],
                    rationale=item["rationale"],
                    references=tuple(item.get("references", ())),
                    applies_to=tuple(item.get("applies_to", ())),
                    exceptions=tuple(
                        FitnessException(**value) for value in item.get("exceptions", ())
                    ),
                )
                for item in loaded.get("fitness", ())
            ),
            generated=tuple(
                GeneratedPolicy(
                    name=item["name"],
                    sources=tuple(item["sources"]),
                    outputs=tuple(item["outputs"]),
                    command=tuple(item["command"]),
                    cwd=item.get("cwd", "."),
                )
                for item in loaded.get("generated", ())
            ),
            docs=DocsPolicy(
                include=tuple(loaded.get("docs", {}).get("include", ())),
                required_headings=tuple(loaded.get("docs", {}).get("required_headings", ())),
                forbid_legacy_links=loaded.get("docs", {}).get("forbid_legacy_links", False),
                currency=DocsCurrencyPolicy(roles=global_roles),
            ),
            # V2 has no repository-wide task inventory. The empty value is deliberately
            # non-scanning; v2 consumers must select a DocumentProjectScope instead.
            task_inventory=TaskInventoryPolicy(include=(), handoffs=(), decisions=()),
            reviewers={
                name: ReviewerDeclaration(
                    name=name,
                    adapter=spec["adapter"],
                    command=tuple(spec["command"]),
                    network=spec["network"],
                    blocking=spec.get("blocking", False),
                    profiles=tuple(spec.get("profiles", ())),
                    owner=spec.get("owner"),
                    expected_provider=spec.get("expected_provider"),
                    expected_model=spec.get("expected_model"),
                    exception_reason=spec.get("exception_reason"),
                    exception_expires=spec.get("exception_expires"),
                    version_command=(
                        tuple(spec["version_command"]) if "version_command" in spec else None
                    ),
                    cwd=spec.get("cwd", "."),
                    timeout_seconds=float(spec.get("timeout_seconds", 60)),
                    max_output_bytes=spec.get("max_output_bytes", 1_000_000),
                    redact=tuple(spec.get("redact", ())),
                    applies_to=tuple(spec.get("applies_to", ())),
                )
                for name, spec in loaded.get("reviewers", {}).items()
            },
            approval_required=tuple(loaded.get("approval_required", ())),
            raw=loaded,
            document_projects=_v2_project_registry(loaded, manifest_path.parent),
            agent_scheduling=loaded.get("agent_scheduling", {}).get("enabled", False),
            size_gate=SizeGateThresholds(
                max_acceptance_criteria=loaded.get("agent_scheduling", {}).get(
                    "max_acceptance_criteria",
                    SizeGateThresholds().max_acceptance_criteria,
                ),
                max_touched_dirs=loaded.get("agent_scheduling", {}).get(
                    "max_touched_dirs", SizeGateThresholds().max_touched_dirs
                ),
            ),
        )
    return Manifest(
        path=manifest_path,
        version=loaded["version"],
        project=ProjectPolicy(
            risk=loaded["project"]["risk"],
            core_outcome=loaded["project"]["core_outcome"],
            documents=tuple(loaded["project"].get("documents", ())),
        ),
        paths=PathPolicy(**{key: tuple(value) for key, value in loaded.get("paths", {}).items()}),
        checks=checks,
        profiles=profiles,
        classifiers={key: tuple(value) for key, value in loaded.get("classifiers", {}).items()},
        fitness=tuple(
            FitnessDeclaration(
                name=item["name"],
                check=item["check"],
                rationale=item["rationale"],
                references=tuple(item.get("references", ())),
                applies_to=tuple(item.get("applies_to", ())),
                exceptions=tuple(FitnessException(**value) for value in item.get("exceptions", ())),
            )
            for item in loaded.get("fitness", ())
        ),
        generated=tuple(
            GeneratedPolicy(
                name=item["name"],
                sources=tuple(item["sources"]),
                outputs=tuple(item["outputs"]),
                command=tuple(item["command"]),
                cwd=item.get("cwd", "."),
            )
            for item in loaded.get("generated", ())
        ),
        docs=DocsPolicy(
            include=tuple(loaded.get("docs", {}).get("include", ())),
            required_headings=tuple(loaded.get("docs", {}).get("required_headings", ())),
            forbid_legacy_links=loaded.get("docs", {}).get("forbid_legacy_links", False),
            currency=(
                DocsCurrencyPolicy(
                    roles=tuple(
                        DocumentRolePolicy(
                            name=item["name"],
                            include=tuple(item["include"]),
                            index=item["index"],
                            id_prefix_digits=item["id_prefix_digits"],
                            contract=(
                                DocumentContractPolicy(**item["contract"])
                                if "contract" in item
                                else None
                            ),
                            states=tuple(item.get("states", ())),
                            current_state=item.get("current_state"),
                        )
                        for item in currency.get("roles", ())
                    ),
                    required_current_truth=tuple(currency.get("required_current_truth", ())),
                    done_task_evidence=(
                        DoneTaskEvidencePolicy(
                            include=tuple(done_evidence["include"]),
                            headings=tuple(done_evidence["headings"]),
                        )
                        if done_evidence
                        else None
                    ),
                )
                if currency
                else None
            ),
        ),
        task_inventory=TaskInventoryPolicy(
            include=tuple(loaded.get("task_inventory", {}).get("include", ("docs/tasks/*.md",))),
            handoffs=tuple(
                loaded.get("task_inventory", {}).get("handoffs", ("docs/handoffs/*.md",))
            ),
            decisions=tuple(
                loaded.get("task_inventory", {}).get(
                    "decisions",
                    ("docs/adr/*.md", "docs/decisions/*.md"),
                )
            ),
            planning=(
                TaskPlanningPolicy(
                    fields={
                        name: TaskPlanningFieldPolicy(
                            values=tuple(spec["values"]),
                            order=tuple(spec.get("order", ())),
                        )
                        for name, spec in planning_fields.items()
                    },
                    default_order=tuple(planning.get("default_order", ())),
                )
                if planning
                else None
            ),
        ),
        reviewers={
            name: ReviewerDeclaration(
                name=name,
                adapter=spec["adapter"],
                command=tuple(spec["command"]),
                network=spec["network"],
                blocking=spec.get("blocking", False),
                profiles=tuple(spec.get("profiles", ())),
                owner=spec.get("owner"),
                expected_provider=spec.get("expected_provider"),
                expected_model=spec.get("expected_model"),
                exception_reason=spec.get("exception_reason"),
                exception_expires=spec.get("exception_expires"),
                version_command=(
                    tuple(spec["version_command"]) if "version_command" in spec else None
                ),
                cwd=spec.get("cwd", "."),
                timeout_seconds=float(spec.get("timeout_seconds", 60)),
                max_output_bytes=spec.get("max_output_bytes", 1_000_000),
                redact=tuple(spec.get("redact", ())),
                applies_to=tuple(spec.get("applies_to", ())),
            )
            for name, spec in loaded.get("reviewers", {}).items()
        },
        approval_required=tuple(loaded.get("approval_required", ())),
        raw=loaded,
    )
