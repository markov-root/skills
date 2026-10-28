"""Read a visual's optional style declaration from its existing BRIEF.md.

Only an unadorned ``style: <name>`` line is a declaration. Names resolve
against the adopted project's ``visuals.toml``; there is no search or default.
"""

from __future__ import annotations

import re
from pathlib import Path


def declared_style(visual_dir: Path) -> tuple[str | None, str | None]:
    """Return (style name, metadata error). A missing line means unstyled.

    This public accessor is shared by validate and index, and can be used by
    future commands without duplicating the BRIEF parsing rule.
    """
    path = visual_dir / "BRIEF.md"
    if not path.is_file():
        return None, None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return None, f"cannot read BRIEF.md ({exc})"
    declarations = [line.split(":", 1)[1].strip() for line in lines
                    if re.match(r"^style\s*:", line)]
    if not declarations:
        return None, None
    if len(declarations) != 1:
        return None, "BRIEF.md has more than one style: line"
    name = declarations[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        return None, "BRIEF.md style must be one nonempty bare name"
    return name, None
