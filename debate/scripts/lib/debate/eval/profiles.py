"""Baseline profiles for the harness (task-0026). A baseline is a DEGENERATE profile of the same
engine — measurement reuses the config the tool runs, it doesn't fork a separate code path.

The literature makes these baselines non-negotiable: a debate claim is uninterpretable without
`direct` and `consultancy` at an equal-call/equal-token budget (Michael 2023 / Kenton 2024 /
Khan 2024), because debate often LOSES to a strong single-model baseline. This ships the three
core profiles; the wider Cluster-3 set (CoT, self-consistency, direct+tools, Self-MoA) are added as
the live sweep needs them (`docs/research/2026-07-26-cluster3-synthesis.md`).

- `direct`      — the judge answers alone (no debate). `plan()` is None: it is NOT a debate plan
                  (it would violate the floor-always-runs invariant), so the live runner executes it
                  as a single propose+aggregate outside the plan loop (deferred to the sweep).
- `consultancy` — one voice + a judge, floor only, no adversary (the weak-oversight baseline).
- `steelman`    — the cross-vendor panel + dialectical adversary (the default plan).
"""

from __future__ import annotations

from dataclasses import dataclass

from debate.engine.plan import Plan, default_plan


@dataclass(frozen=True)
class Profile:
    name: str
    n_proposers: int
    has_adversary: bool
    description: str

    def plan(self) -> Plan | None:
        if self.name == "steelman":
            return default_plan(has_redteam=True)
        if self.name == "consultancy":
            return default_plan(
                has_redteam=False
            )  # floor only; the single voice is a panel constraint
        return None  # `direct`: a no-debate baseline, run outside the plan loop


PROFILES: dict[str, Profile] = {
    p.name: p
    for p in (
        Profile("direct", 1, False, "judge answers alone (propose→aggregate); no debate"),
        Profile("consultancy", 1, False, "one voice + judge; floor, no adversary"),
        Profile("steelman", 3, True, "cross-vendor panel + dialectical adversary (the default)"),
    )
}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown profile {name!r} — known: {', '.join(PROFILES)}") from None
