"""`present schema list|check` — validate one standard file against its schema."""
from __future__ import annotations

from pathlib import Path

from .. import formats, schemas
from ..console import Effects, Result, leaf

# Filename → schema. Delivery records are recognised by their parent directory.
BY_NAME = {"presentations.toml": "presentations", "talk.yaml": "talk", "script.yaml": "script",
           "deck.yaml": "deck", "receipt.json": "receipt", "approvals.yaml": "approvals",
           "annotations.yaml": "annotations", "slides.yaml": "slides", "tokens.json": "tokens",
           "library-slide.yaml": "library-item", "library-visual.yaml": "library-item"}


def infer(path: Path) -> str | None:
    if path.name in BY_NAME:
        return BY_NAME[path.name]
    if path.parent.name == "delivery" and path.suffix in (".yaml", ".yml"):
        return "delivery"
    return None


@leaf("schema", "list", summary="list the standard's schemas and the files they describe",
      effects=Effects(description="Reads only the bundled schemas."), task="0002")
def schema_list(ns, res: Result) -> Result:
    res.data = {"schemas": [{"name": n, "files": [f for f, s in BY_NAME.items() if s == n] or
                             (["delivery/<date>.yaml"] if n == "delivery" else [])} for n in schemas.NAMES]}
    res.text += [f"{s['name']:<14} {', '.join(s['files'])}" for s in res.data["schemas"]]
    return res


def _configure(p):
    p.add_argument("path", type=Path, help="file to validate")
    p.add_argument("--schema", choices=schemas.NAMES, help="override the schema inferred from the filename")


@leaf("schema", "check", summary="validate one file against its schema (inferred from its name)",
      effects=Effects(description="Reads the given file only."), task="0002", configure=_configure)
def schema_check(ns, res: Result) -> Result:
    path: Path = ns.path
    name = ns.schema or infer(path)
    if name is None:
        return res.error("schema_unknown", f"cannot infer a schema for {path.name}", repairable=True,
                         next="present schema check <file> --schema <name>  (see present schema list)")
    if not path.is_file():
        return res.error("file_not_found", f"{path} does not exist", repairable=True)
    try:
        data = formats.load(path)
    except Exception as exc:
        return res.error("file_unparseable", f"{path}: {exc}", repairable=True)
    errs = schemas.errors(name, data)
    res.data = {"path": str(path), "schema": name, "valid": not errs, "errors": errs}
    if errs:
        res.text += [f"{path}: INVALID against {name}"] + [f"  {e}" for e in errs]
        return res.error("schema_invalid", f"{len(errs)} schema error(s) in {path.name}", repairable=True)
    res.text.append(f"{path}: valid ({name})")
    return res
