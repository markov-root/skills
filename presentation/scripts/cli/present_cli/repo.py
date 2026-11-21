"""Find the consumer repository by walking up to presentations.toml — never by counting parents."""
from __future__ import annotations

from pathlib import Path

MARKER = "presentations.toml"


def find_repo(start: Path | None = None) -> Path | None:
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / MARKER).is_file():
            return candidate
    return None


def find_talks(repo: Path) -> list[Path]:
    """Talks are directories directly under the repository root that hold audience/talk.yaml."""
    return sorted(p for p in repo.iterdir() if (p / "audience" / "talk.yaml").is_file())
