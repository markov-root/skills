"""Strict, side-effect-free loading of ``engineering.yaml`` version 1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import jsonschema
import pathspec
import yaml
from pathspec.patterns.gitwildmatch import GitWildMatchPatternError

from ..resources import schema_path as bundled_schema_path
from .documents import HANDOFF_STATES, DocumentContractPolicy


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


def _schema_path() -> Path:
    return bundled_schema_path("engineering.schema.json")


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


def load_manifest(path: str | Path, *, schema_path: str | Path | None = None) -> Manifest:
    """Load and validate a manifest without executing commands or changing files."""
    manifest_path = Path(path).resolve()
    try:
        loaded = yaml.load(manifest_path.read_text(encoding="utf-8"), Loader=_StrictSafeLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ManifestError([f"$: cannot read YAML: {exc}"]) from exc
    if not isinstance(loaded, dict):
        raise ManifestError(["$: expected a mapping"])

    try:
        schema = json.loads(Path(schema_path or _schema_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load bundled engineering schema: {exc}") from exc

    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    issues = _schema_issues(validator, loaded)
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
