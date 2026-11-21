"""Loading the standard's file formats. YAML dates stay strings (schemas expect ISO strings)."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import yaml


class _StringDateLoader(yaml.SafeLoader):
    """SafeLoader without the implicit timestamp resolver: `2026-12-03` stays a string."""


_StringDateLoader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def loads_yaml(text: str) -> Any:
    return yaml.load(text, Loader=_StringDateLoader)  # noqa: S506 — SafeLoader subclass


def load(path: Path) -> Any:
    """Load YAML, TOML or JSON by suffix."""
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return loads_yaml(text)
    if suffix == ".toml":
        return tomllib.loads(text)
    if suffix == ".json":
        return json.loads(text)
    raise ValueError(f"unsupported format: {path.name}")
