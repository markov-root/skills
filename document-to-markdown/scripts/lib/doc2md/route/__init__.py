"""Deterministic routing over eligible adapters.

The production router is intentionally simple and explainable: it plans every adapter that declares
the detected media type, in a stable preference order bounded by the policy attempt budget, and
selects the highest-quality successful attempt. It never invents an adapter, never exceeds the
budget, and never discards a cheaper usable result for a more expensive one of equal quality. The
benchmark-derived promotion of routing weights (Task 0016) layers on top of this contract.
"""

from doc2md.route.heuristic import HeuristicRouter

__all__ = ["HeuristicRouter"]
