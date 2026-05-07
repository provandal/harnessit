"""Langfuse trace fetch wrapper.

Pulls a trace + observations from Langfuse via the existing
``langfuse`` package (v4.5.1 used here). Decoupled from the transform
layer so tests can stub it out — anything that returns a TraceView
can render.

The Langfuse client we already initialize via ``init_langfuse`` for
emitting traces is the same client we use here for reading them
back; ``langfuse.get_client().api.trace.get(trace_id)`` is the path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from harnessit.viewer.transform import (
    Span,
    TraceScore,
    TraceView,
    build_trace_view,
)


def _to_span(observation: Any) -> Span:
    """Adapt a Langfuse ObservationsView record into our normalized Span."""
    usage = getattr(observation, "usage", None) or {}
    if isinstance(usage, dict):
        in_tok = usage.get("input")
        out_tok = usage.get("output")
    else:
        in_tok = getattr(usage, "input", None)
        out_tok = getattr(usage, "output", None)
    return Span(
        id=str(observation.id),
        name=str(observation.name or "<unnamed>"),
        type=str(getattr(observation, "type", "SPAN")),
        parent_id=getattr(observation, "parent_observation_id", None),
        start_time=observation.start_time,
        end_time=getattr(observation, "end_time", None),
        input=getattr(observation, "input", None),
        output=getattr(observation, "output", None),
        metadata=dict(getattr(observation, "metadata", None) or {}),
        model=getattr(observation, "model", None),
        usage_input_tokens=in_tok,
        usage_output_tokens=out_tok,
    )


def _to_trace_score(score: Any) -> TraceScore:
    """Adapt a Langfuse Score record into our TraceScore."""
    return TraceScore(
        name=str(score.name),
        value=getattr(score, "value", None),
        comment=getattr(score, "comment", None),
        string_value=getattr(score, "string_value", None),
    )


def fetch_trace_view(trace_id: str, *, langfuse_client: Any) -> TraceView:
    """Fetch a trace by id and reshape into a TraceView.

    Parameters
    ----------
    trace_id:
        Langfuse trace id (32-hex-char OTel trace id, the one
        ``client.get_current_trace_id()`` returns at run time).
    langfuse_client:
        A ``langfuse.Langfuse`` instance whose ``.api.trace.get()``
        is callable. Tests pass a stub object exposing the same
        attribute path.
    """
    raw = langfuse_client.api.trace.get(trace_id)
    spans = [_to_span(o) for o in (raw.observations or [])]
    scores = tuple(_to_trace_score(s) for s in (getattr(raw, "scores", None) or []))
    return build_trace_view(
        trace_id=str(raw.id),
        trace_name=getattr(raw, "name", None),
        timestamp=raw.timestamp if isinstance(raw.timestamp, datetime) else datetime.now(),
        trace_input=getattr(raw, "input", None),
        trace_output=getattr(raw, "output", None),
        trace_metadata=dict(getattr(raw, "metadata", None) or {}),
        spans=spans,
        scores=scores,
    )


__all__ = ["fetch_trace_view"]
