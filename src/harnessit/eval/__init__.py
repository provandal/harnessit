"""Eval framework — scenario shape, runner, scoring rubrics.

The harness-side eval framework calls Doppelgänger's substrate-level
eval primitives via MCP (Erik 2026-05-05) rather than duplicating them.
This preserves the substrate-adapter contract that Stage 13's AIR
Adapter will inherit. Scoring rubrics enforce Architecture v0.5 §3.8
substrate-level commitments — flow-count delta, distribution-aware
comparison, incomplete-flow annotation — by *requiring* the model's
proposed investigation plan to query those signals.
"""

from harnessit.eval.runner import format_eval_summary, run_eval
from harnessit.eval.scoring import Score, score_triage_quality
from harnessit.eval.types import EvalContext, EvalResult, EvalScenario

__all__ = [
    "EvalContext",
    "EvalResult",
    "EvalScenario",
    "Score",
    "format_eval_summary",
    "run_eval",
    "score_triage_quality",
]
