#!/usr/bin/env python3
"""se_gate_shared — the ONE source for the software-engineering gate dialects.

Task 0118. Three hook dialects need the same notion of "code/build file":

* ``se-consult-gate.sh`` — the blocking PreToolUse consult gate (Claude Code / Codex);
* ``se-lifecycle-hook.sh`` — the warn/record-only lifecycle reminder hook;
* the OpenCode plugin templates rendered by ``harness/hooks.py`` (the plugin cannot import
  this module at runtime, so the template embeds regex sources RENDERED from it).

The shell dialects invoke this file directly (``python3 se_gate_shared.py gate|lifecycle``),
so the classification lives in exactly one place; ``harness/hooks.py`` imports
``scripts.se_gate_shared`` to render the TypeScript regexes. The dev test
``tests/hooks/test_gate_shared_source.py`` fails on any drift between the renderings.

Consultation detection (gate): REAL consultation only, from structured transcript entries —
a ``tool_use`` of the Skill tool whose skill input is ``software-engineering``, or a Bash-like
``tool_use`` whose command invokes the engineering CLI (the bundled ``engineering.py`` or the
``engineering`` PATH launcher). Prose, tool_result text and hook block messages never count —
the 0.12 gate satisfied itself with its own block REASON. A consultation counts in the
subagent's own session and in the parent session (Claude Code keeps subagent transcripts under
``<session-dir>/subagents/*.jsonl`` next to the parent transcript).

Every entry point is FAIL-OPEN: any error — unparseable stdin, absent or unreadable transcript,
internal crash — degrades to allow/silent. The only "block" verdict is the positive
"code/build file AND not consulted" decision.

Standard library only: this module ships in ``public/scripts`` and runs bare under ``python3``
(no PEP 723 runtime), keeping the hooks fast and dependency-free.

CLI: se_gate_shared.py gate        # consult gate: hook JSON on stdin → prints allow|block
     se_gate_shared.py lifecycle   # lifecycle hook: hook JSON on stdin → prints 6 field lines
     se_gate_shared.py classify P  # manual: prints code|not-code
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

SKILL_NAME = "software-engineering"

# A Bash-like tool_use counts as consultation when its command invokes the engineering CLI: the
# bundled script (…/engineering.py …) or the `engineering` PATH launcher (engineering …). The
# whitespace lookahead keeps plain words like `engineering.yaml` from matching; residual
# false positives (e.g. `echo engineering`) fail OPEN (allow) — the safe direction for this gate.
_ENGINEERING_COMMAND = re.compile(r"\bengineering(?:\.py)?(?=$|\s)")

# Prose docs are NEVER gated — even when named like build files (x.dockerfile.md).
PROSE_SUFFIXES: tuple[str, ...] = (".md", ".txt", ".rst")

# Code suffixes, matched case-INSENSITIVELY (0.12 was case-sensitive: A.PY and .R passed).
# .ipynb and .tf are newly covered by task 0118.
CODE_SUFFIXES: tuple[str, ...] = (
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".vue",
    ".svelte",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".hpp",
    ".cxx",
    ".java",
    ".kt",
    ".scala",
    ".rb",
    ".php",
    ".swift",
    ".m",
    ".mm",
    ".lua",
    ".pl",
    ".pm",
    ".r",
    ".jl",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".sql",
    ".gradle",
    ".cs",
    ".fs",
    ".ex",
    ".exs",
    ".erl",
    ".clj",
    ".dart",
    ".hs",
    ".ipynb",
    ".tf",
)

# Build files identified by (base)name rather than suffix, matched case-insensitively.
SPECIAL_BASENAMES: tuple[str, ...] = (
    "makefile",
    "pyproject.toml",
    "cargo.toml",
    "go.mod",
    "package.json",
    "cmakelists.txt",
)
HIDDEN_BASENAMES: tuple[str, ...] = (".gitlab-ci.yml",)
DOCKERFILE_PREFIX = "dockerfile"  # dockerfile, dockerfile.dev, Dockerfile.prod …
MK_SUFFIX = ".mk"
WORKFLOW_DIR = ".github/workflows"  # CI YAML only — not every .yml
WORKFLOW_SUFFIXES: tuple[str, ...] = (".yml", ".yaml")

_UNSAFE_SESSION_ID = re.compile(r"[^A-Za-z0-9._-]")
_TOOL_USE_MARKER = '"tool_use"'  # cheap per-line prefilter; only structured calls can count


# --------------------------------------------------------------------------- classification


def is_code_file(path: str, extra_globs: str = "") -> bool:
    """True when ``path`` is a code/build file the gate dialects must treat as gated.

    ``extra_globs`` is the SE_GATE_EXTS knob: space-separated extra globs, matched
    case-insensitively against the whole path. Evaluation order (mirrored by the OpenCode
    template): exact build-file NAMES beat the prose exclusion (``CMakeLists.txt`` is a build
    file despite its ``.txt`` suffix); otherwise prose docs are never gated; then code suffixes
    and the loose build patterns (dockerfile*, *.mk, CI workflow YAML) apply.
    """
    raw = str(path or "").strip()
    if not raw:
        return False
    low = raw.lower()
    directory, base = low.rsplit("/", 1) if "/" in low else ("", low)
    if base in SPECIAL_BASENAMES or base in HIDDEN_BASENAMES:
        return True  # exact build-file names beat the prose exclusion (CMakeLists.txt)
    if low.endswith(PROSE_SUFFIXES):
        return False  # prose docs are never gated, even when named like build files
    if low.endswith(CODE_SUFFIXES):
        return True
    if base == DOCKERFILE_PREFIX or base.startswith(DOCKERFILE_PREFIX + "."):
        return True
    if len(base) > len(MK_SUFFIX) and base.endswith(MK_SUFFIX):
        return True
    if (
        (directory == WORKFLOW_DIR or directory.endswith("/" + WORKFLOW_DIR))
        and base.endswith(WORKFLOW_SUFFIXES)
        and base not in WORKFLOW_SUFFIXES
    ):
        return True
    for glob in str(extra_globs or "").split():
        if glob and fnmatch.fnmatchcase(low, glob.lower()):
            return True
    return False


def sanitize_session_id(session_id: str) -> str:
    """A session id used as a filename must never carry separators or traversal."""
    safe = _UNSAFE_SESSION_ID.sub("_", str(session_id or ""))
    return "nosid" if safe in ("", ".", "..") else safe


# ----------------------------------------------------------- OpenCode template rendering


def _ts_literal(text: str) -> str:
    """Escape a literal for a JavaScript regex source (dots; slashes are escaped once, at the
    assembled-source level, by ``_ts_source`` — no ``\\-``-style identity escapes, which strict
    JS unicode mode rejects)."""
    return text.replace(".", r"\.")


def _ts_source(text: str) -> str:
    """Final JS regex-source escaping: a raw ``/`` would terminate a ``/…/`` literal in JS."""
    return text.replace("/", r"\/")


def ts_code_regexes() -> tuple[str, str, str, str]:
    """(prose, suffix, names, special) regex sources for the OpenCode plugin template.

    The template embeds these verbatim as ``/…/i`` literals with the SAME evaluation order as
    ``is_code_file``: ``names`` (exact build-file names) OR (NOT ``prose`` AND (``suffix`` OR
    ``special``)). The sources must stay JavaScript-compatible (no Python-only constructs);
    ``tests/hooks/test_gate_shared_source.py`` pins the rendering against ``is_code_file`` so
    the TS dialect cannot drift.
    """
    prose = r"\.(?:" + "|".join(_ts_literal(s[1:]) for s in PROSE_SUFFIXES) + r")$"
    suffix = r"\.(?:" + "|".join(_ts_literal(s[1:]) for s in CODE_SUFFIXES) + r")$"
    names = (
        "(?:^|/)(?:"
        + "|".join(_ts_literal(n) for n in (*SPECIAL_BASENAMES, *HIDDEN_BASENAMES))
        + r")$"
    )
    alternatives = [
        rf"(?:^|/){DOCKERFILE_PREFIX}(?:\.[^/]*)?",
        rf"[^/]+{_ts_literal(MK_SUFFIX)}",
    ]
    workflow_suffixes = "|".join(_ts_literal(s[1:]) for s in WORKFLOW_SUFFIXES)
    alternatives.append(rf"(?:^|/){_ts_literal(WORKFLOW_DIR)}/[^/]+\.(?:{workflow_suffixes})$")
    special = "(?:" + "|".join(alternatives) + ")$"
    return prose, suffix, _ts_source(names), _ts_source(special)


# ------------------------------------------------------------------ consultation detection


def _tool_use_items(record: object):
    """Yield the structured content items of one transcript line.

    Claude Code nests tool_use items under ``message.content``; a bare top-level ``content``
    list is tolerated so hand-written fixtures and other harness shapes stay valid.
    """
    if not isinstance(record, dict):
        return
    for holder in (record.get("message"), record):
        if not isinstance(holder, dict):
            continue
        content = holder.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    yield item


def _tool_use_shows_consultation(item: dict) -> bool:
    if item.get("type") != "tool_use":
        return False
    name = str(item.get("name") or "").strip().lower()
    tool_input = item.get("input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if name == "skill":
        skill = str(tool_input.get("skill") or tool_input.get("name") or "").strip().lower()
        return skill == SKILL_NAME
    if name in ("bash", "shell", "run_command"):
        command = str(tool_input.get("command") or tool_input.get("cmd") or "")
        return bool(_ENGINEERING_COMMAND.search(command))
    return False


def _scan_transcript(path: str) -> bool | None:
    """True = consultation found · False = readable, none found · None = unreadable.

    ``None`` is an ERROR the gate treats as fail-open (allow) — an unreadable transcript is
    never proof of "not consulted". Malformed lines are skipped, never fatal.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if _TOOL_USE_MARKER not in line:
                    continue  # cheap prefilter: only structured tool calls can count
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                for item in _tool_use_items(record):
                    if _tool_use_shows_consultation(item):
                        return True
    except OSError:
        return None
    return False


