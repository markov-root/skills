#!/usr/bin/env python3
"""Select a preprovisioned uv script environment for the engineering launcher.

Task 0102 fallback helper. Invoked by the ``engineering`` launcher with plain
``python3`` when uv fails because the shared cache is unwritable. It only READS
the uv cache: it scans ``$UV_CACHE_DIR`` (default ``~/.cache/uv``) under
``environments-v2/engineering-*`` and prints the newest environment whose
installed package versions exactly match the pins in the adjacent
``engineering.py.lock``. Nothing is written and nothing is installed.

stdlib only (requires python3 >= 3.11 for tomllib). Output contract: on a
match, print the environment's python executable path on stdout and exit 0;
on no match, print nothing and exit 1.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

ENGINEERING_PREFIX = "engineering-"


def _canonical(name: str) -> str:
    """PEP 503 normalization so lock and dist-info names compare equal."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _required_release(specifier: str) -> tuple[int, ...] | None:
    """Extract the release tuple a requires-python specifier pins.

    Supports the equality forms uv writes for script locks (``==3.12.*`` and
    ``==3.12.3``). Any other form, including ``>=``/``<`` bounds, yields None,
    which the caller treats as "cannot verify" -> the environment is not
    eligible (conservative; bounds were previously compared as equality).
    """
    text = specifier.strip()
    for operator in ("==",):
        if text.startswith(operator):
            operand = text[len(operator) :].strip()
            operand = operand.removesuffix(".*")
            parts = operand.split(".")
            if parts and all(part.isdigit() for part in parts):
                return tuple(int(part) for part in parts)
            return None
    return None


def _python_matches(specifier: str, version_info: str) -> bool:
    """Check a pyvenv.cfg version_info against the lock's requires-python.

    The comparison uses only the release components the specifier constrains;
    a trailing ``.*`` wildcard requires the same major.minor, a full ``==X.Y.Z``
    requires the full release. Patch-level claims beyond the specifier length
    are ignored, which cannot over-match for ``==X.Y.*``.
    """
    release = _required_release(specifier)
    if release is None:
        return False
    env_parts = []
    for part in version_info.strip().split("."):
        if not part.isdigit():
            break
        env_parts.append(int(part))
    if len(env_parts) < len(release):
        return False
    return tuple(env_parts[: len(release)]) == release


def _pyvenv_version(env: Path) -> str | None:
    try:
        text = (env / "pyvenv.cfg").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "version_info":
            return value.strip()
    return None


def _site_packages(env: Path) -> Path | None:
    candidates = sorted((env / "lib").glob("python3.*/site-packages"))
    return candidates[0] if candidates else None


def _env_python(env: Path) -> Path | None:
    for name in ("python", "python3"):
        candidate = env / "bin" / name
        if candidate.is_file():
            return candidate
    return None


def _locked_packages(lock: Path) -> dict[str, str]:
    try:
        data = tomllib.loads(lock.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    packages = {}
    for package in data.get("package", []):
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str) and isinstance(version, str):
            packages[_canonical(name)] = version
    return packages


def _installed_versions(site_packages: Path) -> dict[str, str]:
    versions = {}
    for dist_info in site_packages.glob("*.dist-info"):
        stem = dist_info.name[: -len(".dist-info")]
        name, _, version = stem.rpartition("-")
        if name and version:
            versions[_canonical(name)] = version
    return versions


def _mtime_key(env: Path) -> float:
    cfg = env / "pyvenv.cfg"
    try:
        return max(env.stat().st_mtime, cfg.stat().st_mtime)
    except OSError:
        return env.stat().st_mtime


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: engineering-env-match.py <engineering.py.lock>", file=sys.stderr)
        return 2
    lock = Path(argv[1])
    locked = _locked_packages(lock)
    if not locked:
        return 1
    specifier = ""
    try:
        specifier = tomllib.loads(lock.read_text(encoding="utf-8")).get("requires-python", "")
    except (OSError, tomllib.TOMLDecodeError):
        return 1

    cache_dir = os.environ.get("UV_CACHE_DIR")
    if cache_dir:
        cache = Path(cache_dir)
    else:
        cache = Path.home() / ".cache" / "uv"
    environments = cache / "environments-v2"

    candidates: list[tuple[float, Path]] = []
    for env in sorted(environments.glob(f"{ENGINEERING_PREFIX}*")):
        if not env.is_dir():
            continue
        version_info = _pyvenv_version(env)
        if version_info is None or not _python_matches(specifier, version_info):
            continue
        site_packages = _site_packages(env)
        if site_packages is None:
            continue
        installed = _installed_versions(site_packages)
        if any(installed.get(name) != version for name, version in locked.items()):
            continue
        env_python = _env_python(env)
        if env_python is None:
            continue
        candidates.append((_mtime_key(env), env_python))

    if not candidates:
        return 1
    candidates.sort(key=lambda item: (item[0], item[1]))
    print(candidates[-1][1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
