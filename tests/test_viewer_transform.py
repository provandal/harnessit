"""Tests for harnessit.viewer.transform — span tree → sequence diagram.

Hermetic: builds Span instances by hand and asserts on the resulting
TraceView shape. No Langfuse dependency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from harnessit.viewer.transform import (
    Lane,
    Message,
    Span,
    TraceScore,
    TraceView,
    build_trace_view,
    span_name_to_lane,
)


_T0 = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)


def _t(seconds: float) -> datetime:
    return _T0 + timedelta(seconds=seconds)


def _span(
    *,
    id: str,
    name: str,
    parent_id: str | None = None,
    type: str = "SPAN",
    start: float = 0.0,
    end: float | None = None,
    input: Any = None,
    output: Any = None,
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
) -> Span:
    return Span(
        id=id,
        name=name,
        type=type,
        parent_id=parent_id,
        start_time=_t(start),
        end_time=_t(end) if end is not None else None,
        input=input,
        output=output,
        metadata=metadata or {},
        model=model,
    )


# ---------- span name → lane mapping ----------

def test_span_name_to_lane_known_names():
    assert span_name_to_lane("harnessit.eval.judge") is Lane.JUDGE
    assert span_name_to_lane("harnessit.tools.get_topology") is Lane.TOOL
    assert span_name_to_lane("harnessit.tools.future_counters") is Lane.TOOL
    assert span_name_to_lane("harnessit.naked_model.complete") is Lane.AGENT
    assert span_name_to_lane("harnessit.tool_use.complete") is Lane.AGENT


def test_span_name_to_lane_unknown_falls_back_to_other():
    """Forward-compatible: a future stage's spans don't crash the
    viewer; they land in OTHER and stay visible."""
    assert span_name_to_lane("harnessit.future.coolnewthing") is Lane.OTHER
    assert span_name_to_lane("totally.unrelated") is Lane.OTHER


def test_lane_ordering_is_canonical():
    """The diagram column order is fixed left-to-right; test pins it
    so a renderer regression that swaps columns is caught."""
    order = Lane.ordered_for_diagram()
    assert order[0] is Lane.USER
    assert order[1] is Lane.AGENT
    assert order[-1] is Lane.OTHER
    assert Lane.JUDGE in order


# ---------- naked-model trace shape ----------

def test_naked_model_trace_produces_user_request_response_pair():
    """The Stage 2 naked-model path: user -> agent (request) and
    agent -> user (response). No tool calls, no judge."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=10)
    model = _span(
        id="m1", name="harnessit.naked_model.complete",
        parent_id="root", start=0.5, end=8,
        output={"text": "triage plan: pass"}, model="claude-opus-4-7",
    )
    view = build_trace_view(
        trace_id="trace-1",
        trace_name="microburst-symptom-only",
        timestamp=_T0,
        trace_input="step time on host 11.0.0.1 up 1.5x",
        trace_output="triage plan: pass",
        trace_metadata={"scenario_name": "microburst-symptom-only"},
        spans=[eval_root, model],
    )

    # Two messages: User -> Agent (help ticket), Agent -> User (response)
    assert len(view.messages) == 2
    assert view.messages[0].from_lane is Lane.USER
    assert view.messages[0].to_lane is Lane.AGENT
    assert view.messages[0].label == "help ticket"
    assert view.messages[1].from_lane is Lane.AGENT
    assert view.messages[1].to_lane is Lane.USER
    assert view.messages[1].is_response is True
    assert view.messages[1].payload["model"] == "claude-opus-4-7"
    # Active lanes only include those actually used (no Tool, Judge, etc.)
    assert Lane.USER in view.active_lanes
    assert Lane.AGENT in view.active_lanes
    assert Lane.TOOL not in view.active_lanes
    assert Lane.JUDGE not in view.active_lanes


def test_user_prompt_extracted_from_trace_input():
    """The ticket text on the User -> Agent arrow should be the
    trace-level input, not an internal repr of a dict."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=5)
    model = _span(
        id="m1", name="harnessit.naked_model.complete",
        parent_id="root", start=0.5, end=4, output="ok",
    )
    view = build_trace_view(
        trace_id="t",
        trace_name="x",
        timestamp=_T0,
        trace_input="actual user ticket text here",
        trace_output="ok",
        trace_metadata=None,
        spans=[eval_root, model],
    )
    assert view.user_prompt == "actual user ticket text here"
    assert view.messages[0].payload["user_prompt"] == "actual user ticket text here"


def test_help_ticket_payload_includes_system_prompt_and_user_prompt():
    """The User -> Agent message must surface the full agent context
    — system prompt and user prompt both — so the rendered HTML
    shows what the agent actually received from the harness, not
    just the help-ticket text."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=5)
    model = _span(
        id="m1", name="harnessit.naked_model.complete",
        parent_id="root", start=0.5, end=4,
        input={
            "system": "You are a network-investigation assistant for an RDMA fabric.",
            "user": "host 11.0.0.1 slow",
        },
        output="ok",
    )
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        trace_input={"scenario": "x", "target_scenario": "y"},
        trace_output="ok",
        trace_metadata=None,
        spans=[eval_root, model],
    )
    payload = view.messages[0].payload
    assert payload["user_prompt"] == "host 11.0.0.1 slow"
    assert "system_prompt" in payload
    assert "network-investigation assistant" in payload["system_prompt"]


