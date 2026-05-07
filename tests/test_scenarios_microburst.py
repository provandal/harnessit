"""Tests for the microburst-localization scenarios.

Unit tests verify the prompt shape (no failure-class menu, no
pre-computed comparison, quantitative anchor present, topology
preamble only in the with-topology variant). Live end-to-end runs
fire the full stack: real substrate → real Anthropic → real Langfuse.
"""

from __future__ import annotations

import pytest

from harnessit.eval.runner import format_eval_summary, run_eval
from harnessit.eval.types import EvalContext
from harnessit.model import ModelClient
from harnessit.scenarios.microburst import (
    SYSTEM_PROMPT,
    TOPOLOGY_PREAMBLE,
    USER_TICKET,
    microburst_symptom_only,
    microburst_with_topology,
    microburst_with_topology_tool,
)


def _ctx() -> EvalContext:
    return EvalContext(
        target_run={"run_id": "x", "trace_dir": "traces/x"},
        baseline_run=None,
        comparison=None,
        scenario_metadata={},
    )


# ---------- shape tests ----------

def test_symptom_only_factory_shape():
    scenario = microburst_symptom_only()
    assert scenario.name == "microburst-symptom-only"
    assert scenario.target_scenario == "microburst"
    assert scenario.baseline_scenario is None
    assert scenario.expected_to_pass is False
    assert scenario.system_prompt == SYSTEM_PROMPT


def test_with_topology_factory_shape():
    scenario = microburst_with_topology()
    assert scenario.name == "microburst-with-topology"
    assert scenario.target_scenario == "microburst"
    assert scenario.baseline_scenario is None


def test_with_topology_tool_factory_shape():
    """Stage 3 closing test scenario: same target as the other two,
    expected_to_pass=True (testing whether the harness closes the gap),
    uses_tools=True."""
    scenario = microburst_with_topology_tool()
    assert scenario.name == "microburst-with-topology-tool"
    assert scenario.target_scenario == "microburst"
    assert scenario.baseline_scenario is None
    assert scenario.uses_tools is True
    assert scenario.expected_to_pass is True


def test_with_topology_tool_uses_same_user_ticket_as_symptom_only():
    """The tool variant must share the symptom-only prompt verbatim —
    if it leaked topology in the prompt as well, the eval wouldn't
    isolate 'topology came from the tool, not the prompt.'"""
    tool_scenario = microburst_with_topology_tool()
    symptom_scenario = microburst_symptom_only()
    tool_prompt = tool_scenario.build_user_prompt(_ctx())
    symptom_prompt = symptom_scenario.build_user_prompt(_ctx())
    assert tool_prompt == symptom_prompt
    # And it should NOT contain the topology preamble
    assert TOPOLOGY_PREAMBLE not in tool_prompt


# ---------- prompt content ----------

def test_symptom_only_prompt_is_user_ticket():
    scenario = microburst_symptom_only()
    prompt = scenario.build_user_prompt(_ctx())
    assert USER_TICKET in prompt
    # No topology preamble — that's the with-topology variant's job
    assert "leaf" not in prompt.lower()
    assert "spine" not in prompt.lower()


def test_with_topology_prompt_includes_preamble_and_ticket():
    scenario = microburst_with_topology()
    prompt = scenario.build_user_prompt(_ctx())
    assert TOPOLOGY_PREAMBLE in prompt
    assert USER_TICKET in prompt
    assert "leaf 0" in prompt
    assert "spine" in prompt
    # Topology comes BEFORE the ticket
    assert prompt.index(TOPOLOGY_PREAMBLE) < prompt.index(USER_TICKET)


def test_user_ticket_includes_quantitative_anchor():
    """The 'step time up 1.5x' anchor matches the recon ground truth."""
    assert "1.5x" in USER_TICKET
    assert "11.0.0.1" in USER_TICKET


def test_system_prompt_is_role_only_no_failure_class_menu():
    """Critical: the v1 mistake was leaking the answer key in the
    system prompt. v2 is role-only."""
    text = SYSTEM_PROMPT.lower()
    # No enumeration of failure classes
    forbidden = [
        "silent drop",
        "microburst",
        "pfc storm",
        "asymmetric path",
        "hash polarization",
        "link flap",
        "buffer misconfig",
    ]
    for term in forbidden:
        assert term not in text, f"system prompt leaks failure class: {term!r}"


def test_user_ticket_does_not_leak_failure_class():
    text = USER_TICKET.lower()
    forbidden = ["microburst", "incast", "pfc", "ecmp", "silent drop"]
    for term in forbidden:
        assert term not in text, f"user ticket leaks: {term!r}"


def test_user_ticket_does_not_provide_comparison_data():
    """v1 leaked compare_runs output as input. v2's prompt is symptom-only."""
    text = USER_TICKET.lower()
    forbidden = ["fct_p", "flow_count_delta", "percentile", "p99", "incomplete_flow"]
    for term in forbidden:
        assert term not in text, f"user ticket leaks comparison data: {term!r}"


# ---------- live end-to-end ----------

@pytest.mark.requires_substrate
@pytest.mark.requires_anthropic
@pytest.mark.requires_langfuse
async def test_microburst_symptom_only_end_to_end():
    """Stage 2 closing test for symptom-only variant."""
    from harnessit.config import load_settings
    from harnessit.substrate import DoppelgangerClient
    from harnessit.tracing import flush_langfuse, init_langfuse

    settings = load_settings()
    init_langfuse(settings)

    scenario = microburst_symptom_only()
    async with DoppelgangerClient.connect() as substrate:
        model_client = ModelClient.from_settings(settings)
        result = await run_eval(
            scenario=scenario,
            substrate=substrate,
            model_client=model_client,
            run_id_prefix="e2e-symptom-only",
        )
    flush_langfuse()

    assert result.scenario_name == "microburst-symptom-only"
    assert result.target_run_id == "e2e-symptom-only__target"
    assert result.baseline_run_id is None
    assert result.comparison is None
    assert result.completion.text
    assert result.langfuse_trace_id
    assert result.score.criteria

    print("\n" + format_eval_summary(result))


@pytest.mark.requires_substrate
@pytest.mark.requires_anthropic
@pytest.mark.requires_langfuse
async def test_microburst_with_topology_end_to_end():
    """Stage 2 closing test for the with-topology variant."""
    from harnessit.config import load_settings
    from harnessit.substrate import DoppelgangerClient
    from harnessit.tracing import flush_langfuse, init_langfuse

    settings = load_settings()
    init_langfuse(settings)

    scenario = microburst_with_topology()
    async with DoppelgangerClient.connect() as substrate:
        model_client = ModelClient.from_settings(settings)
        result = await run_eval(
            scenario=scenario,
            substrate=substrate,
            model_client=model_client,
            run_id_prefix="e2e-with-topology",
        )
    flush_langfuse()

    assert result.scenario_name == "microburst-with-topology"
    assert result.target_run_id == "e2e-with-topology__target"
    assert result.baseline_run_id is None
    assert result.completion.text
    assert result.langfuse_trace_id

    print("\n" + format_eval_summary(result))
