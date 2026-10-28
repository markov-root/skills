"""Project adoption config: visuals.toml schema, loader, discovery, and scaffold.

Owns the `visuals.toml` contract layer (task 0003): what an adopted project
declares, how a config is resolved and validated, how `visuals init` adopts an
existing tree, and the versioned JSON Schema in `public/assets/schemas/`.

Capability domain, not a command handler: command modules (`init_cmd.py`,
and later render/validate) import this module; it never imports a handler, the
dispatcher, or another capability domain (architecture doc, "Dependency
direction").

Design constraints, binding:

- ADR 0001: canvas geometry is configuration — declared data, not code.
- ADR 0004: config carries no compositional opinion. A canvas profile declares
  geometry, not design; no key in this schema may express a type scale, a
  colour, or a layout. Design tokens live in the theme (ADR 0005), never here.
- Task 0003 criterion 4: an invalid config reports the offending key, the
  expected shape, and the file and line — never a stack trace. `ConfigError`
  carries all four. `tomllib` parses values; a separate pass indexes key lines.
- Criterion 7: the schema is versioned; an unknown version is rejected
  explicitly, never guessed.

Resolution contract (`resolve_config`): walk UP from `start` for
`visuals.toml`. Return `None` when not inside an adopted project — `None`
means "not adopted", it never means "use defaults". Raise `ConfigError` on a
found-but-invalid config.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_NAME = "visuals.toml"
CONFIG_FILENAME = CONFIG_NAME  # readable alias for messages

#: The one config schema version this loader understands. Bumping it is a
#: deliberate act: update the schema file, this tuple, and the scaffold.
KNOWN_SCHEMA_VERSIONS: tuple[int, ...] = (1,)
SCHEMA_VERSION = KNOWN_SCHEMA_VERSIONS[-1]

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "assets"
    / "schemas"
    / "visuals-config.schema.json"
)

#: Registry/ledger/manifest keys, in declaration order.
REGISTRY_KEYS = ("source_registry", "claims_ledger", "consumer_manifest")

SAFE_AREA_KEYS = ("top", "right", "bottom", "left")

# Names selected by visuals.toml but evaluated only by `visuals check`.
MEASUREMENT_ADVISORIES = (
    "geometry-overflow", "effective-type-size", "text-contrast",
    "colour-only-encoding", "label-collision", "stage-geometry",
    "resolved-font-fallback",
)


# ---------------------------------------------------------------------------
# Errors and resolved types (the seam contract)
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Invalid config.

    Carries the offending key, the expected shape, and the file and line —
    everything a human or agent needs to fix the file without a traceback.
    `str()` renders the full message; the fields stay individually addressable
    for `--json` emitters.
    """

    def __init__(self, key: str, expected: str, file: Path, line: int | None) -> None:
        self.key = key
        self.expected = expected
        self.file = file
        self.line = line
        at = f"{file}:{line}" if line is not None else str(file)
        super().__init__(f"{at}: invalid config key {key!r}: expected {expected}")


@dataclass(frozen=True)
class CanvasProfile:
    """One canvas profile: geometry only, never design (ADR 0004)."""

    name: str
    width: int
    height: int
    safe_area: dict[str, int]  # {"top","right","bottom","left"} insets in px
    footer_band: int  # px
    delivery_scale: float  # e.g. 640/1920 for the delivery-size preview


@dataclass(frozen=True)
class Hook:
    """One declared pre-render hook. Declared only — running it is render's job."""

    name: str
    command: tuple[str, ...]
    cwd: Path


@dataclass(frozen=True)
class ScaffoldInclude:
    kind: str  # stylesheet | script
    path: str  # project-relative or web-root-absolute
    module: bool = False  # script type="module" only when declared


@dataclass(frozen=True)
class ScaffoldFooter:
    tag: str
    attributes: dict[str, str]


@dataclass(frozen=True)
class ScaffoldWiring:
    includes: tuple[ScaffoldInclude, ...]
    readiness: str | None  # ready | rendered | none; absent means no signal
    footer: ScaffoldFooter | None
    canvas: str | None


@dataclass(frozen=True)
class ResolvedConfig:
    """A validated project config. `root` is THE PROJECT ROOT (the directory
    holding the visuals.toml that was resolved)."""

    path: Path  # the visuals.toml actually used
    root: Path  # its directory — THE PROJECT ROOT
    schema_version: int
    canvas_profiles: dict[str, CanvasProfile]
    default_profile: str  # key into canvas_profiles
    theme: str | dict[str, Any]  # name/path (str) or inline table (ADR 0005 step 1)
    registry_paths: dict[str, Path]  # "source_registry" | "claims_ledger" | "consumer_manifest"
    hooks: tuple[Hook, ...]
    advisory_checks: tuple[str, ...]
    check_thresholds: dict[str, float]
    improve_max_iterations: int
    web_root: Path  # the directory served as the web root at render time (task 0017)
    styles: dict[str, str]  # declared name -> human description; no defaults or inheritance
    scaffold_wiring: dict[str, ScaffoldWiring]  # project-owned emission, keyed by style