def _expand_transcripts(transcript_path: str) -> list[str]:
    """The transcript itself plus the sibling transcripts that share its session.

    Claude Code layout (verified on disk under ``~/.claude/projects``): the parent session
    transcript is ``<project>/<session>.jsonl`` and its subagent transcripts live under
    ``<project>/<session>/subagents/*.jsonl``. So a subagent transcript must also scan the
    parent session transcript, and a session transcript must also scan its subagents.
    """
    if not transcript_path:
        return []
    main = Path(transcript_path)
    roots = [str(main)]
    parent = main.parent
    if parent.name == "subagents":
        session_dir = parent.parent
        if session_dir.name:
            roots.append(str(session_dir.parent / (session_dir.name + ".jsonl")))
    else:
        subagents = parent / main.stem / "subagents"
        if subagents.is_dir():
            roots.extend(str(candidate) for candidate in sorted(subagents.glob("*.jsonl")))
    return roots


# ------------------------------------------------------------------------- the gate decision


def _cache_dir(environ: dict[str, str] | os._Environ[str]) -> Path:
    base = str(environ.get("XDG_CACHE_HOME") or "").strip() or str(Path.home() / ".cache")
    # v2: markers written by the 0.12 substring detector (which its own block message could
    # satisfy) live one level up and are deliberately not trusted.
    return Path(base) / "se-consult-gate" / "v2"


