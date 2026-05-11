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
import uuid
from typing import Any

from langfuse import get_client, observe

from harnessit.eval.correctness import (
    CorrectnessJudge,
    CorrectnessJudgeError,
    CorrectnessJudgment,
)
from harnessit.eval.judge import Judge, JudgeError, Judgment
from harnessit.eval.types import EvalContext, EvalResult, EvalScenario
from harnessit.model import Completion, ModelClient
from harnessit.substrate import DoppelgangerClient
from harnessit.tools import Tools
from harnessit.tracing import (
    traced_complete,
    traced_complete_with_tools,
    traced_correctness_score,
    traced_judge_score,
)

EVAL_SPAN_NAME = "harnessit.eval.run"
SCORE_NAME = "harnessit.eval.overall_pass"
CORRECTNESS_SCORE_NAME = "harnessit.eval.diagnosis_correctness"


@observe(name=EVAL_SPAN_NAME, capture_input=False, capture_output=False)
async def run_eval(
    *,
    scenario: EvalScenario,
    substrate: DoppelgangerClient,
    model_client: ModelClient,
    run_id_prefix: str | None = None,
    scenario_metadata: dict[str, Any] | None = None,
    judge: Judge | None = None,
    correctness_judge: CorrectnessJudge | None = None,
) -> EvalResult:
    """Run one scenario end-to-end. Returns the structured result.

    ``scenario_metadata`` is propagated into the EvalContext so scorers
    can access scenario-author intent (intended_symptom, root_cause).
    Defaults to an empty dict; if ``correctness_judge`` is provided, the
    runner fetches ground truth via ``substrate.list_scenarios()`` at
    run start and merges it into scenario_metadata under the
    ``ground_truth_intended_symptom`` / ``ground_truth_root_cause`` keys.

    ``judge``: optional LLM-as-judge for the 5-criterion triage rubric.
    When provided, the runner scores the response with both the keyword
    scorer (always) and the rubric judge, using the judge's verdict as
    the primary score (with fallback to keyword on judge failure).

    ``correctness_judge``: optional LLM-as-judge for diagnosis
    correctness. Orthogonal to the rubric. When provided AND ground
    truth is available, the runner grades the agent's stated root cause
    against the substrate's intended_symptom + root_cause. Verdict is
    one of CORRECT / WRONG / NO_DIAGNOSIS. Failure here is non-fatal —
    the rubric run continues independently.
    """
    prefix = run_id_prefix or _default_run_id_prefix(scenario.name)
    is_paired = scenario.baseline_scenario is not None

    # Fetch ground truth at run start so it's available for the
    # correctness judge later. Cheap (one MCP call) and only done when
    # correctness scoring is on. Empty strings when the scenario isn't
    # in the substrate registry — correctness judging will short-circuit.
    ground_truth_intended_symptom = ""
    ground_truth_root_cause = ""
    if correctness_judge is not None:
        try:
            registry = await substrate.list_scenarios()
            for entry in registry:
                if entry.get("name") == scenario.target_scenario:
                    ground_truth_intended_symptom = str(
                        entry.get("intended_symptom") or ""
                    )
                    ground_truth_root_cause = str(entry.get("root_cause") or "")
                    break
        except Exception:
            # Non-fatal: correctness will short-circuit on missing ground
            # truth, the rubric run is unaffected.
            pass

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

    merged_metadata = dict(scenario_metadata or {})
    if ground_truth_intended_symptom:
        merged_metadata.setdefault(
            "ground_truth_intended_symptom", ground_truth_intended_symptom
        )
    if ground_truth_root_cause:
        merged_metadata.setdefault(
            "ground_truth_root_cause", ground_truth_root_cause
        )
    context = EvalContext(
        target_run=target_run,
        baseline_run=baseline_run,
        comparison=comparison,
        scenario_metadata=merged_metadata,
    )

    user_prompt = scenario.build_user_prompt(context)
    tool_calls: tuple = ()
    iterations = 1
    if scenario.uses_tools:
        tools = Tools(
            substrate=substrate,
            scenario_name=scenario.target_scenario,
        )
        tool_use_completion = await traced_complete_with_tools(
            model_client,
            system=scenario.system_prompt,
            user=user_prompt,
            tools=tools.schemas,
            tool_executor=tools.execute,
            scenario_name=scenario.name,
        )
        # Synthesize a Completion for scoring — scorers only inspect text.
        # Token counts are summed across iterations by the loop.
        completion = Completion(
            text=tool_use_completion.text,
            model=tool_use_completion.model,
            input_tokens=tool_use_completion.input_tokens,
            output_tokens=tool_use_completion.output_tokens,
            stop_reason=tool_use_completion.stop_reason,
        )
        tool_calls = tool_use_completion.tool_calls
        iterations = tool_use_completion.iterations
    else:
        completion = traced_complete(
            model_client,
            system=scenario.system_prompt,
            user=user_prompt,
            scenario_name=scenario.name,
        )

    keyword_score = scenario.score(context, completion)

    llm_judgment: Judgment | None = None
    judge_error: str | None = None
    if judge is not None:
        try:
            llm_judgment = await traced_judge_score(
                judge,
                system_prompt=scenario.system_prompt,
                user_prompt=user_prompt,
                agent_response=completion.text,
                tool_calls=tool_calls,
                scenario_name=scenario.name,
            )
        except JudgeError as exc:
            judge_error = str(exc)

    primary_score = (
        llm_judgment.to_score() if llm_judgment is not None else keyword_score
    )

    correctness_judgment: CorrectnessJudgment | None = None
    correctness_error: str | None = None
    if correctness_judge is not None:
        if not (ground_truth_root_cause and ground_truth_intended_symptom):
            correctness_error = (
                "ground truth not available from substrate.list_scenarios() "
                f"for target_scenario={scenario.target_scenario!r}"
            )
        else:
            try:
                correctness_judgment = await traced_correctness_score(
                    correctness_judge,
                    system_prompt=scenario.system_prompt,
                    user_prompt=user_prompt,
                    agent_response=completion.text,
                    intended_symptom=ground_truth_intended_symptom,
                    root_cause=ground_truth_root_cause,
                    scenario_name=scenario.name,
                )
            except CorrectnessJudgeError as exc:
                correctness_error = str(exc)

    client = get_client()
    span_input: dict[str, Any] = {
        "scenario": scenario.name,
        "target_scenario": scenario.target_scenario,
    }
    if is_paired:
        span_input["baseline_scenario"] = scenario.baseline_scenario

    metadata: dict[str, Any] = {
        "scenario_name": scenario.name,
        "expected_to_pass": scenario.expected_to_pass,
        "target_run_id": target_run["run_id"],
        "scoring_mode": "llm_judge" if llm_judgment is not None else "keyword",
    }
    if comparison is not None:
        metadata["flow_count_delta"] = comparison.get("flow_count_delta")
        metadata["has_count_divergence"] = comparison.get("has_count_divergence")
    if baseline_run is not None:
        metadata["baseline_run_id"] = baseline_run["run_id"]
    if judge_error is not None:
        metadata["judge_error"] = judge_error
    if correctness_error is not None:
        metadata["correctness_error"] = correctness_error
    if correctness_judgment is not None:
        metadata["correctness_verdict"] = correctness_judgment.verdict.value

    span_output: dict[str, Any] = {
        "overall_pass": primary_score.overall_pass,
        "criteria": dict(primary_score.criteria),
        "rationale": primary_score.rationale,
        "keyword_score": {
            "overall_pass": keyword_score.overall_pass,
            "criteria": dict(keyword_score.criteria),
        },
    }
    if llm_judgment is not None:
        span_output["llm_judgment"] = {
            "overall_pass": llm_judgment.overall_pass,
            "judge_model": llm_judgment.judge_model,
            "criteria": [
                {"name": c.name, "passed": c.passed, "rationale": c.rationale}
                for c in llm_judgment.criteria
            ],
        }
    if correctness_judgment is not None:
        span_output["correctness_judgment"] = {
            "verdict": correctness_judgment.verdict.value,
            "agent_diagnosis_summary": correctness_judgment.agent_diagnosis_summary,
            "rationale": correctness_judgment.rationale,
            "judge_model": correctness_judgment.judge_model,
        }

    client.update_current_span(
        input=span_input,
        output=span_output,
        metadata=metadata,
    )
    client.score_current_trace(
        name=SCORE_NAME,
        value=1.0 if primary_score.overall_pass else 0.0,
        comment=primary_score.rationale,
    )
    if correctness_judgment is not None:
        # Separate Langfuse trace score so the diagnosis-correctness axis
        # is queryable independently of the rubric axis. Score value:
        # 1.0 for CORRECT, 0.0 for WRONG, 0.5 for NO_DIAGNOSIS — the mid
        # value reflects that NO_DIAGNOSIS is a distinct epistemic
        # stance, not a half-failure; readers should consult the verdict
        # string (in the comment) rather than treating the numeric as
        # ordinal.
        verdict_value = {
            "CORRECT": 1.0,
            "NO_DIAGNOSIS": 0.5,
            "WRONG": 0.0,
        }.get(correctness_judgment.verdict.value, 0.0)
        client.score_current_trace(
            name=CORRECTNESS_SCORE_NAME,
            value=verdict_value,
            comment=(
                f"{correctness_judgment.verdict.value}: "
                f"{correctness_judgment.agent_diagnosis_summary}"
            ),
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
        score=primary_score,
        user_prompt=user_prompt,
        langfuse_trace_id=trace_id,
        tool_calls=tool_calls,
        iterations=iterations,
        keyword_score=keyword_score,
        llm_judgment=llm_judgment,
        judge_error=judge_error,
        correctness_judgment=correctness_judgment,
        correctness_error=correctness_error,
    )