# ---------------------------------------------------------------------------
# Line-tracking TOML reading
# ---------------------------------------------------------------------------

_KEY_PART = r'(?:[A-Za-z0-9_-]+|"(?:\\.|[^"\\])*"|\'[^\']*\')'
_KEY_PATH = rf'{_KEY_PART}(?:\s*\.\s*{_KEY_PART})*'
_RE_HEADER = re.compile(rf'^\s*(\[\[|\[)\s*({_KEY_PATH})\s*(\]\]|\])\s*(?:#.*)?$')
_RE_ASSIGNMENT = re.compile(rf'^\s*({_KEY_PATH})\s*=', re.S)


def _key_parts(key: str) -> tuple[str, ...]:
    """Let tomllib interpret quoted and dotted keys; never parse their syntax twice."""
    parsed = tomllib.loads(f"{key} = 0")
    parts: list[str] = []
    while isinstance(parsed, dict):
        part, parsed = next(iter(parsed.items()))
        parts.append(part)
    return tuple(parts)


def _read_toml_tracked(path: Path) -> tuple[dict[str, Any], dict[tuple[str, ...], int]]:
    """Parse with tomllib, then index declaration lines without interpreting values."""
    raw = path.read_text(encoding="utf-8")
    data = tomllib.loads(raw)
    lines: dict[tuple[str, ...], int] = {}
    table: tuple[str, ...] = ()
    for lineno, line in enumerate(raw.splitlines(), start=1):
        header = _RE_HEADER.match(line)
        if header and (header.group(1), header.group(3)) in (("[", "]"), ("[[", "]]")):
            table = _key_parts(header.group(2))
            for depth in range(1, len(table) + 1):
                lines.setdefault(table[:depth], lineno)
            continue
        assignment = _RE_ASSIGNMENT.match(line)
        if assignment:
            key = (*table, *_key_parts(assignment.group(1)))
            for depth in range(1, len(key) + 1):
                lines[key[:depth]] = lineno
    return data, lines


# ---------------------------------------------------------------------------
# Schema (single machine-readable source; errors cite file and line)
# ---------------------------------------------------------------------------


def _load_schema() -> dict[str, Any]:
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - artifact defect
        raise RuntimeError(f"visuals config schema unreadable at {SCHEMA_PATH}: {exc}") from None


def _profile_schema() -> dict[str, Any]:
    return _load_schema()["$defs"]["canvasProfile"]


def _hook_schema() -> dict[str, Any]:
    return _load_schema()["$defs"]["hook"]


def _expected_of(schema_node: dict[str, Any]) -> str:
    """A human 'expected' phrase for a schema node."""
    if "description" in schema_node:
        return str(schema_node["description"]).split(". ")[0]
    t = schema_node.get("type", "value")
    return f"a {t}"


def _err(key: str, expected: str, file: Path, lines: dict[tuple[str, ...], int]) -> ConfigError:
    dotted = tuple(re.sub(r"\[\d+\]$", "", part) for part in key.split(".")) if key else ()
    while dotted and dotted not in lines:
        dotted = dotted[:-1]
    return ConfigError(key, expected, file, lines.get(dotted))


def _fail(key: str, expected: str, file: Path, lines: dict[tuple[str, ...], int]) -> ConfigError:
    raise _err(key, expected, file, lines)


# --- typed accessors -------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_int(
    container: dict[str, Any],
    dotted: str,
    schema_node: dict[str, Any],
    file: Path,
    lines: dict[tuple[str, ...], int],
    minimum: int | None = None,
) -> int:
    value = container.get(dotted.rsplit(".", 1)[-1])
    if not _is_int(value):
        _fail(dotted, f"an integer{f' >= {minimum}' if minimum is not None else ''}", file, lines)
    if minimum is not None and value < minimum:
        _fail(dotted, f"an integer >= {minimum}", file, lines)
    return value


def _check_table(
    container: dict[str, Any],
    dotted: str,
    file: Path,
    lines: dict[tuple[str, ...], int],
) -> dict[str, Any]:
    value = container.get(dotted.rsplit(".", 1)[-1])
    if not isinstance(value, dict):
        _fail(dotted, "a table ([key] in TOML)", file, lines)
    return value


# --- per-table validation --------------------------------------------------


