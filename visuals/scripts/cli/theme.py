#!/usr/bin/env python3
"""Theme token resolution — the single machine-readable source for theme values.

A theme is a machine-readable TOML token file (schema_version 1) holding
semantic colour roles, type families and scale, the chart palette, and
encoding defaults. Stylesheets, chart palettes, and this validator derive
their values from it rather than restating them: a hex value written in a
second place is the defect audit F7 records (ADR 0005).

Resolution order (ADR 0005, fixed — this module implements it exactly):

1. an explicit path in the project's ``visuals.toml`` theme reference
   (step ``project-inline``);
2. a named lookup in the project's own ``themes/`` directory
   (step ``project-dir``);
3. a named lookup in the user registry ``~/.config/visuals/themes/``
   (step ``user-registry`` — READ only, never written by any command);
4. the brand-neutral default bundled at ``assets/themes/neutral.toml``
   (step ``bundled``).

A theme found at a later step still falls back, value by value, to the
bundled default for tokens it does not declare; ``ResolvedTheme`` reports
which step supplied every token, so the mixture is never folklore. The
bundled default is brand-neutral by decision of ADR 0005 — no client or
third-party brand ships inside the artifact.

The palette validator (``validate_tokens``) is implemented independently
from primary sources recorded in ``public/references/SOURCES.md``: contrast
thresholds from WCAG 2.2 (SC 1.4.3, SC 1.4.11) and colour distance in
CIEDE2000 (Sharma, Wu & Dalal 2005; the implementation is verified against
that paper's published test-pair dataset in the dev test suite). All findings
are advisory and never block (ADR 0004).

This module is a capability domain, not a command handler: ``render.py``
(task 0005) imports ``resolve_theme`` for its provenance receipt. The
interface (``ThemeUnavailable``, ``ResolvedTheme``, ``resolve_theme``) is
fixed by the wave-1 seam contract — a signature change breaks task 0005
silently.
"""

from __future__ import annotations

import math
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # task 0003 owns config.py; imported for typing only
    from config import ResolvedConfig

SCHEMA_VERSION = 1

# Resolution steps, in ADR 0005 order (the seam contract fixes these names).
STEP_PROJECT_INLINE = "project-inline"
STEP_PROJECT_DIR = "project-dir"
STEP_USER_REGISTRY = "user-registry"
STEP_BUNDLED = "bundled"
STEPS = (STEP_PROJECT_INLINE, STEP_PROJECT_DIR, STEP_USER_REGISTRY, STEP_BUNDLED)

BUNDLED_THEMES_DIR = Path(__file__).resolve().parents[2] / "assets" / "themes"
BUNDLED_DEFAULT_NAME = "neutral"
PROJECT_THEMES_DIRNAME = "themes"
THEME_SUFFIX = ".toml"

CONTRAST_TEXT_MIN = 4.5  # WCAG 2.2 SC 1.4.3 (normal text, Level AA)
CONTRAST_NON_TEXT_MIN = 3.0  # WCAG 2.2 SC 1.4.11 (graphical objects, Level AA)


def user_themes_dir() -> Path:
    """The user-level theme registry — READ only; nothing here ever writes it."""
    return Path.home() / ".config" / "visuals" / "themes"


class ThemeUnavailable(Exception):
    """Named theme found in none of the four ADR 0005 locations. Message names all four."""

    searched: tuple[str, ...]

    def __init__(self, searched: tuple[str, ...]) -> None:
        self.searched = tuple(searched)
        super().__init__(
            "theme not found in any of the four resolution locations:\n  "
            + "\n  ".join(self.searched)
        )


class ThemeSchemaError(ValueError):
    """A theme declares a value the schema does not know, or in a malformed shape.

    Rejected with the key named — never silently ignored (criterion 7).
    """

    def __init__(self, key: str, problem: str, source: str = "") -> None:
        self.key = key
        where = f" in {source}" if source else ""
        super().__init__(f"theme key {key!r}: {problem}{where}")


