"""Span tree → sequence-diagram message list.

The Langfuse trace fetch returns a flat list of observations linked by
``parent_observation_id``. The viewer reshapes that into a
sequence-diagram representation: services-as-columns (Lanes), arrows
for each interaction (Messages), with the agent's response and the
judge's per-criterion rationale rendered inline.

Lane assignment is by span-name pattern. The mapping is explicit and
small for v0.1 — Stage 5+ will likely grow it as new tools and skills
add new span namespaces.

Pure data-model code. No I/O. Tests stay hermetic with stub spans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Iterable


class Lane(str, Enum):
    """Sequence-diagram column. Order matters for left-to-right layout."""

    USER = "User"
    AGENT = "Agent"
    TOOL = "Tool"
    SUBSTRATE_ADAPTER = "Substrate Adapter"
    SUBSTRATE = "Substrate"
    JUDGE = "Judge"
    OTHER = "Other"

    @classmethod
    def ordered_for_diagram(cls) -> list["Lane"]:
        """Left-to-right order Mermaid will render. ``OTHER`` last."""
        return [
            cls.USER,
            cls.AGENT,
            cls.TOOL,
            cls.SUBSTRATE_ADAPTER,
            cls.SUBSTRATE,
            cls.JUDGE,
            cls.OTHER,
        ]


@dataclass(frozen=True)
class Span:
    """One observation from a Langfuse trace, normalized.

    Mirrors the subset of ``ObservationsView`` fields the viewer
    consumes. Constructed from raw observation objects in
    ``viewer.client``; the transform layer only sees this normalized
    shape so tests can build them by hand.
    """

    id: str
    name: str
    type: str  # "SPAN" | "GENERATION" | "EVENT"
    parent_id: str | None
    start_time: datetime
    end_time: datetime | None
    input: Any = None
    output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    usage_input_tokens: int | None = None
    usage_output_tokens: int | None = None


@dataclass(frozen=True)
class Message:
    """One arrow in the sequence diagram.

    ``from_lane`` → ``to_lane`` arrow with ``label``. The full input
    and output are preserved on ``payload`` for inline rendering
    (collapsible details below the arrow). ``span_id`` is preserved so
    the rendered HTML can deep-link back into Langfuse.
    """

    from_lane: Lane
    to_lane: Lane
    label: str
    timestamp: datetime
    span_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    is_response: bool = False  # True for return arrows (right-to-left)


@dataclass(frozen=True)
class TraceScore:
    """A trace-level score (overall_pass, etc.) from Langfuse."""

    name: str
    value: float | None
    comment: str | None
    string_value: str | None = None


@dataclass(frozen=True)
class TraceView:
    """Top-level data structure rendered by ``viewer.render``.

    Holds the trace-level metadata + the ordered list of messages +
    the active set of lanes (only render columns we actually use).
    """

    trace_id: str
    trace_name: str | None
    timestamp: datetime
    user_prompt: str
    agent_final_response: str
    messages: tuple[Message, ...]
    active_lanes: tuple[Lane, ...]
    scores: tuple[TraceScore, ...] = ()
    scenario_name: str | None = None
    eval_metadata: dict[str, Any] = field(default_factory=dict)
    judge_criteria: tuple[dict[str, Any], ...] = ()
    judge_rationale: str | None = None
    judge_model: str | None = None


def span_name_to_lane(name: str) -> Lane:
    """Map a Langfuse observation name to a sequence-diagram lane.

    Patterns are checked in order from most-specific to least. Unknown
    names land in ``Lane.OTHER`` rather than crashing — the viewer is
    forward-compatible with new spans landing in future stages.
    """
    if name == "harnessit.eval.run":
        # Top-level eval wrapper; not a per-lane span. Caller handles
        # this case explicitly (it's the trace root).
        return Lane.AGENT
    if name == "harnessit.eval.judge":
        return Lane.JUDGE
    if name.startswith("harnessit.tools."):
        return Lane.TOOL
    if name == "harnessit.naked_model.complete":
        return Lane.AGENT
    if name == "harnessit.tool_use.complete":
        return Lane.AGENT
    # MCP / Adapter call frames if/when they're surfaced as spans
    if name.startswith("doppelganger.") or name.startswith("adapter."):
        return Lane.SUBSTRATE_ADAPTER
    if name.startswith("substrate.") or name.startswith("driver."):
        return Lane.SUBSTRATE
    return Lane.OTHER


def _children_of(spans: list[Span], parent_id: str | None) -> list[Span]:
    """Return spans whose ``parent_id`` matches, sorted by start_time."""
    return sorted(
        (s for s in spans if s.parent_id == parent_id),
        key=lambda s: s.start_time,
    )


def _judge_criteria_from_metadata(judge_span: Span) -> tuple[dict[str, Any], ...]:
    """Extract per-criterion rationale from a ``harnessit.eval.judge`` span.

    The runner's tracing layer puts criteria onto the span's ``output``
    as ``criteria: [{name, passed, rationale}, ...]``. Returns an empty
    tuple if the shape isn't what we expect — defensive against schema
    changes upstream.
    """
    output = judge_span.output
    if not isinstance(output, dict):
        return ()
    raw = output.get("criteria")
    if not isinstance(raw, list):
        return ()
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        out.append({
            "name": name,
            "passed": bool(entry.get("passed", False)),
            "rationale": str(entry.get("rationale", "")),
        })
    return tuple(out)


def _extract_text(value: Any) -> str:
    """Coerce a Langfuse input/output value to a printable string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Common shapes: {"system": ..., "user": ...} or {"text": ...}
        if "user" in value and isinstance(value["user"], str):
            return value["user"]
        if "text" in value and isinstance(value["text"], str):
            return value["text"]
    return repr(value)


