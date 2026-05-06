"""Eval runner — orchestrates one scenario end-to-end.

Stage 2 deliverable 3: a naked frontier model fails the first eval
visibly. The runner owns the substrate-call → optional-comparison →
naked-model → score sequence; the scenario provides the prompt/scoring
policy; Langfuse instrumentation emits the full waterfall (eval span
→ generation span → score event).

Two scenario shapes:

* **Paired** — ``scenario.baseline_scenario`` is set; the runner runs
  baseline + target + ``compare_runs`` and hands the comparison to the
  prompt builder/scorer via ``EvalContext``.
* **Single-run** — ``scenario.baseline_scenario is None``; the runner
  runs only the target and hands ``EvalContext`` with ``baseline_run``
  and ``comparison`` set to None.
"""

from __future__ import annotations

import time
from typing import Any

from langfuse import get_client, observe

from harnessit.eval.types import EvalContext, EvalResult, EvalScenario
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
    scenario_metadata: dict[str, Any] | None = None,
) -> EvalResult:
    """Run one scenario end-to-end. Returns the structured result.

    ``scenario_metadata`` is propagated into the EvalContext so scorers
    can access scenario-author intent (intended_symptom, root_cause).
    Defaults to an empty dict; the per-scenario module supplies it.
    """
    prefix = run_id_prefix or _default_run_id_prefix(scenario.name)
    is_paired = scenario.baseline_scenario is not None

    baseline_run: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
    baseline_run_id: str | None = None
    baseline_trace_dir: str | None = None

    if is_paired:
        baseline_run_id = f"{prefix}__baseline"
        baseline_run = await substrate.run_scenario(
            scenario.baseline_scenario, run_id=baseline_run_id
        )
        baseline_trace_dir = baseline_run["trace_dir"]

    target_run_id = f"{prefix}__target"
    target_run = await substrate.run_scenario(
        scenario.target_scenario, run_id=target_run_id
    )

    if is_paired:
        comparison = await substrate.compare_runs(
            baseline_run["trace_dir"], target_run["trace_dir"]
        )

    context = EvalContext(
        target_run=target_run,
        baseline_run=baseline_run,
        comparison=comparison,
        scenario_metadata=dict(scenario_metadata or {}),
    )

    user_prompt = scenario.build_user_prompt(context)
    completion = traced_complete(
        model_client,
        system=scenario.system_prompt,
        user=user_prompt,
        scenario_name=scenario.name,
    )

    score = scenario.score(context, completion)

    client = get_client()
    span_input: dict[str, Any] = {
        "scenario": scenario.name,
        "target_scenario": scenario.target_scenario,
    }
    if is_paired:
        span_input["baseline_scenario"] = scenario.baseline_scenario

    metadata: dict[str, Any] = {
        "expected_to_pass": scenario.expected_to_pass,
        "target_run_id": target_run["run_id"],
    }
    if comparison is not None:
        metadata["flow_count_delta"] = comparison.get("flow_count_delta")
        metadata["has_count_divergence"] = comparison.get("has_count_divergence")
    if baseline_run is not None:
        metadata["baseline_run_id"] = baseline_run["run_id"]

    client.update_current_span(
        input=span_input,
        output={
            "overall_pass": score.overall_pass,
            "criteria": dict(score.criteria),
            "rationale": score.rationale,
        },
        metadata=metadata,
    )
    client.score_current_trace(
        name=SCORE_NAME,
        value=1.0 if score.overall_pass else 0.0,
        comment=score.rationale,
    )

    trace_id = client.get_current_trace_id()

    return EvalResult(
        scenario_name=scenario.name,
        target_run_id=target_run["run_id"],
        target_trace_dir=target_run["trace_dir"],
        baseline_run_id=baseline_run_id,
        baseline_trace_dir=baseline_trace_dir,
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
        f"target:   {result.target_run_id}",
    ]
    if result.baseline_run_id:
        lines.append(f"baseline: {result.baseline_run_id}")
    if result.comparison is not None:
        lines.append(f"flow_count_delta: {result.comparison.get('flow_count_delta')}")
        lines.append(f"has_count_divergence: {result.comparison.get('has_count_divergence')}")
        lines.append(f"fct_p50_delta_ns: {result.comparison.get('fct_p50_delta_ns')}")
        lines.append(f"fct_p99_delta_ns: {result.comparison.get('fct_p99_delta_ns')}")
        lines.append(f"fct_p999_delta_ns: {result.comparison.get('fct_p999_delta_ns')}")
    lines.append("")
    lines.append(
        f"--- model output ({result.completion.input_tokens}->"
        f"{result.completion.output_tokens} tokens) ---"
    )
    lines.append(result.completion.text)
    lines.append("")
    lines.append("--- scoring ---")
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