@dataclass(frozen=True)
class ResolvedTheme:
    name: str
    tokens: dict[str, object]  # semantic colour roles, type families/scale, chart palette
    resolution_steps: dict[str, str]  # token key -> the step that supplied it
    steps_consulted: tuple[str, ...]  # ordered: project-inline, project-dir, user-registry, bundled


# --------------------------------------------------------------------------
# Colour maths — implemented independently from primary sources recorded in
# public/references/SOURCES.md: WCAG 2.2 for luminance and contrast ratio;
# Sharma, Wu & Dalal (2005) for CIEDE2000, whose published 34-pair test-pair
# dataset the dev suite replays against this implementation.
# --------------------------------------------------------------------------

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def parse_hex(value: object) -> tuple[float, float, float]:
    """Parse #rgb / #rrggbb into sRGB components in [0, 1]. Raises ValueError."""
    if not isinstance(value, str) or not _HEX_RE.match(value):
        raise ValueError(f"not a hex colour: {value!r}")
    v = value[1:]
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    return (
        int(v[0:2], 16) / 255.0,
        int(v[2:4], 16) / 255.0,
        int(v[4:6], 16) / 255.0,
    )


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_value: str) -> float:
    """WCAG 2.2 relative luminance of a hex colour (SC 1.4.3 definition)."""
    r, g, b = parse_hex(hex_value)
    lin = (_srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b))
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """WCAG contrast ratio: (L_lighter + 0.05) / (L_darker + 0.05)."""
    l1 = relative_luminance(fg_hex)
    l2 = relative_luminance(bg_hex)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


# sRGB -> CIE XYZ (D65) -> CIELAB, then CIEDE2000.
_SRGB_TO_XYZ = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)
_D65 = (0.95047, 1.00000, 1.08883)


def _f_lab(t: float) -> float:
    delta = 6 / 29
    return t ** (1 / 3) if t > delta**3 else t / (3 * delta * delta) + 4 / 29


def srgb_to_lab(hex_value: str) -> tuple[float, float, float]:
    r, g, b = parse_hex(hex_value)
    lin = (_srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b))
    xyz = [sum(_SRGB_TO_XYZ[row][c] * lin[c] for c in range(3)) for row in range(3)]
    fx, fy, fz = (_f_lab(xyz[i] / _D65[i]) for i in range(3))
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def ciede2000(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """CIEDE2000 colour difference with kL = kC = kH = 1 (CIE 142:2001).

    Implemented from Sharma, Wu & Dalal (2005), including the hue-mean
    edge cases (|h1'-h2'| > 180 degrees and C1'*C2' == 0) that paper
    documents. The dev suite replays the paper's published 34-pair
    dataset against this function.
    """
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2

    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2.0
    pow25_7 = 25.0**7
    g = 0.5 * (1.0 - math.sqrt(c_bar**7 / (c_bar**7 + pow25_7)))

    a1p = (1.0 + g) * a1
    a2p = (1.0 + g) * a2
    c1p = math.hypot(a1p, b1)
    c2p = math.hypot(a2p, b2)

    def hue(ap: float, b: float) -> float:
        if ap == 0.0 and b == 0.0:
            return 0.0
        h = math.degrees(math.atan2(b, ap))
        return h + 360.0 if h < 0.0 else h

    h1p = hue(a1p, b1)
    h2p = hue(a2p, b2)

    dlp = l2 - l1
    dcp = c2p - c1p

    if c1p * c2p == 0.0:
        dhp = 0.0
    else:
        diff = h2p - h1p
        if abs(diff) <= 180.0:
            dhp = diff
        elif diff > 180.0:
            dhp = diff - 360.0
        else:
            dhp = diff + 360.0
    dhp_big = 2.0 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2.0)

    lbp = (l1 + l2) / 2.0
    cbp = (c1p + c2p) / 2.0

    if c1p * c2p == 0.0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180.0:
        hbp = (h1p + h2p) / 2.0
    elif (h1p + h2p) < 360.0:
        hbp = (h1p + h2p + 360.0) / 2.0
    else:
        hbp = (h1p + h2p - 360.0) / 2.0

    t = (
        1.0
        - 0.17 * math.cos(math.radians(hbp - 30.0))
        + 0.24 * math.cos(math.radians(2.0 * hbp))
        + 0.32 * math.cos(math.radians(3.0 * hbp + 6.0))
        - 0.20 * math.cos(math.radians(4.0 * hbp - 63.0))
    )
    d_theta = 30.0 * math.exp(-(((hbp - 275.0) / 25.0) ** 2))
    rc = 2.0 * math.sqrt(cbp**7 / (cbp**7 + pow25_7))
    sl = 1.0 + (0.015 * (lbp - 50.0) ** 2) / math.sqrt(20.0 + (lbp - 50.0) ** 2)
    sc = 1.0 + 0.045 * cbp  # Eq. (19) of Sharma, Wu & Dalal (2005)
    sh = 1.0 + 0.015 * cbp * t
    rt = -math.sin(math.radians(2.0 * d_theta)) * rc

    term_l = dlp / sl
    term_c = dcp / sc
    term_h = dhp_big / sh
    return math.sqrt(term_l * term_l + term_c * term_c + term_h * term_h + rt * term_c * term_h)