def test_help_ticket_payload_includes_tools_available_for_tool_use():
    """For tool-use scenarios, the User -> Agent payload must list
    the tools the agent had access to. Without this, the rendered
    HTML can't distinguish a with-tool variant from a naked variant
    on the opening arrow alone."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=10)
    model = _span(
        id="m1", name="harnessit.tool_use.complete",
        parent_id="root", start=0.5, end=8,
        input={
            "system": "you are an SRE",
            "user": "host slow",
            "tools": ["get_topology"],
        },
        output={"text": "leaf 0 bottleneck"},
    )
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        trace_input={"scenario": "x", "target_scenario": "y"},
        trace_output="leaf 0 bottleneck",
        trace_metadata=None,
        spans=[eval_root, model],
    )
    payload = view.messages[0].payload
    assert payload["tools_available"] == ["get_topology"]


def test_help_ticket_payload_omits_tools_when_naked_model():
    """Naked-model traces must NOT add a ``tools_available`` field
    (an empty list would be misleading; absence of the field is
    correct). Lets the renderer suppress the tools-row cleanly."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=5)
    model = _span(
        id="m1", name="harnessit.naked_model.complete",
        parent_id="root", start=0.5, end=4,
        input={"system": "sys", "user": "u"},
        output="ok",
    )
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        trace_input={"scenario": "x", "target_scenario": "y"},
        trace_output="ok",
        trace_metadata=None,
        spans=[eval_root, model],
    )
    assert "tools_available" not in view.messages[0].payload


def test_user_prompt_extracted_from_dict_input_with_user_field():
    """Langfuse sometimes stores input as {'system': ..., 'user': ...}.
    Extract the user field rather than dumping the whole dict."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=5)
    model = _span(
        id="m1", name="harnessit.naked_model.complete",
        parent_id="root", start=0.5, end=4, output="ok",
    )
    view = build_trace_view(
        trace_id="t",
        trace_name="x",
        timestamp=_T0,
        trace_input={"system": "you are an SRE", "user": "host slow"},
        trace_output="ok",
        trace_metadata=None,
        spans=[eval_root, model],
    )
    assert view.user_prompt == "host slow"


# ---------- tool-use trace shape ----------

def test_tool_use_trace_walks_tool_children_in_order():
    """The Stage 3 tool-use path: agent -> tool (request) and
    tool -> agent (result), nested between the user-prompt arrival
    and the agent's final response. Multiple tool calls preserved
    in start-time order."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=20)
    model = _span(
        id="m1", name="harnessit.tool_use.complete",
        parent_id="root", start=0.5, end=18,
        output={"text": "leaf 0 is the bottleneck"}, model="claude-opus-4-7",
    )
    tool_a = _span(
        id="ta", name="harnessit.tools.get_topology",
        parent_id="m1", start=2, end=4,
        input={"agent_args": {}, "bound_scenario": "microburst"},
        output={"shape": "leaf-spine", "leaves": 2},
        metadata={"source": "adapter.scenario_topology", "confidence": "high"},
    )
    tool_b = _span(
        id="tb", name="harnessit.tools.future_counters",  # hypothetical second tool
        parent_id="m1", start=6, end=8,
        input={"agent_args": {"port": "leaf0-host0"}},
        output={"pfc_pause_count": 0, "ecn_marks": 1234},
    )
    view = build_trace_view(
        trace_id="t",
        trace_name="microburst-with-topology-tool",
        timestamp=_T0,
        trace_input="ticket",
        trace_output="leaf 0 is the bottleneck",
        trace_metadata={"scenario_name": "microburst-with-topology-tool"},
        spans=[eval_root, model, tool_a, tool_b],
    )

    # Expected message ordering by timestamp:
    #   0: User -> Agent (help ticket)            t=0 (eval root start)
    #   1: Agent -> Tool  (get_topology request)  t=2
    #   2: Tool -> Agent  (get_topology result)   t=4
    #   3: Agent -> Tool  (future_counters req)   t=6
    #   4: Tool -> Agent  (future_counters res)   t=8
    #   5: Agent -> User  (final response)        t=18 (model end)
    labels = [(m.from_lane, m.to_lane, m.label, m.is_response) for m in view.messages]
    assert labels == [
        (Lane.USER, Lane.AGENT, "help ticket", False),
        (Lane.AGENT, Lane.TOOL, "get_topology", False),
        (Lane.TOOL, Lane.AGENT, "get_topology → result", True),
        (Lane.AGENT, Lane.TOOL, "future_counters", False),
        (Lane.TOOL, Lane.AGENT, "future_counters → result", True),
        (Lane.AGENT, Lane.USER, "triage response", True),
    ]
    # Tool result message should preserve envelope metadata for source/staleness
    tool_result = view.messages[2]
    assert tool_result.payload["source"] == "adapter.scenario_topology"
    assert tool_result.payload["confidence"] == "high"
    assert Lane.TOOL in view.active_lanes