def _validate_canvas(
    data: dict[str, Any], file: Path, lines: dict[tuple[str, ...], int]
) -> tuple[dict[str, CanvasProfile], str]:
    canvas = data.get("canvas")
    if canvas is None:
        _fail("canvas", "a [canvas] table with default and profiles", file, lines)
    if not isinstance(canvas, dict):
        _fail("canvas", "a [canvas] table with default and profiles", file, lines)

    default = canvas.get("default")
    if not isinstance(default, str) or not default:
        _fail("canvas.default", "the name of a canvas profile declared in canvas.profiles", file, lines)

    profiles = canvas.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        _fail(
            "canvas.profiles",
            "at least one [canvas.profiles.<name>] table", file, lines,
        )

    pschema = _profile_schema()
    resolved: dict[str, CanvasProfile] = {}
    for name, raw in profiles.items():
        if not isinstance(raw, dict):
            _fail(f"canvas.profiles.{name}", "a table of profile fields", file, lines)
        _unexpected_keys(raw, pschema, f"canvas.profiles.{name}", file, lines)
        for field in pschema["required"]:
            if field not in raw:
                _fail(f"canvas.profiles.{name}.{field}", "required and missing", file, lines)
        width = _check_int(raw, f"canvas.profiles.{name}.width", pschema, file, lines, minimum=1)
        height = _check_int(raw, f"canvas.profiles.{name}.height", pschema, file, lines, minimum=1)
        safe = raw.get("safe_area")
        if not isinstance(safe, dict):
            _fail(f"canvas.profiles.{name}.safe_area", "a table with top/right/bottom/left insets", file, lines)
        _unexpected_keys(safe, pschema["properties"]["safe_area"], f"canvas.profiles.{name}.safe_area", file, lines)
        insets: dict[str, int] = {}
        for side in SAFE_AREA_KEYS:
            if side not in safe:
                _fail(f"canvas.profiles.{name}.safe_area.{side}", "required and missing", file, lines)
            insets[side] = _check_int(
                safe, f"canvas.profiles.{name}.safe_area.{side}", pschema, file, lines, minimum=0
            )
        footer = _check_int(raw, f"canvas.profiles.{name}.footer_band", pschema, file, lines, minimum=0)
        scale = raw.get("delivery_scale")
        if not isinstance(scale, (int, float)) or isinstance(scale, bool):
            _fail(f"canvas.profiles.{name}.delivery_scale", "a number with 0 < delivery_scale <= 1", file, lines)
        if not 0 < scale <= 1:
            _fail(f"canvas.profiles.{name}.delivery_scale", "a number with 0 < delivery_scale <= 1", file, lines)
        resolved[name] = CanvasProfile(
            name=name,
            width=width,
            height=height,
            safe_area=insets,
            footer_band=footer,
            delivery_scale=float(scale),
        )
    if default not in resolved:
        _fail("canvas.default", "the name of a canvas profile declared in canvas.profiles", file, lines)
    return resolved, default


def _validate_theme(data: dict[str, Any], file: Path, lines: dict[tuple[str, ...], int]) -> str | dict[str, Any]:
    theme = data.get("theme")
    if theme is None:
        _fail("theme", "a name, a path (string), or an inline token table (ADR 0005 steps 1-3)", file, lines)
    if isinstance(theme, str):
        if not theme:
            _fail("theme", "a non-empty name or path, or an inline table", file, lines)
        return theme
    if isinstance(theme, dict):
        return theme  # inline token table: structure is task 0004's to validate
    _fail("theme", "a name, a path (string), or an inline token table (ADR 0005 steps 1-3)", file, lines)


def _validate_paths(
    data: dict[str, Any], root: Path, file: Path, lines: dict[tuple[str, ...], int]
) -> dict[str, Path]:
    paths = data.get("paths")
    if paths is None:
        _fail("paths", f"a [paths] table with {', '.join(REGISTRY_KEYS)}", file, lines)
    if not isinstance(paths, dict):
        _fail("paths", f"a [paths] table with {', '.join(REGISTRY_KEYS)}", file, lines)
    pschema = _load_schema()["properties"]["paths"]
    _unexpected_keys(paths, pschema, "paths", file, lines)
    resolved: dict[str, Path] = {}
    for key in REGISTRY_KEYS:
        if key not in paths:
            _fail(f"paths.{key}", "required and missing", file, lines)
        value = paths[key]
        if not isinstance(value, str) or not value:
            _fail(f"paths.{key}", "a path relative to the project root", file, lines)
        candidate = (root / value).resolve()
        root_resolved = root.resolve()
        if candidate != root_resolved and root_resolved not in candidate.parents:
            _fail(f"paths.{key}", "a path inside the project root (no escaping it)", file, lines)
        resolved[key] = candidate
    return resolved


def _validate_web_root(
    data: dict[str, Any], root: Path, file: Path, lines: dict[tuple[str, ...], int]
) -> Path:
    """The directory served as the web root at render time (task 0017 D1).

    Deliberately NOT inside [paths]: those keys are validated as inside the
    project root, and the whole point of the web root is that it may sit
    ABOVE the project root (a repository root whose /_shared assets masters
    reference absolutely). Absent -> the project root, so existing adopted
    projects are unaffected. A web_root pointing nowhere fails at CONFIG
    LOAD with a named message, not later at render time. Whether the source
    directory sits under it is a per-visual fact render checks once the
    visual is located (check_source_under_root).
    """
    value = data.get("web_root")
    if value is None:
        return root.resolve()
    if not isinstance(value, str) or not value:
        _fail("web_root", "a path (string) relative to the project root — the "
              "directory served as the web root; omit it to serve the project root", file, lines)
    resolved = (root / value).resolve()
    if not resolved.is_dir():
        _fail("web_root", f"a directory that exists (resolved {resolved}); the web "
              "root is served as the document root at render time", file, lines)
    return resolved


