"""Inter-rater agreement for the scoring panel (ADR-0012) — measurement, not correction.

An earlier design reached for Cohen's weighted κ; the v6 of *Judging the Judges*
(arXiv:2406.12624) retracted κ because its per-rater chance baseline "adjusts for the observed
average differences between raters, which is in fact part of what we intend to measure." For our
setting — **>2 raters, an ordinal label (`not_met` < `partial` < `met`), a separate `n/a`, and
missing data** — the right family is **Krippendorff's α (ordinal)**, reported with **Gwet's AC2**
(prevalence-robust) alongside, plus the **marginal label distribution** and a plain
**percent-agreement** sanity number (never a headline — high agreement coexists with large score
error). **No Cohen's κ is emitted as a headline.**

These are computed from the panel's own clause judgments — no humans, no seeds — so they ship as
v1 instrumentation. With n=1 run they are *reported*, not yet used to *correct*.

Input shape: `items` is a list of per-clause rating lists, one entry per rater who judged that
clause; `None` or `"n/a"` mean the clause was not applicably rated and are dropped from the
ordinal coefficients (but counted in the marginal distribution).
"""

from __future__ import annotations

ORDINAL: tuple[str, ...] = ("not_met", "partial", "met")

Items = list[list[str | None]]


def _ordinal_rows(items: Items, levels: tuple[str, ...]) -> list[list[int]]:
    """Per item, the applicable ratings as level indices (n/a and unknown labels dropped)."""
    idx = {lab: i for i, lab in enumerate(levels)}
    return [[idx[v] for v in row if v in idx] for row in items]


def ordinal_weights(q: int) -> list[list[float]]:
    """Gwet/Krippendorff ordinal agreement weights for q ranked categories.

    w[k][l] = 1 − d(d+1) / (q(q−1)) with d = |k−l|: 1 on the diagonal, decreasing with rank
    distance, 0 at the extremes (for q categories the farthest-apart pair gets weight 0).
    """
    denom = q * (q - 1)
    return [
        [1.0 - (abs(k - j) * (abs(k - j) + 1)) / denom if denom else 1.0 for j in range(q)]
        for k in range(q)
    ]


def krippendorff_alpha(items: Items, levels: tuple[str, ...] = ORDINAL) -> float | None:
    """Krippendorff's α with the ordinal difference metric. None if no item has ≥2 ratings.

    Built on the coincidence matrix (handles >2 raters and missing data natively). The ordinal
    δ²(c,k) uses the coincidence marginals, so it adapts to the realised label spread.
    """
    rows = _ordinal_rows(items, levels)
    q = len(levels)
    o = [[0.0] * q for _ in range(q)]
    for vals in rows:
        m = len(vals)
        if m < 2:
            continue
        inv = 1.0 / (m - 1)
        for i in range(m):
            for j in range(m):
                if i != j:
                    o[vals[i]][vals[j]] += inv
    n_marg = [sum(o[c]) for c in range(q)]
    n_total = sum(n_marg)
    if n_total < 2:
        return None

    def delta2(c: int, k: int) -> float:
        if c == k:
            return 0.0
        lo, hi = (c, k) if c < k else (k, c)
        s = sum(n_marg[lo : hi + 1]) - (n_marg[c] + n_marg[k]) / 2.0
        return s * s

    d_o = sum(o[c][k] * delta2(c, k) for c in range(q) for k in range(q))
    d_e = sum(n_marg[c] * n_marg[k] * delta2(c, k) for c in range(q) for k in range(q)) / (
        n_total - 1
    )
    if d_e == 0.0:  # no usable variation -> perfect agreement by convention
        return 1.0
    return 1.0 - d_o / d_e


def gwet_ac2(items: Items, levels: tuple[str, ...] = ORDINAL) -> float | None:
    """Gwet's AC2 with ordinal weights. None if no item has ≥2 ratings.

    Chance term pe = (Σw / (q(q−1))) · Σ_k π_k(1−π_k) — the prevalence-robust baseline that
    reduces to AC1 under identity weights. π_k is the mean per-item category prevalence.
    """
    rows = [vals for vals in _ordinal_rows(items, levels) if len(vals) >= 2]
    q = len(levels)
    n = len(rows)
    if n == 0:
        return None
    w = ordinal_weights(q)

    pa_terms = []
    pi = [0.0] * q
    for vals in rows:
        r = len(vals)
        counts = [0] * q
        for v in vals:
            counts[v] += 1
        weighted = sum(w[k][j] * counts[k] * counts[j] for k in range(q) for j in range(q))
        pa_terms.append((weighted - r) / (r * (r - 1)))
        for k in range(q):
            pi[k] += counts[k] / r
    pa = sum(pa_terms) / n
    pi = [p / n for p in pi]

    tw = sum(w[k][j] for k in range(q) for j in range(q))
    pe = (tw / (q * (q - 1))) * sum(p * (1.0 - p) for p in pi)
    if pe >= 1.0:
        return None
    return (pa - pe) / (1.0 - pe)


def percent_agreement(items: Items, levels: tuple[str, ...] = ORDINAL) -> float | None:
    """Plain pairwise exact-agreement fraction over rater pairs (a SANITY number, never a
    headline — high values coexist with large score error)."""
    rows = _ordinal_rows(items, levels)
    agree = 0
    pairs = 0
    for vals in rows:
        m = len(vals)
        for i in range(m):
            for j in range(i + 1, m):
                pairs += 1
                if vals[i] == vals[j]:
                    agree += 1
    return agree / pairs if pairs else None


def marginal_distribution(items: Items) -> dict[str, int]:
    """Raw label counts across all cells, including `n/a` and any null (the denominator story)."""
    out: dict[str, int] = {}
    for row in items:
        for v in row:
            key = "n/a" if v is None else v
            out[key] = out.get(key, 0) + 1
    return out


def agreement_report(items: Items, levels: tuple[str, ...] = ORDINAL) -> dict:
    """The per-clause-type agreement bundle: α + AC2 + marginals + the percent-agreement sanity
    number — published together (ADR-0012). Deliberately carries NO Cohen κ field."""
    marg = marginal_distribution(items)
    return {
        "krippendorff_alpha": krippendorff_alpha(items, levels),
        "gwet_ac2": gwet_ac2(items, levels),
        "percent_agreement": percent_agreement(items, levels),
        "marginal_distribution": marg,
        "n_items": len(items),
        "n_na": marg.get("n/a", 0),
    }
