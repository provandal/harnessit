"""Eval framework — scenario shape, runner, scoring rubrics.

The harness-side eval framework calls Doppelgänger's substrate-level
eval primitives via MCP (Erik 2026-05-05) rather than duplicating them.
This preserves the substrate-adapter contract that Stage 13's AIR
Adapter will inherit. The scoring layer enforces Architecture v0.5 §3.8
substrate-level commitments — flow-count delta as primary failure
signature, distribution-aware comparison, incomplete-flow annotation —
by *requiring* those signals to flow from compare_runs into the score
rubrics.
"""

from harnessit.eval.runner import run_eval
from harnessit.eval.scoring import Score, score_silent_drops_localization
from harnessit.eval.types import EvalResult, EvalScenario

__all__ = [
    "EvalResult",
    "EvalScenario",
    "Score",
    "run_eval",
    "score_silent_drops_localization",
]
