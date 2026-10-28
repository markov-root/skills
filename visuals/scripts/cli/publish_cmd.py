"""Explicit promotion of a reviewed immutable version to latest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="visuals publish", add_help=False)
    parser.add_argument("slug")
    parser.add_argument("version")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code or 2

    import config
    import probe
    import store

    try:
        resolved = config.resolve_config(Path.cwd())
        if resolved is None:
            print("visuals publish: unavailable: no adopted project", file=sys.stderr)
            return 3
        visual = probe.resolve_visual(resolved.root, args.slug)
        store.publish_version(visual, args.version)
    except (config.ConfigError, probe.ProbeUnavailable, store.StoreError) as exc:
        print(f"visuals publish: error: {exc}", file=sys.stderr)
        return 1
    print(f"published {args.slug}: latest -> {args.version}")
    return 0
