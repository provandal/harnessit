"""Tests for harnessit.viewer.client — Langfuse fetch wrapper.

Hermetic via a stub Langfuse client that mimics
``langfuse_client.api.trace.get(trace_id)`` returning a stub
TraceWithFullDetails-shaped object. Verifies the adapter layer
(Langfuse SDK shape → our normalized Span/TraceScore) without
touching the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from harnessit.viewer.client import _to_span, _to_trace_score, fetch_trace_view
from harnessit.viewer.transform import Lane, TraceView


_T0 = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)


# ---------- stub objects mirroring Langfuse v4.5 SDK shape ----------

@dataclass
class _StubObservation:
    id: str
    name: str
    type: str
    parent_observation_id: str | None
    start_time: datetime
    end_time: datetime | None = None
    input: Any = None
    output: Any = None
    metadata: dict[str, Any] | None = None
    model: str | None = None
    usage: Any = None


@dataclass
class _StubScore:
    name: str
    value: float | None = None
    comment: str | None = None
    string_value: str | None = None


@dataclass
class _StubTrace:
    id: str
    timestamp: datetime
    name: str | None = None
    input: Any = None
    output: Any = None
    metadata: dict[str, Any] | None = None
    observations: list[_StubObservation] = field(default_factory=list)
    scores: list[_StubScore] = field(default_factory=list)


@dataclass
class _StubTraceClient:
    trace_data: _StubTrace
    calls: list[str] = field(default_factory=list)

    def get(self, trace_id: str) -> _StubTrace:
        self.calls.append(trace_id)
        return self.trace_data


@dataclass
class _StubAPI:
    trace: _StubTraceClient


@dataclass
class _StubLangfuse:
    api: _StubAPI


# ---------- _to_span ----------

def test_to_span_handles_dict_usage():
    obs = _StubObservation(
        id="o1", name="harnessit.naked_model.complete",
        type="GENERATION",
        parent_observation_id="root",
        start_time=_T0,
        end_time=_T0,
        usage={"input": 100, "output": 50},
    )
    span = _to_span(obs)
    assert span.usage_input_tokens == 100
    assert span.usage_output_tokens == 50


def test_to_span_handles_object_usage():
    """Some Langfuse versions return a Pydantic-model usage object
    rather than a dict; the adapter must handle both."""
    @dataclass
    class _UsageObj:
        input: int
        output: int

    obs = _StubObservation(
        id="o1", name="m", type="GENERATION",
        parent_observation_id=None, start_time=_T0,
        usage=_UsageObj(input=42, output=7),
    )
    span = _to_span(obs)
    assert span.usage_input_tokens == 42
    assert span.usage_output_tokens == 7


def test_to_span_handles_missing_usage():
    obs = _StubObservation(
        id="o1", name="x", type="SPAN",
        parent_observation_id=None, start_time=_T0,
        usage=None,
    )
    span = _to_span(obs)
    assert span.usage_input_tokens is None
    assert span.usage_output_tokens is None


def test_to_span_normalizes_metadata_to_dict():
    obs = _StubObservation(
        id="o1", name="x", type="SPAN",
        parent_observation_id=None, start_time=_T0,
        metadata=None,
    )
    span = _to_span(obs)
    assert span.metadata == {}


# ---------- _to_trace_score ----------

def test_to_trace_score_passes_through_fields():
    s = _StubScore(name="overall_pass", value=1.0, comment="passed")
    ts = _to_trace_score(s)
    assert ts.name == "overall_pass"
    assert ts.value == 1.0
    assert ts.comment == "passed"


# ---------- fetch_trace_view ----------

def _make_minimal_trace() -> _StubTrace:
    """A representative Stage 2 naked-model trace shape."""
    return _StubTrace(
        id="trace-abc",
        timestamp=_T0,
        name="microburst-symptom-only",
        input="step time on host 11.0.0.1 up 1.5x",
        output="triage plan: pass",
        metadata={"scenario_name": "microburst-symptom-only", "scoring_mode": "keyword"},
        observations=[
            _StubObservation(
                id="root", name="harnessit.eval.run", type="SPAN",
                parent_observation_id=None,
                start_time=_T0, end_time=_T0,
            ),
            _StubObservation(
                id="m1", name="harnessit.naked_model.complete",
                type="GENERATION",
                parent_observation_id="root",
                start_time=_T0, end_time=_T0,
                output="triage plan: pass",
                usage={"input": 100, "output": 50},
            ),
        ],
        scores=[
            _StubScore(name="harnessit.eval.overall_pass", value=0.0, comment="2/4"),
        ],
    )


def test_fetch_trace_view_invokes_api_get_with_trace_id():
    trace_data = _make_minimal_trace()
    stub = _StubLangfuse(api=_StubAPI(trace=_StubTraceClient(trace_data=trace_data)))
    fetch_trace_view("trace-abc", langfuse_client=stub)
    assert stub.api.trace.calls == ["trace-abc"]


def test_fetch_trace_view_returns_correct_shape():
    trace_data = _make_minimal_trace()
    stub = _StubLangfuse(api=_StubAPI(trace=_StubTraceClient(trace_data=trace_data)))
    view = fetch_trace_view("trace-abc", langfuse_client=stub)

    assert isinstance(view, TraceView)
    assert view.trace_id == "trace-abc"
    assert view.scenario_name == "microburst-symptom-only"
    assert view.user_prompt == "step time on host 11.0.0.1 up 1.5x"
    assert view.eval_metadata.get("scoring_mode") == "keyword"
    # Active lanes from a naked-model trace = User + Agent only
    assert set(view.active_lanes) == {Lane.USER, Lane.AGENT}
    # Trace-level score plumbed through
    assert len(view.scores) == 1
    assert view.scores[0].name == "harnessit.eval.overall_pass"


def test_fetch_trace_view_handles_empty_observations():
    """Some traces (e.g., a runner that crashed before instrumenting)
    might come back with no observations. Don't crash."""
    trace_data = _StubTrace(
        id="empty", timestamp=_T0, name="x",
        input="prompt", output=None, metadata={},
        observations=[], scores=[],
    )
    stub = _StubLangfuse(api=_StubAPI(trace=_StubTraceClient(trace_data=trace_data)))
    view = fetch_trace_view("empty", langfuse_client=stub)
    # Just the User -> Agent help ticket inferred from input
    assert len(view.messages) == 1