# --------------------------------------------------------------------------
# Token schema (theme file format, schema_version 1)
# --------------------------------------------------------------------------

_TOP_KEYS = ("schema_version", "name", "colour", "type", "chart", "encoding")
_ROLE_KEYS = ("hex", "kind", "on")
_KINDS = ("text", "non-text")


def _is_number(value: object) -> bool:
    """A TOML number — bools are ints in Python but not numbers here."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _err(key: str, problem: str, source: str) -> ThemeSchemaError:
    return ThemeSchemaError(key, problem, source)


def _iter_roles(node: object, prefix: str = ""):
    """Yield (dotted role name, role table) for roles nested to any depth:
    [colour.roles.text.body] is role "text.body"."""
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and not (set(value) & set(_ROLE_KEYS)):
            yield from _iter_roles(value, path)
        else:
            yield path, value


def _validate_role(node: object, path: str, source: str) -> None:
    if not isinstance(node, dict):
        raise _err(path, "must be a table", source)
    for sub, value in node.items():
        key = f"{path}.{sub}"
        if sub == "hex":
            try:
                parse_hex(value)
            except ValueError as exc:
                raise _err(key, str(exc), source) from None
        elif sub == "kind":
            if value not in _KINDS:
                raise _err(key, f"must be one of {', '.join(_KINDS)}", source)
        elif sub == "on":
            if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
                raise _err(key, "must be a list of role names", source)
        else:
            raise _err(key, "unknown role key (known: " + ", ".join(_ROLE_KEYS) + ")", source)


def flatten_tokens(tokens: dict[str, object]) -> dict[str, object]:
    """Public view of the token tree as flat dotted keys -> leaf values."""
    return _flatten(tokens)


def validate_theme_data(data: object, source: str = "") -> None:
    """Validate one theme token table against the schema_version 1 schema.

    Unknown or malformed keys are rejected with the key named — never
    ignored (task criterion 7). Partial tables are valid: a theme may
    override only some tokens and fall back, value by value, to the bundled
    default for the rest.
    """
    if not isinstance(data, dict):
        raise _err("<theme>", "theme table must be a TOML table", source)
    for key in data:
        if key not in _TOP_KEYS:
            raise _err(key, "unknown top-level key (schema_version 1 knows: "
                            + ", ".join(_TOP_KEYS) + ")", source)
    if "schema_version" not in data:
        raise _err("schema_version", "missing — every theme declares one", source)
    sv = data["schema_version"]
    if not _is_number(sv) or sv != SCHEMA_VERSION:
        raise _err("schema_version", f"must be {SCHEMA_VERSION}, got {sv!r}", source)
    if "name" in data and not isinstance(data["name"], str):
        raise _err("name", "must be a string", source)
    if not any(k in data for k in ("colour", "type", "chart", "encoding")):
        raise _err("<theme>", "declares no tokens at all", source)

    colour = data.get("colour")
    if colour is not None:
        if not isinstance(colour, dict) or set(colour) - {"roles"}:
            raise _err("colour", "must be a table with only the key 'roles'", source)
        roles = colour.get("roles")
        if roles is not None:
            if not isinstance(roles, dict):
                raise _err("colour.roles", "must be a table of roles", source)
            for role_path, role in _iter_roles(roles):
                _validate_role(role, f"colour.roles.{role_path}", source)

    ttype = data.get("type")
    if ttype is not None:
        if not isinstance(ttype, dict) or set(ttype) - {"families", "scale", "base"}:
            raise _err("type", "must be a table with keys families, scale, base", source)
        families = ttype.get("families")
        if families is not None:
            if not isinstance(families, dict):
                raise _err("type.families", "must be a table of families", source)
            for fam, spec in families.items():
                key = f"type.families.{fam}"
                if not isinstance(spec, dict) or set(spec) - {"stack"}:
                    raise _err(key, "must be a table with only the key 'stack'", source)
                if "stack" in spec and not isinstance(spec["stack"], str):
                    raise _err(f"{key}.stack", "must be a string", source)
        scale = ttype.get("scale")
        if scale is not None:
            if not isinstance(scale, dict):
                raise _err("type.scale", "must be a table of scale steps", source)
            for step, value in scale.items():
                if not _is_number(value) or value <= 0:
                    raise _err(f"type.scale.{step}", "must be a positive number", source)
        if "base" in ttype and not (_is_number(ttype["base"]) and ttype["base"] > 0):
            raise _err("type.base", "must be a positive number (px)", source)

    chart = data.get("chart")
    if chart is not None:
        if not isinstance(chart, dict) or set(chart) - {"palette"}:
            raise _err("chart", "must be a table with only the key 'palette'", source)
        palette = chart.get("palette")
        if palette is not None:
            if not isinstance(palette, dict) or set(palette) - {"categorical", "sequential"}:
                raise _err("chart.palette", "must be a table with keys categorical, sequential", source)
            for kind, list_key, minimum in (
                ("categorical", "colours", 2),
                ("sequential", "stops", 2),
            ):
                section = palette.get(kind)
                if section is None:
                    continue
                key = f"chart.palette.{kind}"
                if not isinstance(section, dict) or set(section) - {list_key}:
                    raise _err(key, f"must be a table with only the key '{list_key}'", source)
                values = section.get(list_key)
                if not isinstance(section, dict) or list_key not in section:
                    raise _err(f"{key}.{list_key}", "required for chart.palette.%s" % kind, source)
                if not isinstance(values, list) or len(values) < minimum:
                    raise _err(f"{key}.{list_key}", f"must be a list of at least {minimum} colours", source)
                for i, c in enumerate(values):
                    try:
                        parse_hex(c)
                    except ValueError as exc:
                        raise _err(f"{key}.{list_key}[{i}]", str(exc), source) from None

    encoding = data.get("encoding")
    if encoding is not None:
        if not isinstance(encoding, dict) or set(encoding) - {"check"}:
            raise _err("encoding", "must be a table with only the key 'check'", source)
        check = encoding.get("check")
        if check is not None:
            if not isinstance(check, dict) or set(check) - {"palette_min_de00"}:
                raise _err("encoding.check", "must be a table with only the key 'palette_min_de00'", source)
            if "palette_min_de00" in check and not (
                _is_number(check["palette_min_de00"]) and check["palette_min_de00"] > 0
            ):
                raise _err("encoding.check.palette_min_de00", "must be a positive number", source)


def load_theme_file(path: Path) -> dict[str, object]:
    """Read, validate, and return a theme token table. Raises ThemeSchemaError."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ThemeSchemaError("<file>", f"cannot be read: {exc}", str(path)) from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ThemeSchemaError("<file>", f"not valid TOML: {exc}", str(path)) from None
    validate_theme_data(data, str(path))
    return data