def gate(stdin_text: str, environ: dict[str, str] | os._Environ[str] | None = None) -> str:
    """The consult-gate decision: ``block`` only for a code/build file with no consultation."""
    environ = os.environ if environ is None else environ
    try:
        payload = json.loads(stdin_text)
    except ValueError:
        return "allow"  # fail-open
    if not isinstance(payload, dict):
        return "allow"
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        fallback = payload.get("input")
        tool_input = fallback if isinstance(fallback, dict) else {}
    file_path = str(tool_input.get("file_path") or tool_input.get("path") or "")
    session_id = str(payload.get("session_id") or "")
    transcript_path = str(payload.get("transcript_path") or "")

    cache = _cache_dir(environ)
    marker = cache / (sanitize_session_id(session_id) + ".ok")
    try:
        if marker.is_file():
            return "allow"  # fast path: already consulted this session
    except OSError:
        pass

    if not is_code_file(file_path, str(environ.get("SE_GATE_EXTS") or "")):
        return "allow"
    if not transcript_path:
        return "allow"  # no transcript to consult → error → fail-open

    main = _scan_transcript(transcript_path)
    if main is None:
        return "allow"  # unreadable transcript is an error, not proof of "not consulted"
    consulted = main is True
    if not consulted:
        for extra in _expand_transcripts(transcript_path)[1:]:
            found = _scan_transcript(extra)
            if found is None:
                return "allow"  # unreadable related transcript is an error → fail-open
            if found:
                consulted = True
                break
    if consulted:
        try:
            cache.mkdir(parents=True, exist_ok=True)
            marker.touch()
        except OSError:
            pass  # the marker is an optimisation, never a blocker
        return "allow"
    return "block"


def lifecycle(stdin_text: str) -> list[str]:
    """Fields the lifecycle hook needs, one per line: event, tool, file, session, cwd, code.

    ``code`` is 1|0 per ``is_code_file`` (the shared class source). An EMPTY list means
    "unparseable input"; the hook then stays silent (it never blocks and never spams).
    """
    try:
        payload = json.loads(stdin_text)
    except ValueError:
        return []
    if not isinstance(payload, dict):
        return []
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    file_path = str(tool_input.get("file_path") or tool_input.get("path") or "")
    return [
        str(payload.get("hook_event_name") or payload.get("hookEventName") or ""),
        str(payload.get("tool_name") or ""),
        file_path,
        str(payload.get("session_id") or ""),
        str(payload.get("cwd") or tool_input.get("cwd") or ""),
        "1" if is_code_file(file_path) else "0",
    ]


def classify(path: str) -> str:
    return "code" if is_code_file(path) else "not-code"


# -------------------------------------------------------------------------------------- CLI


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    if mode == "gate":
        print(gate(sys.stdin.read()))
        return 0
    if mode == "lifecycle":
        for line in lifecycle(sys.stdin.read()):
            print(line)
        return 0
    if mode == "classify":
        print(classify(argv[2] if len(argv) > 2 else ""))
        return 0
    print("usage: se_gate_shared.py gate|lifecycle|classify [PATH]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        sys.exit(main(sys.argv))
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — fail-open: a crash must never block an edit
        if mode == "gate":
            print("allow")
        sys.exit(0)
