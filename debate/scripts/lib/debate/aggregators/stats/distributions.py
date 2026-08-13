"""The rater three-point distribution model + the special functions it needs (ADR-0013).

This module answers one question: *given a rater's `(low, best, high, confidence)`, what
distribution does that imply, and how do I sample / evaluate it?* The headline `fit_rater`
treats `low`/`high` as the rater's **5th/95th percentiles** (ADR-0013 decision 1) and fits a
modified-PERT Beta by *quantile matching* — not by pinning the Beta support to `[low, high]`,
which manufactured false precision given LLM overconfidence. `fit_sample`/`fit_pdf` then keep
the fitted `RaterFit` opaque to its consumers (the sampler in `montecarlo`, the analytic grid
in `pooling`), so changing the fit representation touches only this file.

The aggregation engine deliberately avoids scipy/numpy (the rest of the pipeline is stdlib-
only), so the special functions the fit needs live here too, as compact well-known routines:

* the regularized incomplete beta `beta_cdf` (Lentz continued fraction, Numerical Recipes) and
  its inverse `beta_ppf` (bisection — the CDF is monotone, so this is exact to ~1e-12);
* the Beta density `beta_pdf` (via `lgamma`);
* the inverse normal CDF `inv_norm_cdf` (Acklam's rational approximation), used to convert a
  rater's stated confidence into an interval-rescaling factor.
"""

from __future__ import annotations

import math
import random
from typing import NamedTuple

_FPMIN = 1e-300
_EPS = 3e-12
_MAXIT = 300


def _betacf(x: float, a: float, b: float) -> float:
    """Continued-fraction core of the incomplete beta (Lentz's method)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, _MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def beta_cdf(x: float, a: float, b: float) -> float:
    """Regularized incomplete beta I_x(a, b) = P(Beta(a,b) <= x), x in [0,1]."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    front = math.exp(ln_front)
    # Use the continued fraction that converges fastest for this x (NR §6.4).
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(x, a, b) / a
    return 1.0 - front * _betacf(1.0 - x, b, a) / b


def beta_ppf(p: float, a: float, b: float) -> float:
    """Inverse CDF (quantile) of Beta(a,b) by bisection. p in [0,1]."""
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(80):  # 2^-80 — far below any width we publish
        mid = 0.5 * (lo + hi)
        if beta_cdf(mid, a, b) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def beta_pdf(x: float, a: float, b: float) -> float:
    """Density of Beta(a,b) at x in [0,1] (0 at the open boundaries for a,b > 1)."""
    if x <= 0.0 or x >= 1.0:
        return 0.0
    ln = (
        (a - 1.0) * math.log(x)
        + (b - 1.0) * math.log1p(-x)
        + math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
    )
    return math.exp(ln)


# Acklam's inverse-normal-CDF rational approximation (|abs error| < 1.15e-9).
_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)