def validate_merged_tokens(tokens: dict[str, object]) -> None:
    """Cross-step checks a single file cannot see: every `on` target must be
    a role that exists after resolution."""
    colour = tokens.get("colour", {})
    roles = colour.get("roles", {}) if isinstance(colour, dict) else {}
    known = {name for name, _ in _iter_roles(roles)}
    for name, role in _iter_roles(roles):
        for target in role.get("on", []):
            if target not in known:
                raise ThemeSchemaError(
                    f"colour.roles.{name}.on",
                    f"references undeclared role {target!r} (no step supplies it)",
                    "resolved theme",
                )


# --------------------------------------------------------------------------
# Resolution (ADR 0005, four steps)
# --------------------------------------------------------------------------

def _flatten(tokens: dict[str, object], prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in tokens.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        else:
            out[path] = value
    return out


def _unflatten(flat: dict[str, object]) -> dict[str, object]:
    root: dict[str, object] = {}
    for path, value in flat.items():
        parts = path.split(".")
        node = root
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
    return root


def _reference_is_path(ref: str) -> bool:
    return "/" in ref or ref.endswith(THEME_SUFFIX)


def _bundled_default_tokens() -> dict[str, object]:
    path = BUNDLED_THEMES_DIR / f"{BUNDLED_DEFAULT_NAME}{THEME_SUFFIX}"
    return load_theme_file(path)


def _step1_source(config: object | None) -> tuple[str, dict[str, object]]:
    """Resolution step 1: the project config's theme reference.

    A Mapping is an inline token table (authored directly in visuals.toml);
    a string containing '/' or ending '.toml' is a path relative to the
    project root. Both are step 1 when they exist. Returns ("", {}) when
    step 1 does not apply or does not exist.
    """
    if config is None:
        return "", {}
    ref = getattr(config, "theme", None)
    if ref is None:
        return "", {}
    from collections.abc import Mapping as _Mapping

    if isinstance(ref, _Mapping):
        validate_theme_data(dict(ref), "visuals.toml [theme] inline table")
        return STEP_PROJECT_INLINE, dict(ref)
    if isinstance(ref, str) and ref.strip() and _reference_is_path(ref):
        root = Path(getattr(config, "root", "."))
        path = Path(ref)
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            return STEP_PROJECT_INLINE, load_theme_file(path)
    return "", {}


def _named_source(step: str, path: Path) -> tuple[str, dict[str, object]]:
    if path.is_file():
        return step, load_theme_file(path)
    return "", {}


def resolve_theme(name: str, config: "ResolvedConfig | None") -> ResolvedTheme:
    """Four-step theme resolution per ADR 0005. Falls back to the bundled
    neutral default for any token the higher steps do not declare.

    ``config`` is task 0003's ResolvedConfig (or None when the working
    directory is not inside an adopted project). Its ``theme`` attribute is
    a str (a name, or a path relative to ``root``) or a Mapping (an inline
    token table — resolution step 1).

    Raises ThemeUnavailable when the named theme is found nowhere (message
    names all four locations); ThemeSchemaError when a found theme is
    invalid, with the key named.
    """
    name = (name or "").strip()
    theme_ref = getattr(config, "theme", None) if config is not None else None
    root = Path(getattr(config, "root", ".")) if config is not None else None

    step1_step, step1_data = _step1_source(config)
    if not step1_step and isinstance(theme_ref, str) and theme_ref.strip() and _reference_is_path(theme_ref.strip()):
        # An explicit path in the config was authoritative and does not exist:
        # it is one of the four searched locations for criterion 2 reporting.
        raise ThemeUnavailable(_searched_locations(name, config, theme_ref))

    # The named lookup (steps 2-4) uses the explicit theme name. When the
    # project supplies an inline table (step 1), that table IS the theme.
    lookup_name = name or BUNDLED_DEFAULT_NAME
    if step1_step:
        overlay_step, overlay = step1_step, step1_data
    else:
        overlay_step, overlay = "", {}
        candidates: tuple[tuple[str, Path], ...] = ()
        if root is not None:
            candidates += ((STEP_PROJECT_DIR, root / PROJECT_THEMES_DIRNAME / f"{lookup_name}{THEME_SUFFIX}"),)
        candidates += (
            (STEP_USER_REGISTRY, user_themes_dir() / f"{lookup_name}{THEME_SUFFIX}"),
            (STEP_BUNDLED, BUNDLED_THEMES_DIR / f"{lookup_name}{THEME_SUFFIX}"),
        )
        for step, path in candidates:
            overlay_step, overlay = _named_source(step, path)
            if overlay_step:
                break
        if not overlay_step:
            raise ThemeUnavailable(_searched_locations(name, config, theme_ref))

    # The bundled neutral default is the value-level fallback for every token
    # the higher steps leave undeclared (ADR 0005: it is step 4 of the order).
    base = load_theme_file(BUNDLED_THEMES_DIR / f"{BUNDLED_DEFAULT_NAME}{THEME_SUFFIX}")

    sources = ((STEP_BUNDLED, base), (overlay_step, overlay)) if overlay_step else ((STEP_BUNDLED, base),)
    flat: dict[str, object] = {}
    steps: dict[str, str] = {}
    for step, table in sources:
        for key, value in _flatten(table).items():
            flat[key] = value
            steps[key] = step
    tokens = _unflatten(flat)
    validate_merged_tokens(tokens)
    steps_consulted = tuple(s for s in STEPS if s in set(steps.values()))
    return ResolvedTheme(
        name=name or BUNDLED_DEFAULT_NAME,
        tokens=tokens,
        resolution_steps=steps,
        steps_consulted=steps_consulted,
    )


def _searched_locations(name: str, config: object, theme_ref: object) -> tuple[str, ...]:
    """The four ADR 0005 locations, concrete, for ThemeUnavailable reporting."""
    name = name or BUNDLED_DEFAULT_NAME
    root = Path(getattr(config, "root", ".")) if config is not None else None
    if isinstance(theme_ref, str) and theme_ref.strip():
        step1 = f"project config theme reference: {theme_ref!r} (explicit path or inline table)"
    elif theme_ref is not None:
        step1 = "project config theme reference: inline table (itself the theme)"
    elif config is not None:
        step1 = f"project config theme reference: {name!r} (no explicit path or inline table)"
    else:
        step1 = "no adopted project (no visuals.toml found walking up) — no step-1 reference"
    step2 = f"project theme directory: {root / PROJECT_THEMES_DIRNAME / (name + THEME_SUFFIX)}" if root else "project theme directory: none (no adopted project)"
    step3 = f"user registry: {user_themes_dir() / (name + THEME_SUFFIX)}"
    step4 = f"bundled default: {BUNDLED_THEMES_DIR / (name + THEME_SUFFIX)}"
    return (step1, step2, step3, step4)


# --------------------------------------------------------------------------
# Derived artifacts — generated from the token source, never restated (F7)
# --------------------------------------------------------------------------

def _css_property(path: str) -> str | None:
    """Token path -> CSS custom property name; None = not a CSS token."""
    if path.startswith("colour.roles.") and path.endswith(".hex"):
        return "--colour-" + path[len("colour.roles.") : -len(".hex")].replace(".", "-")
    if path.startswith("type.families.") and path.endswith(".stack"):
        return "--font-" + path[len("type.families.") : -len(".stack")]
    if path.startswith("type.scale."):
        return "--type-" + path[len("type.scale.") :]
    if path == "type.base":
        return "--type-base"
    return None  # chart palettes and encoding defaults are not stylesheet tokens


def emit_css(tokens: dict[str, object]) -> str:
    """A CSS custom-property block derived from the token source (F7: the
    stylesheet never restates a value the theme file already carries)."""
    lines = [
        "/* generated from the visuals theme token file — edit the tokens, not this block */",
        ":root {",
    ]
    for path, value in sorted(_flatten(tokens).items()):
        prop = _css_property(path)
        if prop is None:
            continue
        if path == "type.base":
            rendered = f"{value}px"
        elif path.startswith("type.scale."):
            rendered = f"{value}rem"
        else:
            rendered = str(value)
        lines.append(f"  {prop}: {rendered};")
    lines.append("}")
    return "\n".join(lines)


def emit_palette(tokens: dict[str, object]) -> dict[str, object]:
    """The machine-readable palette derived from the token source."""
    colour = tokens.get("colour", {})
    roles = colour.get("roles", {}) if isinstance(colour, dict) else {}
    chart = tokens.get("chart", {})
    palette = chart.get("palette", {}) if isinstance(chart, dict) else {}
    return {
        "roles": {name: role.get("hex") for name, role in _iter_roles(roles) if "hex" in role},
        "chart": {
            "categorical": list(palette.get("categorical", {}).get("colours", [])),
            "sequential": list(palette.get("sequential", {}).get("stops", [])),
        },
    }


# --------------------------------------------------------------------------
# Palette validation — advisory findings, never blocking (ADR 0004)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    """One advisory validation finding. ``passed`` is None when no threshold
    is declared and the value is reported informationally only."""

    check: str  # "distance" | "contrast"
    subject: str
    value: float
    threshold: float | None
    passed: bool | None


def validate_tokens(tokens: dict[str, object]) -> tuple[Finding, ...]:
    """Adjacent-pair perceptual distance (CIEDE2000) for the categorical chart
    palette, and WCAG contrast for every declared foreground/background pair.
    Thresholds: WCAG 2.2 SC 1.4.3 (4.5:1) and SC 1.4.11 (3:1); the distance
    minimum is the theme's own declared ``encoding.check.palette_min_de00`` —
    when a theme declares none, distances are reported without a verdict,
    because no primary source prescribes one (public/references/SOURCES.md)."""
    findings: list[Finding] = []

    chart = tokens.get("chart", {})
    palette = chart.get("palette", {}) if isinstance(chart, dict) else {}
    categorical = palette.get("categorical", {})
    colours = categorical.get("colours", []) if isinstance(categorical, dict) else []
    check = tokens.get("encoding", {})
    check = check.get("check", {}) if isinstance(check, dict) else {}
    threshold = check.get("palette_min_de00")
    threshold = float(threshold) if _is_number(threshold) else None
    for i in range(len(colours) - 1):
        value = ciede2000(srgb_to_lab(str(colours[i])), srgb_to_lab(str(colours[i + 1])))
        findings.append(
            Finding(
                check="distance",
                subject=f"categorical[{i}]-categorical[{i + 1}]",
                value=value,
                threshold=threshold,
                passed=None if threshold is None else value >= threshold,
            )
        )

    colour = tokens.get("colour", {})
    roles = colour.get("roles", {}) if isinstance(colour, dict) else {}
    flat_roles = dict(_iter_roles(roles))
    for role_name, role in flat_roles.items():
        if not role.get("on"):
            continue
        fg = role.get("hex")
        if fg is None:
            continue  # a role that only declares metadata falls back; nothing to check
        minimum = CONTRAST_TEXT_MIN if role.get("kind", "non-text") == "text" else CONTRAST_NON_TEXT_MIN
        for bg_name in role["on"]:
            bg_role = flat_roles.get(bg_name, {})
            bg = bg_role.get("hex") if isinstance(bg_role, dict) else None
            if bg is None:
                continue
            ratio = contrast_ratio(fg, bg)
            findings.append(
                Finding(
                    check="contrast",
                    subject=f"{role_name} on {bg_name}",
                    value=ratio,
                    threshold=minimum,
                    passed=ratio >= minimum,
                )
            )
    return tuple(findings)