def _validate_hooks(
    data: dict[str, Any], root: Path, file: Path, lines: dict[tuple[str, ...], int]
) -> tuple[Hook, ...]:
    hooks = data.get("hooks")
    if hooks is None:
        return ()
    if not isinstance(hooks, list):
        _fail("hooks", "an array of [[hooks]] tables", file, lines)
    schema = _hook_schema()
    resolved: list[Hook] = []
    seen: set[str] = set()
    for index, raw in enumerate(hooks):
        where = f"hooks[{index}]"
        if not isinstance(raw, dict):
            _fail(where, "a [[hooks]] table with name and run", file, lines)
        _unexpected_keys(raw, schema, where, file, lines)
        for field in schema["required"]:
            if field not in raw:
                _fail(f"{where}.{field}", "required and missing", file, lines)
        name = raw["name"]
        if not isinstance(name, str) or not name:
            _fail(f"{where}.name", "a non-empty unique name", file, lines)
        if name in seen:
            _fail(f"{where}.name", "a unique name (duplicate)", file, lines)
        seen.add(name)
        run = raw["run"]
        if not isinstance(run, list) or not run or not all(isinstance(a, str) and a for a in run):
            _fail(f"{where}.run", "a non-empty array of argument strings (argv, executed without a shell)", file, lines)
        cwd_value = raw.get("cwd", ".")
        if not isinstance(cwd_value, str) or not cwd_value:
            _fail(f"{where}.cwd", "a working directory relative to the project root", file, lines)
        cwd = (root / cwd_value).resolve()
        root_resolved = root.resolve()
        if cwd != root_resolved and root_resolved not in cwd.parents:
            _fail(f"{where}.cwd", "a working directory inside the project root (no escaping it)", file, lines)
        resolved.append(Hook(name=name, command=tuple(run), cwd=cwd))
    return tuple(resolved)


def _validate_advisory(data: dict[str, Any], file: Path, lines: dict[tuple[str, ...], int]) -> tuple[str, ...]:
    checks = data.get("advisory_checks")
    if checks is None:
        return ()
    if not isinstance(checks, list) or not all(isinstance(c, str) and c for c in checks):
        _fail("advisory_checks", "an array of check-name strings (possibly empty)", file, lines)
    seen: set[str] = set()
    for name in checks:
        if name in seen:
            _fail("advisory_checks", f"unique check names ({name!r} repeated)", file, lines)
        seen.add(name)
    return tuple(checks)


def _validate_check_thresholds(data: dict[str, Any], file: Path,
                               lines: dict[tuple[str, ...], int]) -> dict[str, float]:
    raw = data.get("check_thresholds", {})
    schema = _load_schema()["properties"]["check_thresholds"]
    if not isinstance(raw, dict):
        _fail("check_thresholds", "a table of numeric measurement thresholds", file, lines)
    _unexpected_keys(raw, schema, "check_thresholds", file, lines)
    result: dict[str, float] = {}
    for key, value in raw.items():
        floor = 0 if key in ("label_collision_max_area_px2", "stage_max_drift_px", "crop_margin_px") else 1
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not math.isfinite(value) or value < 0 or (floor and value == 0)):
            _fail(f"check_thresholds.{key}", "a finite number above zero" if floor else
                  "a finite nonnegative number", file, lines)
        result[key] = float(value)
    return result


def _validate_improve(data: dict[str, Any], file: Path,
                      lines: dict[tuple[str, ...], int]) -> int:
    raw = data.get("improve", {})
    if not isinstance(raw, dict):
        _fail("improve", "a table with max_iterations", file, lines)
    _unexpected_keys(raw, _load_schema()["properties"]["improve"], "improve", file, lines)
    cap = raw.get("max_iterations", 3)
    if not _is_int(cap) or not 1 <= cap <= 10:
        _fail("improve.max_iterations", "an integer from 1 to 10", file, lines)
    return cap


def _validate_styles(data: dict[str, Any], file: Path, lines: dict[tuple[str, ...], int]) -> dict[str, str]:
    styles = data.get("styles", {})
    if not isinstance(styles, dict):
        _fail("styles", "a table of named styles", file, lines)
    result: dict[str, str] = {}
    for name, entry in styles.items():
        where = f"styles.{name}"
        if not isinstance(entry, dict):
            _fail(where, "a table containing a description", file, lines)
        _unexpected_keys(entry, {"properties": {"description": {}}}, where, file, lines)
        description = entry.get("description")
        if not isinstance(description, str) or not description.strip():
            _fail(f"{where}.description", "a nonempty human description", file, lines)
        result[name] = description
    return result


