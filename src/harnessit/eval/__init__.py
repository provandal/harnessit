"""Eval framework — scenario shape, runner, scoring rubrics.

The harness-side eval framework calls Doppelgänger's substrate-level
eval primitives via MCP (Erik 2026-05-05) rather than duplicating them.
This preserves the substrate-adapter contract that Stage 13's AIR
Adapter will inherit. Scoring rubrics enforce Architecture v0.5 §3.8
substrate-level commitments — flow-count delta, distribution-aware
comparison, incomplete-flow annotation — by *requiring* the model's
proposed investigation plan to query those signals.

2026-05-11 sweep finding: the rubric (keyword + 5-criterion LLM judge)
measures triage *quality* but does not correlate with diagnosis
correctness. ``CorrectnessJudge`` adds an orthogonal axis that grades
the agent's stated root cause against substrate ground truth.
"""

from harnessit.eval.correctness import (
    CorrectnessJudge,
    CorrectnessJudgeError,
    CorrectnessJudgment,
    Verdict,
)
from harnessit.eval.runner import format_eval_summary, run_eval
from harnessit.eval.scoring import Score, score_triage_quality
from harnessit.eval.types import EvalContext, EvalResult, EvalScenario

__all__ = [
    "CorrectnessJudge",
    "CorrectnessJudgeError",
    "CorrectnessJudgment",
    "EvalContext",
    "EvalResult",
    "EvalScenario",
    "Score",
    "Verdict",
    "format_eval_summary",
    "run_eval",
    "score_triage_quality",
]
