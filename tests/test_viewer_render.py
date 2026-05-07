"""Tests for harnessit.viewer.render — TraceView → HTML string.

Hermetic: build a TraceView in memory, render to HTML, assert on the
HTML structure (Mermaid block, criteria table, message detail blocks).
No browser, no DOM — string-level assertions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from harnessit.viewer.render import _render_mermaid_diagram, render_trace_html
from harnessit.viewer.transform import (
    Lane,
    Message,
    TraceScore,
    TraceView,
)


_T0 = datetime(2026, 5, 7, 13, 0, 0, tzinfo=timezone.utc)


def _make_view(
    *,
    messages=None,
    judge_criteria=(),
    judge_rationale=None,
    judge_model=None,
    scores=(),
    eval_metadata=None,
    scenario_name=None,
) -> TraceView:
    msgs = messages or [
        Message(
            from_lane=Lane.USER,
            to_lane=Lane.AGENT,
            label="help ticket",
            timestamp=_T0,
        ),
        Message(
            from_lane=Lane.AGENT,
            to_lane=Lane.USER,
            label="triage response",
            timestamp=_T0,
            is_response=True,
            payload={"text": "leaf 0 bottleneck"},
        ),
    ]
    used = {m.from_lane for m in msgs} | {m.to_lane for m in msgs}
    return TraceView(
        trace_id="trace-test-id",
        trace_name="test-scenario",
        timestamp=_T0,
        user_prompt="step time on host 11.0.0.1 up 1.5x",
        agent_final_response="leaf 0 bottleneck",
        messages=tuple(msgs),
        active_lanes=tuple(l for l in Lane.ordered_for_diagram() if l in used),
        scores=tuple(scores),
        scenario_name=scenario_name,
        eval_metadata=eval_metadata or {},
        judge_criteria=tuple(judge_criteria),
        judge_rationale=judge_rationale,
        judge_model=judge_model,
    )


# ---------- structural HTML ----------

def test_render_emits_doctype_and_mermaid_cdn():
    """Sanity: produces a valid HTML5 document and pulls Mermaid from CDN."""
    html = render_trace_html(_make_view())
    assert html.startswith("<!DOCTYPE html>")
    assert "mermaid@10" in html
    assert "mermaid.initialize" in html


def test_render_includes_trace_id_in_header():
    html = render_trace_html(_make_view())
    assert "trace-test-id" in html


def test_render_uses_scenario_name_in_title_when_present():
    """The scenario name is preferred over trace_name/trace_id in the
    h1 because it's the human-readable thing."""
    html = render_trace_html(_make_view(scenario_name="microburst-with-topology-tool"))
    assert "microburst-with-topology-tool" in html


# ---------- mermaid sequence diagram ----------

def test_render_mermaid_diagram_has_active_lanes_only():
    """The diagram should declare only lanes referenced by messages
    (no empty columns); naked-model view must not include Tool/Judge."""
    html = render_trace_html(_make_view())
    # The Mermaid block is escaped in HTML, so we look for the
    # participant declarations as escaped text.
    assert "participant USER as User" in html
    assert "participant AGENT as Agent" in html
    assert "participant TOOL" not in html  # not active in this view
    assert "participant JUDGE" not in html


def test_render_mermaid_uses_solid_arrow_for_request_dashed_for_response():
    """Mermaid syntax: ``->>`` for request, ``-->>`` for response.
    Asserted on the pre-escape Mermaid source — the HTML embedding
    escapes ``>`` to ``&gt;`` (Mermaid.js reads textContent which
    un-escapes), so the raw HTML doesn't contain literal ``->>``."""
    diagram_source = _render_mermaid_diagram(_make_view())
    assert "USER->>AGENT" in diagram_source
    assert "AGENT-->>USER" in diagram_source


def test_render_mermaid_label_strips_problematic_characters():
    """Mermaid trips on ``;`` and bare ``:`` in inline labels. The
    renderer must scrub them so the diagram doesn't break."""
    msgs = [
        Message(
            from_lane=Lane.AGENT, to_lane=Lane.USER,
            label="result; with: bad chars", timestamp=_T0, is_response=True,
        ),
    ]
    diagram_source = _render_mermaid_diagram(_make_view(messages=msgs))
    # ``;`` and bare ``:`` after a word should not appear in the
    # diagram label (they're scrubbed to ``,`` and `` -``).
    assert "result; with:" not in diagram_source
    assert "result, with -" in diagram_source


# ---------- judge panel ----------

def test_render_judge_panel_rows_match_criteria():
    """Per-criterion verdicts should render as table rows with PASS/FAIL
    and the rationale text."""
    criteria = [
        {"name": "considers_multiple_hypotheses", "passed": True, "rationale": "Names 4 classes"},
        {"name": "synthesizes_available_context", "passed": False, "rationale": "Asks user"},
    ]
    html = render_trace_html(_make_view(
        judge_criteria=criteria,
        judge_rationale="3/5 passed",
        judge_model="claude-opus-4-7",
    ))
    assert "considers_multiple_hypotheses" in html
    assert "synthesizes_available_context" in html
    assert "Names 4 classes" in html
    assert "Asks user" in html
    # Both verdict markers should appear
    assert "PASS" in html
    assert "FAIL" in html
    # Overall rationale + judge model
    assert "3/5 passed" in html
    assert "claude-opus-4-7" in html