def _validate_scaffold_wiring(
    data: dict[str, Any], profiles: dict[str, CanvasProfile],
    file: Path, lines: dict[tuple[str, ...], int],
) -> dict[str, ScaffoldWiring]:
    raw = data.get("scaffold", {})
    if not isinstance(raw, dict):
        _fail("scaffold", "a table keyed by a declared style name", file, lines)
    result: dict[str, ScaffoldWiring] = {}
    for name, entry in raw.items():
        where = f"scaffold.{name}"
        if not isinstance(entry, dict):
            _fail(where, "a table of includes, readiness, footer and canvas", file, lines)
        _unexpected_keys(entry, {"properties": {k: {} for k in
                          ("includes", "readiness", "footer", "canvas")}}, where, file, lines)
        includes = entry.get("includes", [])
        if not isinstance(includes, list):
            _fail(f"{where}.includes", "an array of include tables", file, lines)
        parsed_includes: list[ScaffoldInclude] = []
        for i, include in enumerate(includes):
            loc = f"{where}.includes[{i}]"
            if not isinstance(include, dict):
                _fail(loc, "a table with kind and path", file, lines)
            _unexpected_keys(include, {"properties": {"kind": {}, "path": {}, "module": {}}}, loc, file, lines)
            kind, path = include.get("kind"), include.get("path")
            if kind not in ("stylesheet", "script"):
                _fail(f"{loc}.kind", "stylesheet or script", file, lines)
            if not isinstance(path, str) or not path or path.startswith("//") or \
                    ".." in Path(path).parts or any(x in path for x in ("{{", "{%", "${", "?", "#")):
                _fail(f"{loc}.path", "a literal project-relative or web-root-absolute asset path", file, lines)
            module = include.get("module", False)
            if not isinstance(module, bool) or (module and kind != "script"):
                _fail(f"{loc}.module", "a boolean, true only on a script", file, lines)
            parsed_includes.append(ScaffoldInclude(kind, path, module))
        readiness = entry.get("readiness")
        if readiness is not None and readiness not in ("ready", "rendered", "none"):
            _fail(f"{where}.readiness", "ready, rendered, or none", file, lines)
        footer_raw = entry.get("footer")
        footer = None
        if footer_raw is not None:
            if not isinstance(footer_raw, dict):
                _fail(f"{where}.footer", "a table with tag and optional attributes", file, lines)
            _unexpected_keys(footer_raw, {"properties": {"tag": {}, "attributes": {}}},
                             f"{where}.footer", file, lines)
            tag = footer_raw.get("tag")
            attrs = footer_raw.get("attributes", {})
            if not isinstance(tag, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", tag):
                _fail(f"{where}.footer.tag", "a literal lowercase HTML tag name", file, lines)
            if not isinstance(attrs, dict) or any(
                not isinstance(k, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", k)
                or not isinstance(v, str) or any(x in v for x in ("{{", "{%", "${"))
                for k, v in attrs.items()
            ):
                _fail(f"{where}.footer.attributes", "literal string attributes", file, lines)
            footer = ScaffoldFooter(tag, attrs)
        canvas = entry.get("canvas")
        if canvas is not None and (not isinstance(canvas, str) or canvas not in profiles):
            _fail(f"{where}.canvas", "the name of a declared canvas profile", file, lines)
        result[name] = ScaffoldWiring(tuple(parsed_includes), readiness, footer, canvas)
    return result


def _unexpected_keys(
    table: dict[str, Any],
    schema_node: dict[str, Any],
    where: str,
    file: Path,
    lines: dict[tuple[str, ...], int],
) -> None:
    """additionalProperties: false, with the line the offending key sits on."""
    allowed = set(schema_node.get("properties", {}))
    for key in table:
        if key not in allowed:
            dotted = f"{where}.{key}" if where else key
            _fail(dotted, f"one of {', '.join(sorted(allowed))} (unknown key)", file, lines)


# --- whole-config validation -----------------------------------------------


def _validate(
    data: dict[str, Any],
    lines: dict[tuple[str, ...], int],
    file: Path,
    root: Path,
) -> ResolvedConfig:
    """Validate raw parsed data and build the ResolvedConfig."""
    schema = _load_schema()
    _unexpected_keys(data, schema, "", file, lines)

    version = data.get("schema_version")
    if version is None:
        _fail("schema_version", "a config schema version (this loader knows: "
              + ", ".join(str(v) for v in KNOWN_SCHEMA_VERSIONS) + ")", file, lines)
    if isinstance(version, str) and version.isdigit():
        version = int(version)
    if not _is_int(version):
        _fail("schema_version", "an integer config schema version", file, lines)
    if version not in KNOWN_SCHEMA_VERSIONS:
        _fail("schema_version", "a config schema version this loader knows (found "
              f"{version}; known: {', '.join(str(v) for v in KNOWN_SCHEMA_VERSIONS)})", file, lines)

    profiles, default = _validate_canvas(data, file, lines)
    theme = _validate_theme(data, file, lines)
    registry_paths = _validate_paths(data, root, file, lines)
    hooks = _validate_hooks(data, root, file, lines)
    advisory = _validate_advisory(data, file, lines)
    check_thresholds = _validate_check_thresholds(data, file, lines)
    improve_max_iterations = _validate_improve(data, file, lines)
    styles = _validate_styles(data, file, lines)
    scaffold_wiring = _validate_scaffold_wiring(data, profiles, file, lines)
    web_root = _validate_web_root(data, root, file, lines)

    return ResolvedConfig(
        path=file,
        root=root,
        schema_version=version,
        canvas_profiles=profiles,
        default_profile=default,
        theme=theme,
        registry_paths=registry_paths,
        hooks=hooks,
        advisory_checks=advisory,
        check_thresholds=check_thresholds,
        improve_max_iterations=improve_max_iterations,
        web_root=web_root,
        styles=styles,
        scaffold_wiring=scaffold_wiring,
    )


# ---------------------------------------------------------------------------
# Resolution and discovery
# ---------------------------------------------------------------------------


def resolve_config(start: Path) -> ResolvedConfig | None:
    """Walk UP from `start` for visuals.toml. Return None when not inside an
    adopted project — None means "not adopted", it never means "use defaults".
    Raise ConfigError on a found-but-invalid config."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        path = candidate / CONFIG_NAME
        if path.is_file():
            return load_config(path)
    return None


def load_config(path: Path) -> ResolvedConfig:
    """Load and validate one visuals.toml. Raises ConfigError with key,
    expected shape, file, and line on anything invalid — never a traceback."""
    path = path.resolve()
    try:
        data, lines = _read_toml_tracked(path)
    except tomllib.TOMLDecodeError:
        raise
    return _validate(data, lines, path, path.parent)


# ---------------------------------------------------------------------------
# Discovery: what `visuals init` infers from an existing tree
# ---------------------------------------------------------------------------

CORPUS_PROFILE_SLIDE = "slide"
CORPUS_PROFILE_TITLE_BAND = "title-band"

#: The shared renderer's own defaults (`_shared/render/render.sh`):
#: WIDTH=1920 HEIGHT=1080. Wrappers that do not set RENDER_WIDTH/RENDER_HEIGHT
#: inherit this.
SHARED_RENDERER_DEFAULT = (1920, 1080)

#: The title-band geometry: the deck owns the title in a 108px band, so a
#: chart below it is 1920x972 (STANDARDS.md, "Canvas and composition").
TITLE_BAND_SIZE = (1920, 972)

#: Default insets and the fixed source-credit footer band.
CORPUS_INSETS = {"top": 32, "right": 40, "bottom": 24, "left": 40}
CORPUS_FOOTER_BAND = 62

#: Delivery-size preview: the 640px legibility check at full-slide width.
DELIVERY_WIDTH = 640


def delivery_scale_for(width: int) -> float:
    return DELIVERY_WIDTH / width


def discover_project_shape(root: Path) -> dict[str, Any] | None:
    """Infer corpus evidence from an existing tree, read-only.

    Returns the pieces of a visuals.toml body the renderer actually varied:
    the two canvas profiles in use, the registry/ledger/manifest paths, and
    the pre-render hooks the wrapper variants encode (audit F3). Returns None
    when nothing in the tree looks like a visuals corpus.
    """
    profiles: dict[str, dict[str, Any]] = {}
    hooks: list[dict[str, Any]] = []

    if (root / "CONVENTIONS.md").is_file():
        # The full-slide default the shared renderer itself declares.
        profiles[CORPUS_PROFILE_SLIDE] = {
            "width": SHARED_RENDERER_DEFAULT[0],
            "height": SHARED_RENDERER_DEFAULT[1],
            "safe_area": dict(CORPUS_INSETS),
            "footer_band": CORPUS_FOOTER_BAND,
            "delivery_scale": delivery_scale_for(SHARED_RENDERER_DEFAULT[0]),
        }

    for wrapper in sorted(root.glob("**/render.sh")):
        text = wrapper.read_text(encoding="utf-8", errors="replace")
        if "_shared/render/render.sh" not in text:
            continue  # not a corpus wrapper; do not claim it as evidence
        width_m = re.search(r"RENDER_WIDTH\s*=\s*(\d+)", text)
        height_m = re.search(r"RENDER_HEIGHT\s*=\s*(\d+)", text)
        size = (
            (int(width_m.group(1)), int(height_m.group(1)))
            if width_m and height_m
            else SHARED_RENDERER_DEFAULT
        )
        if size == TITLE_BAND_SIZE:
            profiles.setdefault(
                CORPUS_PROFILE_TITLE_BAND,
                {
                    "width": size[0],
                    "height": size[1],
                    "safe_area": dict(CORPUS_INSETS),
                    "footer_band": CORPUS_FOOTER_BAND,
                    "delivery_scale": delivery_scale_for(size[0]),
                },
            )
        visual_dir = wrapper.parent
        derive = sorted(visual_dir.glob("derive.mjs"))
        if derive:
            hooks.append(
                {
                    "name": _unique_hook_name(hooks, f"derive-{visual_dir.name}"),
                    "run": ["node", derive[0].name],
                    "cwd": _relative_to_root(root, visual_dir),
                }
            )
        sync = visual_dir / "sync-data.sh"
        if sync.is_file():
            hooks.append(
                {
                    "name": _unique_hook_name(hooks, f"sync-data-{visual_dir.name}"),
                    "run": ["./sync-data.sh", "--no-fetch"],
                    "cwd": _relative_to_root(root, visual_dir),
                }
            )

    if not profiles:
        return None

    return {
        "profiles": profiles,
        "hooks": hooks,
        "paths": _discover_paths(root),
        "theme": _discover_theme(root),
        "web_root": _discover_web_root(root),
    }


def _unique_hook_name(existing: list[dict[str, Any]], base: str) -> str:
    names = {h["name"] for h in existing}
    if base not in names:
        return base
    i = 2
    while f"{base}-{i}" in names:
        i += 1
    return f"{base}-{i}"


def _relative_to_root(root: Path, target: Path) -> str:
    return target.resolve().relative_to(root.resolve()).as_posix()


def _find_unique(root: Path, filename: str) -> str | None:
    """Path of the unique non-template file with this name, relative to root.
    Files under a `templates/` directory are scaffolding, not the project's
    contract file, and are skipped — the corpus carries both
    `research/CLAIMS.md` and `_shared/templates/CLAIMS.md`, and without the
    skip, discovery is ambiguous. The corpus's own source registry legitimately
    lives under `visuals/_shared/`, so `_shared/` as such is NOT skipped."""
    hits = []
    for p in root.glob(f"**/{filename}"):
        parts = p.relative_to(root).parts
        if "templates" in parts:
            continue
        hits.append(p)
    if len(hits) == 1:
        return _relative_to_root(root, hits[0])
    return None


def _discover_paths(root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    candidates = {
        "source_registry": "sources.json",
        "claims_ledger": "CLAIMS.md",
        "consumer_manifest": "SLIDES.md",
    }
    for key, filename in candidates.items():
        rel = _find_unique(root, filename)
        if rel:
            found[key] = rel
    return found


def _discover_web_root(root: Path) -> tuple[str, str] | None:
    """Find the nearest ancestor justified by a missing root-absolute asset.

    A parent directory alone is not evidence. Only a reference found in a
    master (or its local stylesheet) that fails at root and resolves at that
    ancestor can move the served web root.
    """
    refs: set[str] = set()
    asset_re = re.compile(
        r"\b(?:src|href)\s*=\s*[\"'](/[^\"'#?]+)[\"']|url\(\s*[\"']?(/[^\"')]+)",
        re.I,
    )
    css_re = re.compile(
        r"<link[^>]*\brel=[\"']stylesheet[\"'][^>]*\bhref=[\"']([^\"']+)[\"']", re.I
    )
    for master in sorted(root.glob("**/source*/**/*.html")):
        html = master.read_text(encoding="utf-8", errors="replace")
        texts = [html]
        for href in css_re.findall(html):
            if href.startswith(("/", "//", "http:", "https:", "data:")):
                continue
            css = (master.parent / href).resolve()
            if css.is_file() and (root.resolve() == css or root.resolve() in css.parents):
                texts.append(css.read_text(encoding="utf-8", errors="replace"))
        for text in texts:
            for match in asset_re.finditer(text):
                ref = match.group(1) or match.group(2)
                if ref.startswith("//") or ".." in Path(ref).parts:
                    continue
                if not (root / ref.lstrip("/")).is_file():
                    refs.add(ref)
    ancestors = root.resolve().parents
    resolved_refs = {
        ref for ref in refs
        if any((ancestor / ref.lstrip("/")).is_file() for ancestor in ancestors)
    }
    for ancestor in ancestors:
        if resolved_refs and all(
            (ancestor / ref.lstrip("/")).is_file() for ref in resolved_refs
        ):
            return (Path(os.path.relpath(ancestor, root)).as_posix(), sorted(resolved_refs)[0])
    return None


def _discover_theme(root: Path) -> str:
    """The corpus's theme as a NAME for ADR 0005 step 2/3 lookup. Naming the
    brand is honest even before a project theme TOML exists; resolving it is
    task 0004's job."""
    if (root / "CONVENTIONS.md").is_file():
        return "spain"
    return "default"


# ---------------------------------------------------------------------------
# Scaffold (neutral) and the TOML writer
# ---------------------------------------------------------------------------


def scaffold_body() -> dict[str, Any]:
    """The empty-directory scaffold: one neutral profile, zero insets, no
    hooks, no advisory selection, default theme. Geometry and contract wiring
    only — no borrowed compositional opinion (ADR 0004)."""
    width, height = SHARED_RENDERER_DEFAULT
    return {
        "canvas": {
            "default": CORPUS_PROFILE_SLIDE,
            "profiles": {
                CORPUS_PROFILE_SLIDE: {
                    "width": width,
                    "height": height,
                    "safe_area": {side: 0 for side in SAFE_AREA_KEYS},
                    "footer_band": 0,
                    "delivery_scale": delivery_scale_for(width),
                }
            },
        },
        "theme": "neutral",  # the bundled brand-neutral default; must resolve out of the box
        "paths": {key: f"visuals/_shared/{name}" for key, name in (
            ("source_registry", "sources.json"),
            ("claims_ledger", "CLAIMS.md"),
            ("consumer_manifest", "SLIDES.md"),
        )},
        "hooks": [],
        "advisory_checks": [],
        "check_thresholds": {},
    }


def to_toml(body: dict[str, Any]) -> str:
    """Render a config body as TOML the loader accepts. Root-level bare keys
    are written before any [table] header — a bare key after a table header
    belongs to that table, which is exactly the drift this writer must not
    manufacture. The schema_version is written quoted (it is a semantic
    version, not a number to compute with)."""
    out: list[str] = []
    out.append("# visuals.toml — project adoption config (schema docs: assets/schemas/visuals-config.schema.json)")
    out.append("# Geometry and contract only. Per ADR 0004, no key here may express a type scale, a colour, or a layout.")
    out.append("")
    out.append(f'schema_version = "{SCHEMA_VERSION}"')
    out.append("")

    # Root-level bare keys first; every table header after this point would
    # otherwise capture them.
    theme = body["theme"]
    if isinstance(theme, dict):
        out.append("advisory_checks = " + _toml_array(list(body.get("advisory_checks", ()))))
        out.append("")
    else:
        out.append(f'theme = "{theme}"')
        out.append("advisory_checks = " + _toml_array(list(body.get("advisory_checks", ()))))
        out.append("")
    if body.get("web_root"):
        out.append(f'web_root = "{body["web_root"]}" # found via {body["web_root_reference"]}')
        out.append("")

    if body.get("check_thresholds"):
        out.append("[check_thresholds]")
        for key, value in body["check_thresholds"].items():
            out.append(f"{key} = {value}")
        out.append("")

    canvas = body["canvas"]
    out.append("[canvas]")
    out.append(f'default = "{canvas["default"]}"')
    out.append("")
    for name, profile in canvas["profiles"].items():
        out.append(f"[canvas.profiles.{name}]")
        out.append(f"width = {profile['width']}")
        out.append(f"height = {profile['height']}")
        out.append(f"footer_band = {profile['footer_band']}")
        scale = profile["delivery_scale"]
        scale_text = repr(scale) if isinstance(scale, float) else str(scale)
        out.append(f"delivery_scale = {scale_text}")
        out.append(f"[canvas.profiles.{name}.safe_area]")
        for side in SAFE_AREA_KEYS:
            out.append(f"{side} = {profile['safe_area'][side]}")
        out.append("")

    if isinstance(theme, dict):
        out.append("[theme]")
        for key, value in theme.items():
            out.append(_toml_value_line(key, value))
        out.append("")

    out.append("[paths]")
    for key in REGISTRY_KEYS:
        note = " # not found — fill this in" if key in body.get("_undiscovered_paths", ()) else ""
        out.append(f'{key} = "{body["paths"][key]}"{note}')
    out.append("")

    for hook in body.get("hooks", ()):
        out.append("[[hooks]]")
        out.append(f'name = "{hook["name"]}"')
        out.append("run = " + _toml_array(hook["run"]))
        if hook.get("cwd"):
            out.append(f'cwd = "{hook["cwd"]}"')
        out.append("")

    return "\n".join(out)


def _toml_array(items: list[str]) -> str:
    return "[" + ", ".join(f'"{i}"' for i in items) + "]"


def _toml_value_line(key: str, value: Any) -> str:
    if isinstance(value, str):
        return f'{key} = "{value}"'
    if isinstance(value, bool):
        return f"{key} = {'true' if value else 'false'}"
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return f"{key} = {_toml_array(value)}"
    if isinstance(value, list):
        return f"{key} = [" + ", ".join(_toml_inline(v) for v in value) + "]"
    return f"{key} = {_toml_inline(value)}"


def _toml_inline(value: Any) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml_inline(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_inline(v) for v in value) + "]"
    return str(value)


def schema_version_of(path: Path) -> int:
    """Read just the schema_version of a config file. Raises ConfigError for a
    missing or malformed version — the same message shape as a full load."""
    path = path.resolve()
    data, lines = _read_toml_tracked(path)
    version = data.get("schema_version")
    if isinstance(version, str) and version.isdigit():
        version = int(version)
    if not _is_int(version):
        _fail("schema_version", "an integer config schema version", path, lines)
    if version not in KNOWN_SCHEMA_VERSIONS:  # type: ignore[operator]
        _fail("schema_version", "a config schema version this loader knows (found "
              f"{version}; known: {', '.join(str(v) for v in KNOWN_SCHEMA_VERSIONS)})", path, lines)
    return version  # type: ignore[return-value]


def is_schema_current(path: Path) -> bool:
    """True when the file's schema_version is one this build understands."""
    try:
        return schema_version_of(path) in KNOWN_SCHEMA_VERSIONS
    except ConfigError:
        return False


def _cli_banner() -> str:  # pragma: no cover - informational
    return f"visuals config schema v{SCHEMA_VERSION}: {SCHEMA_PATH}"


if __name__ == "__main__":  # pragma: no cover - manual inspection aid
    print(_cli_banner())
    for arg in sys.argv[1:]:
        try:
            cfg = load_config(Path(arg))
            print(f"{arg}: OK (schema_version {cfg.schema_version}, root {cfg.root})")
        except ConfigError as exc:
            print(f"{arg}: {exc}")
