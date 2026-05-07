"""Frontier model layer — naked completion + tool-use loop.

Thin wrapper around ``anthropic.Anthropic`` exposing two entry points:

* ``ModelClient.complete`` — Stage 2 naked-model call (system + user,
  text in, text out). No tools, no retrieval, no memory.
* ``ModelClient.complete_with_tools`` — Stage 3 tool-use loop. Same
  system + user, plus a tools list and an async executor. Iterates on
  ``stop_reason == "tool_use"``, dispatches each tool_use block through
  the executor, appends ``tool_result`` blocks, loops until
  ``end_turn``.

The Anthropic client is injected via constructor so tests can swap in a
fake without touching the network. Production callers use
``ModelClient.from_settings()``. The tool-use loop is async at the outer
boundary (so executors can be MCP-async naturally) but keeps the
underlying Anthropic client sync via ``asyncio.to_thread`` — no separate
``AsyncAnthropic`` instance, no async-rewrite of the existing tests.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from harnessit.config import Settings


@dataclass(frozen=True)
class Completion:
    """Structured result of a single naked-model call."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None


@dataclass(frozen=True)
class ToolCall:
    """One round-trip through the tool-use loop.

    ``output`` is whatever the executor returned, preserved verbatim for
    Langfuse/eval inspection. ``output_serialized`` is the string form
    that was actually sent back to the model in the ``tool_result``
    block.
    """

    id: str
    name: str
    input: dict[str, Any]
    output: Any
    output_serialized: str


@dataclass(frozen=True)
class ToolUseCompletion:
    """Result of a ``complete_with_tools`` run.

    Token counts are summed across every iteration of the loop. ``text``
    is the final assistant turn's text content (after the last
    ``tool_result`` round-trip). ``stop_reason`` is the SDK's stop
    reason from the final iteration; ``"max_iterations"`` if the loop
    was terminated by the iteration cap before the model ended its
    turn.
    """

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None
    tool_calls: tuple[ToolCall, ...]
    iterations: int


ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[Any]]


class _MessagesAPI(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class _AnthropicLike(Protocol):
    messages: _MessagesAPI


class ModelClient:
    """Naked frontier-model client.

    Parameters
    ----------
    client:
        An object exposing ``client.messages.create(...)`` — the
        Anthropic SDK's ``Anthropic`` instance, or a fake in tests.
    model:
        Model id used for every call (no per-call override yet).
    default_max_tokens:
        Default cap on output tokens. Callers can override per call.
    """

    def __init__(
        self,
        *,
        client: _AnthropicLike,
        model: str,
        default_max_tokens: int = 4096,
    ) -> None:
        self._client = client
        self.model = model
        self.default_max_tokens = default_max_tokens

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: Any) -> "ModelClient":
        """Construct using a real ``anthropic.Anthropic`` from Settings."""
        from anthropic import Anthropic

        return cls(
            client=Anthropic(api_key=settings.anthropic_api_key),
            model=settings.model,
            **kwargs,
        )

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int | None = None,
    ) -> Completion:
        """One-shot completion with a system prompt + a single user turn."""
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.default_max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _to_completion(response)

    async def complete_with_tools(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        tool_executor: ToolExecutor,
        max_tokens: int | None = None,
        max_iterations: int = 10,
    ) -> ToolUseCompletion:
        """Tool-use loop. Async at the outer boundary; the underlying
        Anthropic call stays sync via ``asyncio.to_thread``.

        ``tool_executor`` receives ``(name, input_dict)`` and returns
        whatever it likes — strings pass through, dicts/lists are JSON
        encoded into the ``tool_result`` content. The loop terminates on
        any ``stop_reason`` other than ``"tool_use"``, or when
        ``max_iterations`` is exceeded (in which case ``stop_reason`` on
        the result is ``"max_iterations"``).
        """
        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        tool_calls: list[ToolCall] = []
        total_input_tokens = 0
        total_output_tokens = 0
        final_text = ""
        final_model = ""
        final_stop_reason: str | None = None
        iterations = 0

        for iteration in range(max_iterations):
            iterations = iteration + 1
            response = await asyncio.to_thread(
                self._client.messages.create,
                model=self.model,
                max_tokens=max_tokens or self.default_max_tokens,
                system=system,
                tools=tools,
                messages=messages,
            )
            usage = response.usage
            total_input_tokens += usage.input_tokens
            total_output_tokens += usage.output_tokens
            final_model = response.model
            final_stop_reason = response.stop_reason

            if response.stop_reason != "tool_use":
                final_text = "".join(
                    block.text
                    for block in response.content
                    if getattr(block, "type", None) == "text"
                )
                return ToolUseCompletion(
                    text=final_text,
                    model=final_model,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    stop_reason=final_stop_reason,
                    tool_calls=tuple(tool_calls),
                    iterations=iterations,
                )

            assistant_blocks = [_serialize_block(b) for b in response.content]
            messages.append({"role": "assistant", "content": assistant_blocks})

            tool_result_blocks: list[dict[str, Any]] = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                output = await tool_executor(block.name, dict(block.input))
                serialized = _serialize_tool_output(output)
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        input=dict(block.input),
                        output=output,
                        output_serialized=serialized,
                    )
                )
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": serialized,
                    }
                )
            messages.append({"role": "user", "content": tool_result_blocks})

        return ToolUseCompletion(
            text=final_text,
            model=final_model,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            stop_reason="max_iterations",
            tool_calls=tuple(tool_calls),
            iterations=iterations,
        )


def _to_completion(response: Any) -> Completion:
    """Extract Completion fields from an Anthropic Message response."""
    text = "".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    )
    usage = response.usage
    return Completion(
        text=text,
        model=response.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        stop_reason=response.stop_reason,
    )


def _serialize_block(block: Any) -> dict[str, Any]:
    """Convert an SDK content block to a plain dict for re-feeding into messages.

    The Anthropic SDK accepts either pydantic models or plain dicts on
    the way back in. Going through a dict keeps tests hermetic — fakes
    can use ``@dataclass`` blocks without inheriting pydantic semantics.
    """
    block_type = getattr(block, "type", None)
    if block_type == "text":
        return {"type": "text", "text": block.text}
    if block_type == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": dict(block.input),
        }
    raise ValueError(f"Unexpected content block type: {block_type!r}")


def _serialize_tool_output(output: Any) -> str:
    """Serialize an executor return value into a tool_result content string.

    Strings pass through unchanged. Everything else is JSON-encoded —
    dicts and lists are the common cases for substrate query results.
    """
    if isinstance(output, str):
        return output
    return json.dumps(output, default=str)