def test_render_judge_panel_omitted_when_no_criteria():
    """Naked-model traces have no judge spans → judge panel suppressed."""
    html = render_trace_html(_make_view())
    assert "LLM judge" not in html
    assert "judge-table" not in html


def test_render_judge_panel_html_escapes_rationale():
    """Rationale text often contains ``<`` (e.g., '<200 tokens'). HTML
    escape so the page doesn't break on user-supplied content."""
    criteria = [
        {"name": "x", "passed": True, "rationale": "Used <script> tag in response"},
    ]
    html = render_trace_html(_make_view(judge_criteria=criteria))
    assert "&lt;script&gt;" in html
    assert "<script>" not in html.replace(
        '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>',
        "",
    ).replace(
        "<script>\n    mermaid.initialize",
        "",
    )


# ---------- scores panel ----------

def test_render_scores_panel_shows_trace_level_score():
    scores = [TraceScore(name="harnessit.eval.overall_pass", value=1.0, comment="passed")]
    html = render_trace_html(_make_view(scores=scores))
    assert "harnessit.eval.overall_pass" in html
    assert "passed" in html


def test_render_scores_panel_omitted_when_no_scores():
    html = render_trace_html(_make_view())
    assert "scores-table" not in html


# ---------- message detail blocks ----------

def test_render_message_detail_uses_collapsible_details():
    """Each message gets a <details>/<summary> block so the page
    doesn't dump raw payloads up front."""
    html = render_trace_html(_make_view())
    assert html.count("<details") == 2  # one per message
    assert "<summary>" in html


def test_render_message_payload_renders_as_pre_block():
    """Tool result payloads render as preformatted JSON for readability."""
    msgs = [
        Message(
            from_lane=Lane.AGENT, to_lane=Lane.TOOL,
            label="get_topology", timestamp=_T0,
            payload={"input": {}},
        ),
        Message(
            from_lane=Lane.TOOL, to_lane=Lane.AGENT,
            label="get_topology → result", timestamp=_T0,
            is_response=True,
            payload={"output": {"shape": "leaf-spine", "leaves": 2}},
        ),
    ]
    html = render_trace_html(_make_view(messages=msgs))
    assert "leaf-spine" in html
    assert "<pre class='payload'>" in html


# ---------- eval metadata ----------

def test_render_includes_eval_metadata_keys():
    """Scoring mode and target run id show up as header metadata so
    the SRE knows whether they're looking at keyword-only or LLM-judged."""
    metadata = {
        "scenario_name": "microburst-with-topology-tool",
        "scoring_mode": "llm_judge",
        "target_run_id": "abc-target",
        "expected_to_pass": True,
    }
    html = render_trace_html(_make_view(eval_metadata=metadata))
    assert "scoring_mode" in html
    assert "llm_judge" in html
    assert "abc-target" in html


# ---------- end-to-end smoke ----------

def test_render_full_trace_view_produces_html_under_size_limit():
    """Sanity: a full tool-use+judge view should render to <100KB
    of HTML for a typical Stage 3 trace, including all panels."""
    msgs = [
        Message(from_lane=Lane.USER, to_lane=Lane.AGENT, label="help ticket", timestamp=_T0),
        Message(from_lane=Lane.AGENT, to_lane=Lane.TOOL, label="get_topology", timestamp=_T0),
        Message(
            from_lane=Lane.TOOL, to_lane=Lane.AGENT, label="get_topology → result",
            timestamp=_T0, is_response=True,
            payload={"output": {"leaves": 2, "spines": 4}},
        ),
        Message(
            from_lane=Lane.AGENT, to_lane=Lane.USER, label="triage response",
            timestamp=_T0, is_response=True,
            payload={"text": "..."},
        ),
        Message(from_lane=Lane.AGENT, to_lane=Lane.JUDGE, label="evaluate", timestamp=_T0),
        Message(
            from_lane=Lane.JUDGE, to_lane=Lane.AGENT, label="verdict: PASS",
            timestamp=_T0, is_response=True,
        ),
    ]
    criteria = [
        {"name": f"criterion_{i}", "passed": True, "rationale": "..."}
        for i in range(5)
    ]
    scores = [TraceScore(name="overall_pass", value=1.0, comment="all pass")]
    html = render_trace_html(_make_view(
        messages=msgs, judge_criteria=criteria,
        judge_rationale="all good", judge_model="claude-opus-4-7",
        scores=scores,
        eval_metadata={"scenario_name": "microburst-with-topology-tool"},
        scenario_name="microburst-with-topology-tool",
    ))
    assert len(html) < 100_000  # generous upper bound on a Stage 3 trace HTML
    # All panels rendered
    assert "Sequence diagram" in html
    assert "judge-table" in html
    assert "scores-table" in html
    assert "Messages (6)" in html
