"""The referees axis (ADR-0012): cheap, deterministic checks run BETWEEN rounds that emit FACTS
(never verdicts), injected as a FLAGS block into the next prompt so the panel spends its reasoning
on the residue, not on what code can compute.

`base.py` defines the seam (the `Finding` type + the `Checker` signature + the disposition lanes).
The concrete checkers (near_duplicate, non_atomic, thin_rationale, unaddressed, ungrounded_quote, …)
and the engine wiring that runs them at each injection point are added by task-0013.
"""