def _default_run_id_prefix(scenario_name: str) -> str:
    """Generate a UUID-prefixed run_id that does NOT embed the scenario
    name. The substrate's adapter exposes the trace_dir path on tool
    responses (the harness needs it to wire compare_runs); embedding
    the EvalScenario name in the prefix would leak the answer key the
    same way the Doppelgänger Driver's old auto-run_id pattern did
    (caught 2026-05-09, fixed 2026-05-10). The scenario_name is
    accepted but ignored — kept in the signature so future tooling
    that needs scenario-aware naming on the *operator* side (logs,
    not agent-facing data) can branch on it."""
    del scenario_name  # intentionally unused — see docstring
    return f"run-{uuid.uuid4().hex[:12]}"


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
    if result.tool_calls:
        lines.append("")
        lines.append(
            f"--- tool calls ({len(result.tool_calls)} across "
            f"{result.iterations} iterations) ---"
        )
        for i, tc in enumerate(result.tool_calls, start=1):
            lines.append(f"  {i}. {tc.name}({tc.input}) -> {len(tc.output_serialized)} chars")
    lines.append("")
    lines.append(
        f"--- model output ({result.completion.input_tokens}->"
        f"{result.completion.output_tokens} tokens) ---"
    )
    lines.append(result.completion.text)
    lines.append("")
    if result.llm_judgment is not None or result.keyword_score is not None:
        # Keyword-vs-LLM calibration table — the actual signal
        # we care about while LLM scoring is on probation.
        kw = result.keyword_score
        llm = result.llm_judgment
        kw_criteria = kw.criteria if kw is not None else {}
        llm_criteria = (
            {c.name: c.passed for c in llm.criteria} if llm is not None else {}
        )
        all_names = list(kw_criteria.keys() or llm_criteria.keys())
        lines.append("--- scoring (keyword | LLM) ---")
        for name in all_names:
            kw_str = "PASS" if kw_criteria.get(name) else "FAIL"
            if llm is None:
                llm_str = "n/a"
            else:
                llm_str = "PASS" if llm_criteria.get(name) else "FAIL"
            lines.append(f"  {name}: {kw_str} | {llm_str}")
        kw_overall = "PASS" if kw and kw.overall_pass else "FAIL"
        if llm is None:
            llm_overall = "n/a"
        else:
            llm_overall = "PASS" if llm.overall_pass else "FAIL"
        lines.append("")
        lines.append(f"overall:  keyword={kw_overall} | LLM={llm_overall}")
        if result.judge_error is not None:
            lines.append(f"judge_error: {result.judge_error}")
        if llm is not None:
            lines.append("")
            lines.append("--- LLM judge rationale ---")
            for c in llm.criteria:
                marker = "PASS" if c.passed else "FAIL"
                lines.append(f"  [{marker}] {c.name}: {c.rationale}")
            lines.append("")
            lines.append(f"  overall ({llm.judge_model}): {llm.overall_rationale}")
    else:
        lines.append("--- scoring ---")
        for criterion, passed in score.criteria.items():
            lines.append(f"  {criterion}: {'PASS' if passed else 'FAIL'}")
        lines.append("")
        lines.append(f"overall_pass: {score.overall_pass}")
    lines.append("")
    lines.append(
        f"primary_overall_pass: {score.overall_pass} "
        f"({'LLM judge' if result.llm_judgment is not None else 'keyword fallback'})"
    )
    if result.correctness_judgment is not None:
        cj = result.correctness_judgment
        lines.append("")
        lines.append("--- diagnosis correctness (orthogonal to rubric) ---")
        lines.append(f"  verdict: {cj.verdict.value}")
        lines.append(f"  agent's stated diagnosis: {cj.agent_diagnosis_summary}")
        lines.append(f"  rationale: {cj.rationale}")
    elif result.correctness_error is not None:
        lines.append("")
        lines.append(f"--- diagnosis correctness: SKIPPED ({result.correctness_error}) ---")
    if result.langfuse_trace_id:
        lines.append(f"langfuse_trace_id: {result.langfuse_trace_id}")
    return "\n".join(lines)


__all__ = [
    "EVAL_SPAN_NAME",
    "SCORE_NAME",
    "format_eval_summary",
    "run_eval",
]