def inv_norm_cdf(p: float) -> float:
    """Inverse standard-normal CDF (probit). p in (0,1)."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError("inv_norm_cdf requires 0 < p < 1")
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return (
        (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5])
        * q
        / (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0)
    )


# --- the modified-PERT, fit by quantile-matching (ADR-0013) ---

# Common credible level the elicited interval is rescaled to before pooling. IDEA's R1: a stated
# "I'm c-confident the truth is in [low, high]" is converted to the panel's shared level so that
# confidence actually changes the fitted width instead of being collected-and-ignored.
CREDIBLE_LEVEL = 0.90
_Z_HALF_LEVEL = inv_norm_cdf(0.5 + CREDIBLE_LEVEL / 2.0)  # z for the target half-interval

# Clamp stated confidence into a sane band before rescaling: a model claiming > 99% certainty on
# a compliance interval is not credible (don't let it shrink the band to a needle), and < 10%
# would blow the interval up absurdly. Documented prior, revisable from seeds.
_CONF_FLOOR, _CONF_CEIL = 0.10, 0.99


def rescale_interval(
    low: float, best: float, high: float, confidence: float
) -> tuple[float, float]:
    """Stretch/shrink [low, high] around `best` so it represents the common credible level.

    `confidence` is the rater's stated probability the truth lies in [low, high]. If it equals
    the target level (0.90 — also the unspecified-default, so a missing confidence is a no-op
    rather than wrongly narrowing) or is a fully-certain >= 1.0, the interval is returned
    unchanged. A less-confident rater (c < 0.90) has its interval widened; an over-confident one
    (c > 0.90) narrowed. Factor = z(0.95) / z((1+c)/2) under a normal reference (IDEA R1).
    """
    if confidence >= 1.0 or confidence <= 0.0:
        return low, high
    c = min(max(confidence, _CONF_FLOOR), _CONF_CEIL)
    if abs(c - CREDIBLE_LEVEL) < 1e-9:
        return low, high
    factor = _Z_HALF_LEVEL / inv_norm_cdf(0.5 + c / 2.0)
    return best - (best - low) * factor, best + (high - best) * factor


def pert_shape(low: float, best: float, high: float, gamma: float) -> tuple[float, float]:
    """Modified-PERT Beta shape parameters (alpha, beta) for mode `best` in [low, high].

    `gamma` is the concentration (classic PERT uses 4, which over-concentrates given LLM
    overconfidence; ADR-0013 uses ~2–3). The mode's relative position drives the skew.
    """
    span = high - low
    if span <= 0.0:
        return 1.0, 1.0
    m = min(max((best - low) / span, 0.0), 1.0)
    return 1.0 + gamma * m, 1.0 + gamma * (1.0 - m)


def quantile_support(low: float, high: float, alpha: float, beta: float) -> tuple[float, float]:
    """Effective Beta support (a, b) such that the Beta(alpha,beta) on (a,b) has its 5th/95th
    percentiles exactly at `low`/`high` — i.e. treat low/high as tail quantiles, not endpoints.

    Returns (a, span) where a sample is `a + span * z`, z ~ Beta(alpha, beta).
    """
    z05 = beta_ppf(0.05, alpha, beta)
    z95 = beta_ppf(0.95, alpha, beta)
    if z95 <= z05:  # degenerate shape — fall back to support == interval
        return low, max(high - low, 0.0)
    span = (high - low) / (z95 - z05)
    return low - span * z05, span


# --- the fitted rater distribution (the one object consumers pass around) ---

# Modified-PERT concentration. Classic PERT uses 4, which over-concentrates given documented
# LLM overconfidence; ADR-0013 uses ~2–3. Revisable from seed performance once seeds exist.
DEFAULT_GAMMA = 2.5


class RaterFit(NamedTuple):
    """One rater's score distribution as a Beta(alpha, beta) on the support (a_supp, a_supp+span).

    Opaque to consumers: sample it with `fit_sample`, evaluate its density with `fit_pdf`. Built
    only by `fit_rater`. Keeping the four fields private to this module means changing the fit
    (e.g. a different family) touches `montecarlo`/`pooling` not at all.
    """

    alpha: float
    beta: float
    a_supp: float
    span: float


def fit_rater(
    low: float, best: float, high: float, confidence: float, gamma: float = DEFAULT_GAMMA
) -> RaterFit | None:
    """Fit one rater's three-point estimate to a quantile-matched modified-PERT (ADR-0013).

    Confidence rescaling (IDEA R1) is applied first, so two raters with the same (low, best,
    high) but different confidence get different fitted widths. Returns None for a degenerate
    (zero-width) rater — the caller samples that as a point mass at `best`.
    """
    low, high = rescale_interval(low, best, high, confidence)
    if high <= low:
        return None
    best = min(max(best, low), high)
    alpha, beta = pert_shape(low, best, high, gamma)
    a_supp, span = quantile_support(low, high, alpha, beta)
    if span <= 0.0:
        return None
    return RaterFit(alpha, beta, a_supp, span)


def fit_sample(fit: RaterFit, rng: random.Random) -> float:
    """One draw from the fitted distribution (unclamped — the caller owns the [0,1] score bound)."""
    return fit.a_supp + fit.span * rng.betavariate(fit.alpha, fit.beta)


def fit_pdf(fit: RaterFit, x: float) -> float:
    """Density of the fitted distribution at x (0 outside its support)."""
    z = (x - fit.a_supp) / fit.span
    return beta_pdf(z, fit.alpha, fit.beta) / fit.span if 0.0 < z < 1.0 else 0.0
