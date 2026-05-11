"""Eval framework types — scenario shape, run context, result shape.

Stage 2 supports two scenario shapes:

* **Paired** — a baseline run + an injected run + a ``compare_runs``
  output. The legacy silent-drops shape; useful when the eval has a
  clean before/after pair.
* **Single-run** — one scenario run; no baseline, no comparison. The
  microburst shape and (we expect) most future scenarios. Real on-call
  doesn't get pre-paired comparisons handed to it.

Both shapes share ``EvalContext`` — the runner populates the relevant
fields and hands it to ``build_user_prompt`` and ``score``. Single-run
scenarios receive ``baseline_run = None`` and ``comparison = None``;
prompt builders and scorers handle the absence explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from harnessit.eval.correctness import CorrectnessJudgment
from harnessit.eval.judge import Judgment
from harnessit.eval.scoring import Score
from harnessit.model import Completion, ToolCall


@dataclass(frozen=True)
class EvalContext:
    """Everything the prompt builder and scorer need from one eval run.

    ``target_run`` is the run_scenario result for the scenario under
    investigation — always present. ``baseline_run`` and ``comparison``
    are only populated for paired scenarios; single-run scenarios pass
    ``None`` and the prompt/scorer handle the absence.

    ``scenario_metadata`` carries scenario-author intent
    (``intended_symptom``, ``root_cause``, ``difficulty``) so scorers
    can grade against ground truth in single-run mode.
    """

    target_run: dict[str, Any]
    baseline_run: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
    scenario_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalScenario:
    """Declarative description of one eval scenario.

    ``target_scenario`` is the substrate scenario name to run (always).
    ``baseline_scenario`` is optional — when set, the runner also runs
    the baseline and computes ``compare_runs``; when None, single-run
    mode applies.

    ``build_user_prompt(context)`` shapes the run data into the user
    message. ``score(context, completion)`` grades the model output
    against the substrate signals + scenario metadata.
    """

    name: str
    description: str
    system_prompt: str
    target_scenario: str
    build_user_prompt: Callable[[EvalContext], str]
    score: Callable[[EvalContext, Completion], Score]
    baseline_scenario: str | None = None
    expected_to_pass: bool = False
    # Stage 3: when True, the runner gives the model the harness tool
    # surface (harnessit.tools.Tools bound to ``target_scenario``) and
    # uses ``ModelClient.complete_with_tools``. When False (Stage 2
    # default), the runner uses the naked single-shot path.
    uses_tools: bool = False


@dataclass(frozen=True)
class EvalResult:
    """One eval run's complete record.

    ``baseline_run_id``/``baseline_trace_dir``/``comparison`` are None
    for single-run scenarios. ``target_*`` is always populated.
    """

    scenario_name: str
    target_run_id: str
    target_trace_dir: str
    completion: Completion
    score: Score
    user_prompt: str
    baseline_run_id: str | None = None
    baseline_trace_dir: str | None = None
    comparison: dict[str, Any] | None = None
    langfuse_trace_id: str | None = None
    # Stage 3: present when the scenario used tools. Empty tuple for
    # naked scenarios; preserves agent's tool round-trips for analysis.
    tool_calls: tuple[ToolCall, ...] = ()
    iterations: int = 1
    # Stage 3 v0.4-candidate: dual-scoring for the keyword-vs-LLM
    # calibration table. ``keyword_score`` is always populated. When
    # the runner is given a judge, ``llm_judgment`` populates on
    # success or ``judge_error`` populates on failure (mutually
    # exclusive). The primary ``score`` field (above) is derived:
    # llm_judgment.to_score() when present, else keyword_score.
    keyword_score: Score | None = None
    llm_judgment: Judgment | None = None
    judge_error: str | None = None
    # 2026-05-11 sweep finding: rubric (keyword + LLM) does not correlate
    # with diagnosis correctness. ``correctness_judgment`` is an
    # orthogonal axis that grades the agent's stated root cause against
    # substrate ground truth. None when no correctness judge was
    # provided OR when the substrate didn't expose ground truth for the
    # target scenario; ``correctness_error`` populates on judge failure.
    correctness_judgment: CorrectnessJudgment | None = None
    correctness_error: str | None = None
