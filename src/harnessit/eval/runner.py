"""Eval runner — orchestrates one scenario end-to-end.

The runner is the integration point for Stage 2's deliverable 3
(naked frontier model fails the first eval visibly). It owns the
substrate-call → comparison → naked-model → score sequence; the
scenario provides the prompt/scoring policy; Langfuse instrumentation
emits the full waterfall (eval span → generation span → score event).
"""

from __future__ import annotations

import time
from typing import Any

from langfuse import get_client, observe

from harnessit.eval.scoring import Score
from harnessit.eval.types import EvalResult, EvalScenario
from harnessit.model import ModelClient
from harnessit.substrate import DoppelgangerClient
from harnessit.tracing import traced_complete

EVAL_SPAN_NAME = "harnessit.eval.run"
SCORE_NAME = "harnessit.eval.overall_pass"


@observe(name=EVAL_SPAN_NAME, capture_input=False, capture_output=False)
async def run_eval(
    *,
    scenario: EvalScenario,
    substrate: DoppelgangerClient,
    model_client: ModelClient,
    run_id_prefix: str | None = None,
) -> EvalResult:
    """Run one scenario end-to-end. Returns the structured result.

    The substrate's ``run_scenario`` calls happen inside the adapter
    subprocess, so they aren't visible to Langfuse from this side; the
    naked-model call is wrapped by ``traced_complete``. The eval-level
    span here gives the trajectory viewer (Stage 4) a parent to anchor
    children under.
    """
    prefix = run_id_prefix or _default_run_id_prefix(scenario.name)

    baseline_run_id = f"{prefix}__baseline"
    injected_run_id = f"{prefix}__injected"

    baseline = await substrate.run_scenario(
        scenario.baseline_scenario, run_id=baseline_run_id
    )
    injected = await substrate.run_scenario(
        scenario.injected_scenario, run_id=injected_run_id
    )
    comparison = await substrate.compare_runs(
        baseline["trace_dir"], injected["trace_dir"]
    )

    user_prompt = scenario.build_user_prompt(comparison)
    completion = traced_complete(
        model_client,
        system=scenario.system_prompt,
        user=user_prompt,
        scenario_name=scenario.name,
    )

    score = scenario.score(comparison, completion)

    client = get_client()
    client.update_current_span(
        input={
            "scenario": scenario.name,
            "baseline_scenario": scenario.baseline_scenario,
            "injected_scenario": scenario.injected_scenario,
        },
        output={
            "overall_pass": score.overall_pass,
            "criteria": dict(score.criteria),
            "rationale": score.rationale,
        },
        metadata={
            "expected_to_pass": scenario.expected_to_pass,
            "flow_count_delta": comparison.get("flow_count_delta"),
            "has_count_divergence": comparison.get("has_count_divergence"),
            "baseline_run_id": baseline["run_id"],
            "injected_run_id": injected["run_id"],
        },
    )
    client.score_current_trace(
        name=SCORE_NAME,
        value=1.0 if score.overall_pass else 0.0,
        comment=score.rationale,
    )

    trace_id = client.get_current_trace_id()

    return EvalResult(
        scenario_name=scenario.name,
        baseline_run_id=baseline["run_id"],
        baseline_trace_dir=baseline["trace_dir"],
        injected_run_id=injected["run_id"],
        injected_trace_dir=injected["trace_dir"],
        comparison=comparison,
        completion=completion,
        score=score,
        user_prompt=user_prompt,
        langfuse_trace_id=trace_id,
    )


def _default_run_id_prefix(scenario_name: str) -> str:
    safe = scenario_name.replace("/", "-").replace(" ", "-")
    return f"{safe}-{int(time.time())}"


def format_eval_summary(result: EvalResult) -> str:
    """Human-readable summary of an eval result for terminal output."""
    score = result.score
    lines = [
        f"=== {result.scenario_name} ===",
        f"baseline: {result.baseline_run_id}",
        f"injected: {result.injected_run_id}",
        f"flow_count_delta: {result.comparison.get('flow_count_delta')}",
        f"has_count_divergence: {result.comparison.get('has_count_divergence')}",
        f"fct_p50_delta_ns: {result.comparison.get('fct_p50_delta_ns')}",
        f"fct_p99_delta_ns: {result.comparison.get('fct_p99_delta_ns')}",
        f"fct_p999_delta_ns: {result.comparison.get('fct_p999_delta_ns')}",
        "",
        f"--- model output ({result.completion.input_tokens}→{result.completion.output_tokens} tokens) ---",
        result.completion.text,
        "",
        "--- scoring ---",
    ]
    for criterion, passed in score.criteria.items():
        lines.append(f"  {criterion}: {'PASS' if passed else 'FAIL'}")
    lines.append("")
    lines.append(f"overall_pass: {score.overall_pass}")
    if result.langfuse_trace_id:
        lines.append(f"langfuse_trace_id: {result.langfuse_trace_id}")
    return "\n".join(lines)


__all__ = [
    "EVAL_SPAN_NAME",
    "SCORE_NAME",
    "format_eval_summary",
    "run_eval",
]
