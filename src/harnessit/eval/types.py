"""Eval framework types — scenario shape, result shape."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from harnessit.eval.scoring import Score
from harnessit.model import Completion


@dataclass(frozen=True)
class EvalScenario:
    """Declarative description of one eval scenario.

    Two MCP scenario names — ``baseline_scenario`` and
    ``injected_scenario`` — drive Doppelgänger to produce a baseline run
    and a fault-injected run, respectively. ``compare_runs`` then
    produces the comparison that gets handed to the model.

    ``build_user_prompt`` shapes the comparison data into the user
    message. ``score`` grades the completion against the comparison
    payload (which is used as the source of ground-truth signals: at
    minimum, ``flow_count_delta`` and the per-percentile FCT deltas).
    """

    name: str
    description: str
    system_prompt: str
    baseline_scenario: str
    injected_scenario: str
    build_user_prompt: Callable[[dict[str, Any]], str]
    score: Callable[[dict[str, Any], Completion], Score]
    expected_to_pass: bool = False


@dataclass(frozen=True)
class EvalResult:
    """One eval run's complete record.

    Carries everything needed to either reconstruct the run from disk
    (via the trace dirs) or render it in the trajectory viewer (Stage 4).
    """

    scenario_name: str
    baseline_run_id: str
    baseline_trace_dir: str
    injected_run_id: str
    injected_trace_dir: str
    comparison: dict[str, Any]
    completion: Completion
    score: Score
    user_prompt: str
    langfuse_trace_id: str | None = None