# ---------- judge ----------

def test_judge_span_produces_request_verdict_pair_and_extracts_criteria():
    """harnessit.eval.judge → Agent -> Judge (evaluate) and
    Judge -> Agent (verdict). Per-criterion rationale lifted onto
    the TraceView for inline rendering."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=20)
    model = _span(
        id="m1", name="harnessit.naked_model.complete",
        parent_id="root", start=0.5, end=10, output="response",
    )
    judge = _span(
        id="j1", name="harnessit.eval.judge",
        parent_id="root", start=12, end=18,
        output={
            "overall_pass": True,
            "overall_rationale": "All five criteria pass",
            "criteria": [
                {"name": "considers_multiple_hypotheses", "passed": True, "rationale": "Names 4 classes"},
                {"name": "names_telemetry_to_query", "passed": True, "rationale": "Lists 6 sources"},
                {"name": "synthesizes_available_context", "passed": True, "rationale": "Cites leaf 0"},
            ],
        },
        metadata={"judge_model": "claude-opus-4-7"},
    )
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        trace_input="ticket", trace_output="response",
        trace_metadata=None,
        spans=[eval_root, model, judge],
    )

    judge_messages = [m for m in view.messages if Lane.JUDGE in (m.from_lane, m.to_lane)]
    assert len(judge_messages) == 2
    assert judge_messages[0].from_lane is Lane.AGENT
    assert judge_messages[0].to_lane is Lane.JUDGE
    assert judge_messages[1].from_lane is Lane.JUDGE
    assert judge_messages[1].is_response is True
    assert "PASS" in judge_messages[1].label

    # Per-criterion rationale lifted to TraceView for inline rendering
    assert len(view.judge_criteria) == 3
    names = {c["name"] for c in view.judge_criteria}
    assert "synthesizes_available_context" in names
    assert view.judge_rationale == "All five criteria pass"
    assert view.judge_model == "claude-opus-4-7"


def test_judge_verdict_label_reflects_overall_pass_false():
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=20)
    judge = _span(
        id="j1", name="harnessit.eval.judge",
        parent_id="root", start=2, end=4,
        output={"overall_pass": False, "criteria": [], "overall_rationale": "fail"},
    )
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        trace_input="ticket", trace_output="resp",
        trace_metadata=None,
        spans=[eval_root, judge],
    )
    judge_messages = [m for m in view.messages if Lane.JUDGE in (m.from_lane, m.to_lane)]
    assert any("FAIL" in m.label for m in judge_messages)


# ---------- defensive / edge cases ----------

def test_unknown_span_routed_to_other_lane_not_dropped():
    """Forward-compatible: a future Stage's spans appear in OTHER
    rather than disappearing silently."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=10)
    weird = _span(
        id="w1", name="harnessit.future.something_new",
        parent_id="root", start=2, end=3,
    )
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        trace_input="t", trace_output="o",
        trace_metadata=None,
        spans=[eval_root, weird],
    )
    other_msgs = [m for m in view.messages if m.from_lane is Lane.OTHER]
    assert len(other_msgs) == 1
    assert Lane.OTHER in view.active_lanes


def test_empty_spans_produce_minimal_view():
    """A trace with only the eval-root span (e.g., scenario crashed
    before model call) should still render — header + user prompt."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=1)
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        trace_input="prompt", trace_output=None,
        trace_metadata=None,
        spans=[eval_root],
    )
    # Just the User -> Agent help ticket
    assert len(view.messages) == 1
    assert view.messages[0].from_lane is Lane.USER


def test_messages_sorted_stably_by_timestamp():
    """Span order in the input list shouldn't matter — the view
    sorts by timestamp. Tool-use ordering depends on this."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=20)
    model = _span(
        id="m1", name="harnessit.tool_use.complete",
        parent_id="root", start=0.5, end=18, output="response",
    )
    tool_late = _span(
        id="t2", name="harnessit.tools.get_topology",
        parent_id="m1", start=10, end=12,
    )
    tool_early = _span(
        id="t1", name="harnessit.tools.get_topology",
        parent_id="m1", start=2, end=4,
    )
    # Pass the late tool first to confirm sorting kicks in
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        trace_input="t", trace_output="o",
        trace_metadata=None,
        spans=[eval_root, model, tool_late, tool_early],
    )
    timestamps = [m.timestamp for m in view.messages]
    assert timestamps == sorted(timestamps), (
        f"messages not sorted by timestamp: {timestamps}"
    )


