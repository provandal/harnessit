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

from typing import Any

from langfuse import Langfuse, get_client, observe

from harnessit.config import Settings
from harnessit.model import Completion, ModelClient

GENERATION_SPAN_NAME = "harnessit.naked_model.complete"


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
