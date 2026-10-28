#!/usr/bin/env python3
"""`visuals init` — adopt an existing tree by writing one visuals.toml.

Writes ONLY the config file, and only when adoption is possible:

- A visuals.toml already resolvable from the working directory → refuse,
  exit 2, name the file; nothing is written. Re-init is never a silent
  overwrite.
- An existing tree that looks like a visuals corpus (the reference corpus
  does) → a config describing discovered canvas profiles, contract paths,
  pre-render hooks, and any web root evidenced by absolute asset references.
  Missing contract paths are marked as replacements, never claimed as found.
  Nothing else in the tree is touched — task 0003 criterion 2's before/after
  checksum must be empty.
- An empty (or corpus-free) directory → the neutral scaffold: one profile,
  zero insets, no hooks, no advisory selection. Geometry and contract wiring
  only — no compositional opinion (ADR 0004).

The generated config is validated by writing it, then loading it back through
`config.load_config` before the file is reported as written — an init that
produces a config its own loader rejects is a defect, not a deliverable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # capability domain (task 0003); never a handler-to-handler import


def main(argv: list[str]) -> int:
    """Handler entry point. `argv` is this command's own arguments, without the
    program name or the command name — the dispatcher declares no flags for us
    (that would be a second command catalog), so we parse our own here."""
    parser = argparse.ArgumentParser(prog="visuals init", add_help=False)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a JSON report of what was (or was not) written",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2  # usage

    cwd = Path.cwd()
    existing = config.resolve_config(cwd)
    if existing is not None:
        message = (
            f"refusing to init: {cwd} is already inside an adopted project "
            f"({existing.path}); edit that file instead — init never overwrites"
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "command": "init",
                        "written": None,
                        "adopted": str(existing.path),
                        "mode": "refused",
                        "message": message,
                    },
                    indent=2,
                )
            )
        else:
            print(message, file=sys.stderr)
        return 2

    shape = config.discover_project_shape(cwd)
    body = _body_from_shape(shape)
    mode = "discovered" if shape else "scaffold"

    text = config.to_toml(body)
    target = cwd / config.CONFIG_NAME
    # Validate-before-commit: load the exact bytes back through the loader.
    import tempfile

    with tempfile.NamedTemporaryFile(
        "w", suffix=".toml", encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    try:
        config.load_config(tmp_path)
    except config.ConfigError as exc:
        tmp_path.unlink(missing_ok=True)
        print(
            f"error: init produced a config its own loader rejects — {exc}",
            file=sys.stderr,
        )
        return 1  # blocking: the tool would be shipping a broken contract
    tmp_path.unlink(missing_ok=True)

    target.write_text(text, encoding="utf-8")

    # Report against the real file, in place.
    written = config.load_config(target)
    profiles = {name: (p.width, p.height) for name, p in written.canvas_profiles.items()}
    hooks = [h.name for h in written.hooks]
    if args.json:
        print(
            json.dumps(
                {
                    "command": "init",
                    "written": str(target),
                    "mode": mode,
                    "schema_version": written.schema_version,
                    "default_profile": written.default_profile,
                    "canvas_profiles": profiles,
                    "theme": written.theme if isinstance(written.theme, str) else "<inline table>",
                    "paths": {
                        k: str(v.relative_to(written.root))
                        for k, v in written.registry_paths.items()
                    },
                    "paths_not_found": list(body.get("_undiscovered_paths", ())),
                    "web_root": body.get("web_root"),
                    "web_root_reference": body.get("web_root_reference"),
                    "hooks": hooks,
                    "advisory_checks": list(written.advisory_checks),
                    "message": f"wrote {target} ({mode}; nothing else in the tree was touched)",
                },
                indent=2,
            )
        )
    else:
        print(f"wrote {target} ({mode})")
        print(f"  canvas: default {written.default_profile} {profiles}")
        print(f"  theme: {written.theme if isinstance(written.theme, str) else '<inline table>'}")
        if body.get("web_root"):
            print(f"  web_root: {body['web_root']} (found via {body['web_root_reference']})")
        for key in shape["paths"] if shape else written.registry_paths:
            print(f"  paths.{key}: {written.registry_paths[key].relative_to(written.root)}")
        if body.get("_undiscovered_paths"):
            print("  contract paths not found — fill these in:")
            for key in body["_undiscovered_paths"]:
                print(f"    paths.{key}: {body['paths'][key]}")
        if hooks:
            print(f"  hooks: {', '.join(hooks)}")
        print(f"  advisory_checks: {list(written.advisory_checks) or '[] (none selected)'}")
        print("  nothing else in the tree was written or modified")
    return 0


def _body_from_shape(shape: dict | None) -> dict:
    """Merge discovered corpus evidence into a full config body.

    Keep the empty-directory scaffold intact. A discovered tree with missing
    contract paths gets explicit replacement markers instead of inherited
    scaffold values that could look like discovered facts.
    """
    body = config.scaffold_body()
    if not shape:
        return body
    canvas = body["canvas"]
    canvas["profiles"] = shape["profiles"]
    # Default profile: the full-slide canvas unless the tree says otherwise —
    # the corpus's most common wrapper geometry is the title-band, but the
    # full-slide profile is the one the shared renderer itself declares.
    canvas["default"] = (
        config.CORPUS_PROFILE_TITLE_BAND
        if config.CORPUS_PROFILE_TITLE_BAND in shape["profiles"]
        else next(iter(shape["profiles"]))
    )
    body["theme"] = shape["theme"]
    missing = tuple(key for key in body["paths"] if key not in shape["paths"])
    body["paths"] = {
        key: shape["paths"].get(key, f"REPLACE_WITH_{key.upper()}")
        for key in body["paths"]
    }
    body["_undiscovered_paths"] = missing
    if shape["web_root"]:
        body["web_root"], body["web_root_reference"] = shape["web_root"]
    body["hooks"] = shape["hooks"]
    return body


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
