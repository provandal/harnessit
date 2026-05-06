"""Tests for the silent-drops localization scenario.

Unit tests verify the prompt includes §3.8 substrate signals and that
the scoring layer adds the localization rubric on top of the four
shared rubrics. Live end-to-end test runs the full scenario against
the real substrate + real Anthropic API + real Langfuse Cloud.
"""

from __future__ import annotations

import pytest

from harnessit.eval.runner import format_eval_summary, run_eval
from harnessit.model import Completion, ModelClient
from harnessit.scenarios.silent_drops import (
    SCENARIO_NAME,
    build_user_prompt,
    score,
    silent_drops_localization,
)


def _completion(text: str) -> Completion:
    return Completion(
        text=text,
        model="claude-opus-4-7",
        input_tokens=20,
        output_tokens=40,
        stop_reason="end_turn",
    )


def _comparison() -> dict:
    return {
        "flow_count_delta": -8,
        "has_count_divergence": True,
        "fct_p50_delta_ns": 5_000,
        "fct_p99_delta_ns": 80_000,
        "fct_p999_delta_ns": 200_000,
        "baseline_summary": {
            "total": 255, "completed": 255, "incomplete": 0,
            "by_status": {"COMPLETED": 255}, "fct": {"p50_ns": 12_000},
        },
        "injected_summary": {
            "total": 247, "completed": 244, "incomplete": 3,
            "by_status": {"COMPLETED": 244, "INCOMPLETE_FLOW": 3},
            "fct": {"p50_ns": 17_000},
        },
        "findings": ["flow count divergence detected", "tail latency shifted"],
    }


def test_factory_returns_correct_shape():
    scenario = silent_drops_localization()
    assert scenario.name == SCENARIO_NAME
    assert scenario.baseline_scenario == "spike-burst-baseline"
    assert scenario.injected_scenario == "spike-burst-silent-drops"
    assert scenario.expected_to_pass is False


def test_user_prompt_includes_primary_signal():
    """flow_count_delta is the §3.8 primary failure signature."""
    prompt = build_user_prompt(_comparison())
    assert "flow_count_delta: -8" in prompt
    assert "has_count_divergence: True" in prompt


def test_user_prompt_includes_distribution_signal():
    prompt = build_user_prompt(_comparison())
    assert "p50:" in prompt
    assert "p99:" in prompt
    assert "p999:" in prompt
    assert "80000" in prompt  # p99 delta value


def test_user_prompt_includes_incomplete_flow_annotation():
    prompt = build_user_prompt(_comparison())
    assert "incomplete=3" in prompt


def test_user_prompt_includes_findings():
    prompt = build_user_prompt(_comparison())
    assert "flow count divergence detected" in prompt
    assert "tail latency shifted" in prompt


def test_user_prompt_does_not_include_per_flow_data():
    """Per-flow data is intentionally absent — that's what makes the
    naked-model failure mode meaningful."""
    prompt = build_user_prompt(_comparison())
    # No flow tuples should appear in the rendered prompt
    assert "10.0.0" not in prompt  # IP-prefix baseline scenarios use


def test_score_perfect_answer_with_localization_caveat_passes():
    """The honest naked-model answer: identifies failure + asks for per-flow data."""
    text = (
        "I see silent drops in the injected run. The flow-count delta is -8, "
        "meaning 8 flows are missing. There are also incomplete flows in "
        "the injected run. The p99 tail shifts. To localize the affected "
        "flows specifically, I would need per-flow data — the comparison "
        "summary does not include the flow tuples."
    )
    result = score(_comparison(), _completion(text))
    assert result.criteria["identifies_failure_class"] is True
    assert result.criteria["cites_flow_count_delta"] is True
    assert result.criteria["acknowledges_incomplete_flows"] is True
    assert result.criteria["cites_distribution_signal"] is True
    assert result.criteria["localizes_affected_flows"] is True
    assert result.overall_pass is True


def test_score_naked_failure_mode_misses_localization():
    """Model identifies failure class, but doesn't address localization."""
    text = (
        "Silent drops causing fewer flows. The p99 tail shifts. Some "
        "flows are incomplete in the injected run."
    )
    result = score(_comparison(), _completion(text))
    assert result.criteria["identifies_failure_class"] is True
    assert result.criteria["cites_flow_count_delta"] is True
    assert result.criteria["acknowledges_incomplete_flows"] is True
    assert result.criteria["cites_distribution_signal"] is True
    assert result.criteria["localizes_affected_flows"] is False
    assert result.overall_pass is False


def test_score_concrete_tuple_passes_localization():
    text = (
        "Silent drops affecting flows. I see 10.0.0.1:4444 missing from "
        "injected. flow-count delta -8. p99 tail shifts. Incomplete flows "
        "are visible."
    )
    result = score(_comparison(), _completion(text))
    assert result.criteria["localizes_affected_flows"] is True


def test_score_vague_answer_fails_everything():
    text = "Something is different but I can't tell what."
    result = score(_comparison(), _completion(text))
    assert result.overall_pass is False
    # All criteria should be False or absent
    for passed in result.criteria.values():
        assert passed is False


# ---------- live end-to-end ----------

@pytest.mark.requires_substrate
@pytest.mark.requires_anthropic
@pytest.mark.requires_langfuse
async def test_silent_drops_end_to_end_real_substrate():
    """The Stage 2 closing test: real substrate, real Opus call, real Langfuse.

    Verifies that all three integration points fit together end-to-end.
    The score may pass or fail — that's empirical. The eval framework
    producing a structured result with §3.8-aligned grading is the
    actual deliverable.
    """
    from harnessit.config import load_settings
    from harnessit.substrate import DoppelgangerClient
    from harnessit.tracing import flush_langfuse, init_langfuse

    settings = load_settings()
    init_langfuse(settings)

    scenario = silent_drops_localization()
    async with DoppelgangerClient.connect() as substrate:
        model_client = ModelClient.from_settings(settings)
        result = await run_eval(
            scenario=scenario,
            substrate=substrate,
            model_client=model_client,
            run_id_prefix="test-e2e",
        )
    flush_langfuse()

    # Structural assertions only — the score is empirical.
    assert result.scenario_name == SCENARIO_NAME
    assert result.baseline_run_id == "test-e2e__baseline"
    assert result.injected_run_id == "test-e2e__injected"
    assert result.comparison.get("flow_count_delta") is not None
    assert result.completion.text  # model produced output
    assert result.langfuse_trace_id  # span landed in Langfuse
    assert result.score.criteria  # scoring produced structured output

    # Echo the result so we can read it in CI logs / capture in journal.
    print("\n" + format_eval_summary(result))
