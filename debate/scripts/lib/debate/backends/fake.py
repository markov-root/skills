"""FakeDebater — offline test double (fake the seam you own)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeDebater:
    """Offline test double. `responses` maps a key (e.g. round name) to a JSON string."""

    id: str
    responses: dict[str, str]
    backend: str = "fake"
    calls: list[tuple[str, str]] = field(default_factory=list)

    def generate(self, system: str, user: str, *, want_json: bool = False) -> str:
        self.calls.append((system, user))
        # Return the response whose key appears in the system prompt; most specific first.
        for key in sorted(self.responses, key=len, reverse=True):
            if key.lower() in system.lower():
                return self.responses[key]
        return next(iter(self.responses.values()))
