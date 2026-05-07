"""Langfuse v4 instrumentation around the naked-model layer.

Stage 2 deliverable 2 (Build Plan v0.3 §2.1): "Langfuse instrumentation
captures every span from the very first model call." Stage 4 transitions
the backing store from managed Langfuse Cloud to self-hosted; this layer
is unaffected because Langfuse v4 is OTel-based and we only depend on
the public client surface.

Use:

    settings = load_settings()
    init_langfuse(settings)             # once at process startup
    completion = traced_complete(       # per call
        model_client,
        system=...,
        user=...,
        scenario_name=...,
    )
    flush_langfuse()                    # before process exit
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langfuse import Langfuse, get_client, observe

from harnessit.config import Settings
from harnessit.model import Completion, ModelClient, ToolCall, ToolExecutor, ToolUseCompletion

if TYPE_CHECKING:
    # Avoid a cycle: harnessit.eval.judge imports JUDGE_SPAN_NAME from
    # this module (re-exports it for callers); we only need the Judge /
    # Judgment types at type-check time.
    from harnessit.eval.judge import Judge, Judgment

GENERATION_SPAN_NAME = "harnessit.naked_model.complete"
TOOL_USE_GENERATION_SPAN_NAME = "harnessit.tool_use.complete"
JUDGE_SPAN_NAME = "harnessit.eval.judge"


def init_langfuse(
    settings: Settings,
    *,
    span_exporter: Any | None = None,
    flush_at: int | None = None,
    tracing_enabled: bool = True,
) -> Langfuse:
    """Initialize the singleton Langfuse client from Settings.

    Parameters
    ----------
    settings:
        Loaded HarnessIT settings.
    span_exporter:
        Optional OTel ``SpanExporter`` override (used by tests with
        ``InMemorySpanExporter``).
    flush_at:
        Override for batched-flush threshold; tests use ``flush_at=1``
        for synchronous span observation.
    tracing_enabled:
        Set False to no-op all spans (useful for hermetic dev runs).
    """
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_base_url,
        tracing_enabled=tracing_enabled,
        span_exporter=span_exporter,
        flush_at=flush_at,
    )


def flush_langfuse() -> None:
    """Flush buffered spans to the backend. Safe to call from atexit hooks."""
    get_client().flush()


@observe(
    as_type="generation",
    name=GENERATION_SPAN_NAME,
    capture_input=False,
    capture_output=False,
)
def traced_complete(
    model_client: ModelClient,
    *,
    system: str,
    user: str,
    max_tokens: int | None = None,
    scenario_name: str | None = None,
) -> Completion:
    """Naked-model call wrapped in a Langfuse generation span.

    Captures input messages, output text, model id, and token usage on
    the active generation span. ``scenario_name`` is propagated as
    metadata so eval runs can be filtered in the Langfuse UI.
    """
    completion = model_client.complete(system=system, user=user, max_tokens=max_tokens)

    metadata: dict[str, Any] = {"stop_reason": completion.stop_reason}
    if scenario_name is not None:
        metadata["scenario_name"] = scenario_name

    get_client().update_current_generation(
        model=completion.model,
        input={"system": system, "user": user},
        output=completion.text,
        usage_details={
            "input": completion.input_tokens,
            "output": completion.output_tokens,
        },
        metadata=metadata,
    )
    return completion


@observe(
    as_type="generation",
    name=TOOL_USE_GENERATION_SPAN_NAME,
    capture_input=False,
    capture_output=False,
)
async def traced_complete_with_tools(
    model_client: ModelClient,
    *,
    system: str,
    user: str,
    tools: list[dict[str, Any]],
    tool_executor: ToolExecutor,
    max_tokens: int | None = None,
    max_iterations: int = 10,
    scenario_name: str | None = None,
) -> ToolUseCompletion:
    """Tool-use loop wrapped in a Langfuse generation span.

    Per-tool spans (``harnessit.tools.<name>``) emit independently from
    inside the executor; this generation span owns the model-side
    summary — input messages, final output text, summed token counts,
    iteration count, list of tool names invoked.
    """
    completion = await model_client.complete_with_tools(
        system=system,
        user=user,
        tools=tools,
        tool_executor=tool_executor,
        max_tokens=max_tokens,
        max_iterations=max_iterations,
    )

    metadata: dict[str, Any] = {
        "stop_reason": completion.stop_reason,
        "iterations": completion.iterations,
        "tool_calls": [
            {"name": tc.name, "id": tc.id} for tc in completion.tool_calls
        ],
    }
    if scenario_name is not None:
        metadata["scenario_name"] = scenario_name

    get_client().update_current_generation(
        model=completion.model,
        input={
            "system": system,
            "user": user,
            "tools": [t["name"] for t in tools],
        },
        output=completion.text,
        usage_details={
            "input": completion.input_tokens,
            "output": completion.output_tokens,
        },
        metadata=metadata,
    )
    return completion


@observe(
    as_type="span",
    name=JUDGE_SPAN_NAME,
    capture_input=False,
    capture_output=False,
)
async def traced_judge_score(
    judge: Judge,
    *,
    system_prompt: str,
    user_prompt: str,
    agent_response: str,
    tool_calls: tuple[ToolCall, ...] = (),
    scenario_name: str | None = None,
) -> Judgment:
    """LLM-judge call wrapped in a Langfuse span.

    The span captures the judge's structured output — per-criterion
    rationale, overall verdict, judge model — so the trajectory viewer
    (Stage 4) can render the judge's reasoning alongside the agent's.
    Failures bubble up as ``JudgeError`` for the runner to catch and
    fall back to keyword scoring.
    """
    judgment = await judge.score(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        agent_response=agent_response,
        tool_calls=tool_calls,
    )

    metadata: dict[str, Any] = {
        "judge_model": judgment.judge_model,
    }
    if scenario_name is not None:
        metadata["scenario_name"] = scenario_name

    get_client().update_current_span(
        input={
            "judge_model": judge.model,
            "agent_response_length": len(agent_response),
            "tool_calls_count": len(tool_calls),
        },
        output={
            "overall_pass": judgment.overall_pass,
            "overall_rationale": judgment.overall_rationale,
            "criteria": [
                {"name": c.name, "passed": c.passed, "rationale": c.rationale}
                for c in judgment.criteria
            ],
        },
        metadata=metadata,
    )
    return judgment
