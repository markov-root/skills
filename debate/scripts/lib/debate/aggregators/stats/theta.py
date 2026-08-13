"""BEW-Θ — the probabilistic estimand for the headline.

The interim (C+) headline is the arbitrated clause-mass mean, with the panel band kept as a
separate diagnostic — coherent, but the point and band describe different quantities. The
destination makes the point *itself* probabilistic so coherence is a theorem, not a clamp:

    Θ = the clause-mass-weighted fraction of TRUE compliance, a latent random variable.
    headline = E[Θ];  band = percentiles of the SAME Θ  ⇒  the point lies inside its own band.

Per clause we set a Beta whose MODE is the arbitrated value a_c ∈ {0, 0.5, 1} (preserving the
regulatory distinction between *compliance level* and *evidence quality*) and whose CONCENTRATION
is set by the evidence tier (weaker evidence ⇒ a *wider* Beta, never a lower mode). This is the
BEW-Θ refinement (cross-vendor red-team): a `met` stays mode-1 regardless of tier, but its
*expected* p_c < 1 with one-sided downward uncertainty; a `not_met` gets a small UPWARD allowance
(the dominant false-zero error), larger when the evidence is thin/absent.

The κ (concentration) values are a DOCUMENTED, PRE-REGISTERED prior — the δ/ε-replacement the
debate demanded — revisable from seeds. Until the coverage/PIT gate passes against
gold clauses, BEW-Θ is emitted LABELLED UNCALIBRATED and does not replace the displayed headline.
"""

from __future__ import annotations

import math
import random

from debate.aggregators.stats.distributions import beta_ppf
from debate.aggregators.stats.model import VALUE_SCORE

# Concentration of the per-clause Beta by evidence tier (higher = tighter = more certain). A
# documented prior, NOT calibrated — revisable from seed-error data. κ ≥ 2 required.
_KAPPA: dict[str, float] = {"primary": 20.0, "inferred": 10.0, "thin": 6.0, "none": 4.0}
_KAPPA_DEFAULT = 8.0


def clause_beta(value: str, evidence_tier: str | None) -> tuple[float, float]:
    """(alpha, beta) for a clause's compliance Beta: mode = arbitrated value, concentration = tier.

    met (mode 1) -> Beta(κ-1, 1): mode at 1, one-sided downward uncertainty, mean (κ-1)/κ < 1.
    not_met (mode 0) -> Beta(1, κ-1): mode at 0, one-sided UPWARD allowance (false-zero), mean 1/κ.
    partial (mode .5) -> Beta(κ/2, κ/2): symmetric around 0.5.
    """
    m = VALUE_SCORE.get(value, 0.0)  # 0 / 0.5 / 1
    kappa = _KAPPA.get(evidence_tier or "", _KAPPA_DEFAULT)
    a = m * (kappa - 2.0) + 1.0
    b = (1.0 - m) * (kappa - 2.0) + 1.0
    return a, b


def _phi(x: float) -> float:
    """Standard-normal CDF Φ (for the Gaussian copula), via erfc."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def theta_stats(
    clauses: list[tuple[str, str | None, float]],
    *,
    n_samples: int = 10_000,
    seed: int = 12345,
    rho: float = 0.0,
    agg: str = "mean",
) -> dict | None:
    """Distribution stats for Θ over the given ACTIVE clauses on one basis.

    `clauses` is a list of (value, evidence_tier, weight). Each clause is Xₖ ~ Beta_k, correlated
    by a one-factor Gaussian copula with correlation `rho` (default 0 = independent floor, matching
    the production aggregation; a structural block-ρ can be supplied later — ADR-0013).

    `agg` selects how the per-draw clauses combine, mirroring the indicator's `satisfy`:
    `mean` → the clause-mass weighted mean Θ = Σ wₖ Xₖ / Σ wₖ (`all_of`); `max` → the per-draw MAX
    over the clauses (`any_of`, the t-conorm — weight-free, like the point estimator). Either way
    the point E[Θ] and the band are percentiles of the SAME Θ, so coherence (point-in-band) holds.

    Returns {mean, median, p5, p95} on [0,1], or None if no clause carries weight.
    """
    betas = [(clause_beta(v, t), w) for v, t, w in clauses if w > 0]
    wsum = sum(w for _, w in betas)
    if not betas or wsum <= 0:
        return None
    rng = random.Random(seed)
    sr, s1r = math.sqrt(rho), math.sqrt(1.0 - rho)
    draws = []
    for _ in range(n_samples):
        z_common = rng.gauss(0.0, 1.0)
        per_clause = []
        for (a, b), w in betas:
            latent = sr * z_common + s1r * rng.gauss(0.0, 1.0)
            u = min(max(_phi(latent), 1e-9), 1.0 - 1e-9)
            per_clause.append((beta_ppf(u, a, b), w))
        if agg == "max":
            draws.append(max(x for x, _ in per_clause))
        else:
            draws.append(sum(x * w for x, w in per_clause) / wsum)
    draws.sort()

    def _pct(p: float) -> float:
        idx = min(int(p * n_samples), n_samples - 1)
        return draws[idx]

    return {
        "mean": sum(draws) / n_samples,
        "median": _pct(0.50),
        "p5": _pct(0.05),
        "p95": _pct(0.95),
    }