def test_trace_view_active_lanes_only_contain_used_lanes():
    """A naked-model trace shouldn't list Tool/Judge/Substrate as
    active lanes — that'd add empty columns to the diagram."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=5)
    model = _span(
        id="m1", name="harnessit.naked_model.complete",
        parent_id="root", start=0, end=4, output="r",
    )
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        trace_input="t", trace_output="r",
        trace_metadata=None,
        spans=[eval_root, model],
    )
    assert set(view.active_lanes) == {Lane.USER, Lane.AGENT}


def test_eval_root_metadata_merges_into_trace_metadata():
    """Stage 3's runner sets scenario_name on the eval-root span
    (via update_current_span), not on the trace's top-level metadata.
    The transform must pick it up so the viewer's title isn't 'harnessit.eval.run'."""
    eval_root = _span(
        id="root", name="harnessit.eval.run", start=0, end=10,
        metadata={
            "scenario_name": "microburst-with-topology-tool",
            "scoring_mode": "llm_judge",
            "target_run_id": "abc__target",
        },
    )
    view = build_trace_view(
        trace_id="t",
        trace_name="harnessit.eval.run",  # the @observe decorator's name
        timestamp=_T0,
        trace_input="ticket",
        trace_output="response",
        trace_metadata=None,  # trace-level metadata is None / empty
        spans=[eval_root],
    )
    assert view.scenario_name == "microburst-with-topology-tool"
    assert view.eval_metadata.get("scoring_mode") == "llm_judge"
    assert view.eval_metadata.get("target_run_id") == "abc__target"


def test_scenario_name_falls_back_to_trace_input_scenario():
    """When neither trace.metadata nor eval-root.metadata has
    scenario_name, fall back to trace.input.scenario — pre-Stage-3-
    LLM-judge traces only set it as span input."""
    eval_root = _span(
        id="root", name="harnessit.eval.run", start=0, end=10,
        # No scenario_name in metadata
    )
    view = build_trace_view(
        trace_id="t",
        trace_name="harnessit.eval.run",
        timestamp=_T0,
        # trace.input shape from runner.py: {scenario, target_scenario}
        trace_input={"scenario": "microburst-with-topology-tool", "target_scenario": "microburst"},
        trace_output=None,
        trace_metadata=None,
        spans=[eval_root],
    )
    assert view.scenario_name == "microburst-with-topology-tool"


def test_user_prompt_falls_back_to_model_span_user_input():
    """trace.input is the eval-root span's input dict {scenario,
    target_scenario}, NOT the user prompt. The actual help ticket
    lives on the model span's input.user — the viewer must pull
    from there when trace.input doesn't have a user field."""
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=10)
    model = _span(
        id="m1", name="harnessit.naked_model.complete",
        parent_id="root", start=0.5, end=8,
        input={
            "system": "you are a network-investigation assistant",
            "user": "step time on host 11.0.0.1 up 1.5x",
        },
        output="response",
    )
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        # Real-world shape: trace.input is the eval-span's input dict
        trace_input={"scenario": "microburst-symptom-only", "target_scenario": "microburst"},
        trace_output="response",
        trace_metadata=None,
        spans=[eval_root, model],
    )
    assert view.user_prompt == "step time on host 11.0.0.1 up 1.5x"
    assert view.messages[0].payload["user_prompt"] == "step time on host 11.0.0.1 up 1.5x"


def test_eval_root_metadata_does_not_overwrite_trace_metadata():
    """If the trace's top-level metadata also has scenario_name, the
    trace's value wins (it's authored explicitly by the runner if set
    at all). Use setdefault semantics."""
    eval_root = _span(
        id="root", name="harnessit.eval.run", start=0, end=10,
        metadata={"scenario_name": "from-span"},
    )
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        trace_input="t", trace_output="o",
        trace_metadata={"scenario_name": "from-trace"},
        spans=[eval_root],
    )
    assert view.scenario_name == "from-trace"


def test_trace_scores_passed_through():
    eval_root = _span(id="root", name="harnessit.eval.run", start=0, end=5)
    score = TraceScore(
        name="harnessit.eval.overall_pass", value=1.0, comment="passed all"
    )
    view = build_trace_view(
        trace_id="t", trace_name="x", timestamp=_T0,
        trace_input="t", trace_output="o",
        trace_metadata=None,
        spans=[eval_root],
        scores=[score],
    )
    assert len(view.scores) == 1
    assert view.scores[0].value == 1.0
    assert view.scores[0].comment == "passed all"