def build_trace_view(
    *,
    trace_id: str,
    trace_name: str | None,
    timestamp: datetime,
    trace_input: Any,
    trace_output: Any,
    trace_metadata: dict[str, Any] | None,
    spans: Iterable[Span],
    scores: Iterable[TraceScore] = (),
) -> TraceView:
    """Reshape a Langfuse trace + spans into a sequence-diagram view.

    Algorithm:
    1. Find the eval-run root (parent_id None, name harnessit.eval.run).
       If absent, treat all roots as siblings.
    2. Walk children of the root in start-time order. For each:
       - Generation spans → User → Agent (request) and Agent → User
         (response) message pair.
       - Tool-use generation → request/response pair, then walk
         children for Tool calls (Agent → Tool → Agent).
       - Judge span → Agent → Judge (request) and Judge → Agent
         (verdict) message pair; judge criteria stored separately.
    3. Build the active-lane set from the lanes actually used.
    """
    span_list = list(spans)
    metadata = trace_metadata or {}

    # Locate the eval-run root if present.
    eval_root: Span | None = None
    for s in span_list:
        if s.name == "harnessit.eval.run" and s.parent_id is None:
            eval_root = s
            break

    walk_root_id = eval_root.id if eval_root is not None else None

    # Merge the eval-root span's metadata into the trace-level metadata.
    # Stage 3's runner sets scenario_name and friends on the eval-root
    # span via update_current_span(metadata=...), not on the trace
    # itself — the viewer needs both to find the scenario name and
    # other run-level metadata reliably.
    if eval_root is not None and isinstance(eval_root.metadata, dict):
        for key, value in eval_root.metadata.items():
            metadata.setdefault(key, value)

    # Fallback: scenario_name might be on trace.input.scenario (the
    # @observe-decorated runner sets that explicitly via span input).
    # Pre-Stage-3-LLM-judge traces only had it there.
    if "scenario_name" not in metadata and isinstance(trace_input, dict):
        if isinstance(trace_input.get("scenario"), str):
            metadata.setdefault("scenario_name", trace_input["scenario"])

    user_prompt = _extract_text(trace_input)
    # If trace.input is a dict that doesn't contain a "user" field
    # (the eval-root span's input is {scenario, target_scenario}),
    # fall back to the actual model span's user input — that's where
    # the help ticket text lives.
    if not user_prompt or user_prompt.startswith("{"):
        for s in span_list:
            if s.name in ("harnessit.naked_model.complete", "harnessit.tool_use.complete"):
                if isinstance(s.input, dict):
                    user_input = s.input.get("user")
                    if isinstance(user_input, str) and user_input:
                        user_prompt = user_input
                        break

    agent_final_response = _extract_text(trace_output)

    messages: list[Message] = []
    judge_criteria: tuple[dict[str, Any], ...] = ()
    judge_rationale: str | None = None
    judge_model: str | None = None

    # Inferred opening message: the user's help ticket lands at the agent.
    # Use the eval-run start_time so this anchors to the run start.
    if user_prompt:
        opener_ts = eval_root.start_time if eval_root else timestamp
        messages.append(Message(
            from_lane=Lane.USER,
            to_lane=Lane.AGENT,
            label="help ticket",
            timestamp=opener_ts,
            span_id=eval_root.id if eval_root else None,
            payload={"text": user_prompt},
        ))

    # Walk children of the eval root in start-time order.
    children = _children_of(span_list, walk_root_id)

    for child in children:
        lane = span_name_to_lane(child.name)

        if child.name in ("harnessit.naked_model.complete", "harnessit.tool_use.complete"):
            # The agent's model call. For the tool-use variant, walk
            # its children to surface tool round-trips before the
            # final response.
            inner = _children_of(span_list, child.id)
            tool_spans = [s for s in inner if span_name_to_lane(s.name) == Lane.TOOL]
            for tool_span in tool_spans:
                tool_label = tool_span.name.removeprefix("harnessit.tools.")
                tool_input = (
                    tool_span.input.get("agent_args")
                    if isinstance(tool_span.input, dict)
                    else tool_span.input
                )
                messages.append(Message(
                    from_lane=Lane.AGENT,
                    to_lane=Lane.TOOL,
                    label=tool_label,
                    timestamp=tool_span.start_time,
                    span_id=tool_span.id,
                    payload={"input": tool_input},
                ))
                if tool_span.end_time is not None:
                    messages.append(Message(
                        from_lane=Lane.TOOL,
                        to_lane=Lane.AGENT,
                        label=f"{tool_label} → result",
                        timestamp=tool_span.end_time,
                        span_id=tool_span.id,
                        payload={
                            "output": tool_span.output,
                            "source": tool_span.metadata.get("source"),
                            "confidence": tool_span.metadata.get("confidence"),
                            "staleness_class": tool_span.metadata.get("staleness_class"),
                        },
                        is_response=True,
                    ))
            # Final agent response arrow back to user
            response_text = _extract_text(child.output) or agent_final_response
            if response_text and child.end_time is not None:
                messages.append(Message(
                    from_lane=Lane.AGENT,
                    to_lane=Lane.USER,
                    label="triage response",
                    timestamp=child.end_time,
                    span_id=child.id,
                    payload={
                        "text": response_text,
                        "model": child.model,
                        "input_tokens": child.usage_input_tokens,
                        "output_tokens": child.usage_output_tokens,
                    },
                    is_response=True,
                ))
        elif child.name == "harnessit.eval.judge":
            messages.append(Message(
                from_lane=Lane.AGENT,
                to_lane=Lane.JUDGE,
                label="evaluate response",
                timestamp=child.start_time,
                span_id=child.id,
                payload={"input": child.input},
            ))
            judge_criteria = _judge_criteria_from_metadata(child)
            if isinstance(child.output, dict):
                judge_rationale = child.output.get("overall_rationale")
            judge_model = (
                child.metadata.get("judge_model")
                if isinstance(child.metadata, dict)
                else None
            )
            verdict_label = "verdict"
            if isinstance(child.output, dict):
                overall = child.output.get("overall_pass")
                if overall is True:
                    verdict_label = "verdict: PASS"
                elif overall is False:
                    verdict_label = "verdict: FAIL"
            if child.end_time is not None:
                messages.append(Message(
                    from_lane=Lane.JUDGE,
                    to_lane=Lane.AGENT,
                    label=verdict_label,
                    timestamp=child.end_time,
                    span_id=child.id,
                    payload={
                        "output": child.output,
                        "judge_model": judge_model,
                    },
                    is_response=True,
                ))
        else:
            # Unknown span — represent as a self-arrow on its inferred lane
            # so the data isn't silently dropped.
            messages.append(Message(
                from_lane=lane,
                to_lane=lane,
                label=child.name,
                timestamp=child.start_time,
                span_id=child.id,
                payload={"input": child.input, "output": child.output},
            ))

    # Sort by timestamp to produce a clean top-to-bottom flow even when
    # spans came back in any order. Stable so siblings tied on time
    # preserve emission order (matters for paired request/response).
    messages.sort(key=lambda m: m.timestamp)

    # Active lanes = lanes referenced by any message, ordered by the
    # canonical left-to-right diagram order.
    used_lanes = {m.from_lane for m in messages} | {m.to_lane for m in messages}
    active_lanes = tuple(
        lane for lane in Lane.ordered_for_diagram() if lane in used_lanes
    )

    return TraceView(
        trace_id=trace_id,
        trace_name=trace_name,
        timestamp=timestamp,
        user_prompt=user_prompt,
        agent_final_response=agent_final_response,
        messages=tuple(messages),
        active_lanes=active_lanes,
        scores=tuple(scores),
        scenario_name=metadata.get("scenario_name") if isinstance(metadata, dict) else None,
        eval_metadata=dict(metadata) if isinstance(metadata, dict) else {},
        judge_criteria=judge_criteria,
        judge_rationale=judge_rationale,
        judge_model=judge_model,
    )


__all__ = [
    "Lane",
    "Message",
    "Span",
    "TraceScore",
    "TraceView",
    "build_trace_view",
    "span_name_to_lane",
]
