"""Rater dependence — the effective number of independent opinions (ADR-0013 decision 6).

Our panel (gpt / kimi / glm / claude) is not four independent witnesses: models from the same
vendor family or sharing a base model make *correlated* errors (a shared blind spot in the
training corpus depresses several at once). Averaging correlated raters as if independent
overstates confidence (Clemen & Winkler 1999). We report the **effective number of independent
raters**

    N_eff = N / (1 + (N - 1) * rho_bar)

as a per-indicator trust diagnostic, where `rho_bar` is the average pairwise error correlation
under a **block** structure: higher within a vendor family, lower across families.

The block-rho values here are a *documented structural prior*; empirical rho from seed-error
correlations can drop in without changing this interface.
"""

from __future__ import annotations

# Structural block-rho prior, revisable from seeds. rho=0 would mean fully
# independent raters, recovering N_eff = N exactly (the independent floor).
RHO_WITHIN_FAMILY = 0.5
RHO_ACROSS_FAMILY = 0.2


def mean_pairwise_rho(
    families: list[str],
    *,
    rho_within: float = RHO_WITHIN_FAMILY,
    rho_across: float = RHO_ACROSS_FAMILY,
) -> float:
    """Average pairwise correlation over all rater pairs, using the block prior."""
    n = len(families)
    if n <= 1:
        return 0.0
    total = 0.0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += rho_within if families[i] == families[j] else rho_across
            pairs += 1
    return total / pairs


def effective_raters(
    families: list[str],
    *,
    rho_within: float = RHO_WITHIN_FAMILY,
    rho_across: float = RHO_ACROSS_FAMILY,
) -> float:
    """N_eff = N / (1 + (N-1)*rho_bar). `families` is the vendor family per rater (order-free).

    With all-distinct families and rho_across=0 this returns N exactly (independent floor).
    """
    n = len(families)
    if n <= 1:
        return float(n)
    rho_bar = mean_pairwise_rho(families, rho_within=rho_within, rho_across=rho_across)
    return n / (1.0 + (n - 1) * rho_bar)
