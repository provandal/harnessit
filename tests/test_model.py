"""Tests for harnessit.model — fake Anthropic client, no network."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from harnessit.model import (
    Completion,
    ModelClient,
    ToolCall,
    ToolUseCompletion,
    _to_completion,
)


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _FakeMessage:
    content: list[Any]
    model: str
    usage: _FakeUsage
    stop_reason: str | None = "end_turn"


class _FakeMessagesAPI:
    def __init__(self, response: _FakeMessage) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        return self.response


@dataclass
class _FakeClient:
    messages: _FakeMessagesAPI = field(default=None)  # type: ignore[assignment]


def _make_client(text: str = "hello", *, model: str = "claude-opus-4-7") -> tuple[ModelClient, _FakeMessagesAPI]:
    response = _FakeMessage(
        content=[_FakeTextBlock(text=text)],
        model=model,
        usage=_FakeUsage(input_tokens=12, output_tokens=4),
    )
    api = _FakeMessagesAPI(response)
    fake = _FakeClient(messages=api)
    client = ModelClient(client=fake, model=model)
    return client, api


def test_complete_returns_text_and_usage():
    client, _ = _make_client(text="paint it black")
    result = client.complete(system="be terse", user="hello?")
    assert isinstance(result, Completion)
    assert result.text == "paint it black"
    assert result.model == "claude-opus-4-7"
    assert result.input_tokens == 12
    assert result.output_tokens == 4
    assert result.stop_reason == "end_turn"


def test_complete_passes_system_and_user_to_sdk():
    client, api = _make_client()
    client.complete(system="SYS", user="USR")
    assert len(api.calls) == 1
    call = api.calls[0]
    assert call["system"] == "SYS"
    assert call["messages"] == [{"role": "user", "content": "USR"}]
    assert call["model"] == "claude-opus-4-7"
    assert call["max_tokens"] == 4096  # default


def test_complete_max_tokens_override():
    client, api = _make_client()
    client.complete(system="s", user="u", max_tokens=128)
    assert api.calls[0]["max_tokens"] == 128


def test_complete_default_max_tokens_constructor_arg():
    response = _FakeMessage(
        content=[_FakeTextBlock(text="x")],
        model="m",
        usage=_FakeUsage(input_tokens=1, output_tokens=1),
    )
    api = _FakeMessagesAPI(response)
    client = ModelClient(client=_FakeClient(messages=api), model="m", default_max_tokens=512)
    client.complete(system="s", user="u")
    assert api.calls[0]["max_tokens"] == 512


def test_complete_concatenates_multiple_text_blocks():
    response = _FakeMessage(
        content=[
            _FakeTextBlock(text="part-1 "),
            _FakeTextBlock(text="part-2"),
        ],
        model="m",
        usage=_FakeUsage(input_tokens=1, output_tokens=2),
    )
    api = _FakeMessagesAPI(response)
    client = ModelClient(client=_FakeClient(messages=api), model="m")
    result = client.complete(system="s", user="u")
    assert result.text == "part-1 part-2"


def test_to_completion_skips_non_text_blocks():
    @dataclass
    class _ToolUseBlock:
        type: str = "tool_use"
        name: str = "foo"

    response = _FakeMessage(
        content=[
            _FakeTextBlock(text="visible"),
            _ToolUseBlock(),
        ],
        model="m",
        usage=_FakeUsage(input_tokens=1, output_tokens=1),
    )
    completion = _to_completion(response)
    assert completion.text == "visible"


def test_complete_handles_empty_text():
    response = _FakeMessage(
        content=[],
        model="m",
        usage=_FakeUsage(input_tokens=1, output_tokens=0),
        stop_reason="max_tokens",
    )
    api = _FakeMessagesAPI(response)
    client = ModelClient(client=_FakeClient(messages=api), model="m")
    result = client.complete(system="s", user="u")
    assert result.text == ""
    assert result.stop_reason == "max_tokens"


# ---------------------------------------------------------------------------
# Tool-use loop tests
# ---------------------------------------------------------------------------


@dataclass
class _FakeToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


class _ScriptedMessagesAPI:
    """Fake messages.create that returns a scripted sequence of responses."""

    def __init__(self, responses: list[_FakeMessage]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("Scripted API exhausted; unexpected extra call")
        return self.responses.pop(0)


def _make_scripted_client(
    responses: list[_FakeMessage], *, model: str = "claude-opus-4-7"
) -> tuple[ModelClient, _ScriptedMessagesAPI]:
    api = _ScriptedMessagesAPI(responses)
    client = ModelClient(client=_FakeClient(messages=api), model=model)
    return client, api


@pytest.mark.asyncio
async def test_complete_with_tools_no_tool_use_returns_text_immediately():
    """If the first response is end_turn, the loop terminates after one call."""
    client, api = _make_scripted_client(
        [
            _FakeMessage(
                content=[_FakeTextBlock(text="all good, no tools needed")],
                model="claude-opus-4-7",
                usage=_FakeUsage(input_tokens=10, output_tokens=6),
                stop_reason="end_turn",
            )
        ]
    )

    async def executor(name: str, args: dict[str, Any]) -> str:
        raise AssertionError("executor should not be called when stop_reason=end_turn")

    result = await client.complete_with_tools(
        system="sys",
        user="ping",
        tools=[{"name": "noop", "description": "x", "input_schema": {"type": "object"}}],
        tool_executor=executor,
    )

    assert isinstance(result, ToolUseCompletion)
    assert result.text == "all good, no tools needed"
    assert result.tool_calls == ()
    assert result.iterations == 1
    assert result.input_tokens == 10
    assert result.output_tokens == 6
    assert result.stop_reason == "end_turn"
    assert len(api.calls) == 1
    assert api.calls[0]["tools"] == [
        {"name": "noop", "description": "x", "input_schema": {"type": "object"}}
    ]


@pytest.mark.asyncio
async def test_complete_with_tools_dispatches_then_returns_text():
    """tool_use -> executor -> tool_result -> end_turn. One round-trip."""
    client, api = _make_scripted_client(
        [
            _FakeMessage(
                content=[
                    _FakeTextBlock(text="let me check"),
                    _FakeToolUseBlock(
                        id="tu_1", name="get_topology", input={"hint": "fabric"}
                    ),
                ],
                model="claude-opus-4-7",
                usage=_FakeUsage(input_tokens=20, output_tokens=8),
                stop_reason="tool_use",
            ),
            _FakeMessage(
                content=[_FakeTextBlock(text="2 leaves x 4 spines, host 11.0.0.1 on leaf 1")],
                model="claude-opus-4-7",
                usage=_FakeUsage(input_tokens=50, output_tokens=15),
                stop_reason="end_turn",
            ),
        ]
    )

    executor_calls: list[tuple[str, dict[str, Any]]] = []

    async def executor(name: str, args: dict[str, Any]) -> dict[str, Any]:
        executor_calls.append((name, args))
        return {"leaves": 2, "spines": 4, "hosts_per_leaf": 8}

    result = await client.complete_with_tools(
        system="sys",
        user="help",
        tools=[
            {"name": "get_topology", "description": "fabric", "input_schema": {"type": "object"}}
        ],
        tool_executor=executor,
    )

    assert result.text == "2 leaves x 4 spines, host 11.0.0.1 on leaf 1"
    assert result.iterations == 2
    assert result.stop_reason == "end_turn"
    assert result.input_tokens == 70  # summed across both calls
    assert result.output_tokens == 23
    assert executor_calls == [("get_topology", {"hint": "fabric"})]
    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert isinstance(call, ToolCall)
    assert call.id == "tu_1"
    assert call.name == "get_topology"
    assert call.input == {"hint": "fabric"}
    assert call.output == {"leaves": 2, "spines": 4, "hosts_per_leaf": 8}
    assert json.loads(call.output_serialized) == call.output

    # Second messages.create should have received the assistant turn + tool_result
    second_call_messages = api.calls[1]["messages"]
    assert len(second_call_messages) == 3  # original user, assistant, tool_result
    assistant_msg = second_call_messages[1]
    assert assistant_msg["role"] == "assistant"
    assistant_blocks = assistant_msg["content"]
    assert {"type": "text", "text": "let me check"} in assistant_blocks
    assert any(
        b.get("type") == "tool_use" and b["id"] == "tu_1" and b["name"] == "get_topology"
        for b in assistant_blocks
    )
    tool_result_msg = second_call_messages[2]
    assert tool_result_msg["role"] == "user"
    assert tool_result_msg["content"][0]["type"] == "tool_result"
    assert tool_result_msg["content"][0]["tool_use_id"] == "tu_1"


@pytest.mark.asyncio
async def test_complete_with_tools_string_output_passes_through():
    """Executor returning a plain string should not be JSON-wrapped."""
    client, _ = _make_scripted_client(
        [
            _FakeMessage(
                content=[_FakeToolUseBlock(id="tu_1", name="t", input={})],
                model="m",
                usage=_FakeUsage(input_tokens=1, output_tokens=1),
                stop_reason="tool_use",
            ),
            _FakeMessage(
                content=[_FakeTextBlock(text="ok")],
                model="m",
                usage=_FakeUsage(input_tokens=1, output_tokens=1),
                stop_reason="end_turn",
            ),
        ]
    )

    async def executor(name: str, args: dict[str, Any]) -> str:
        return "raw string output"

    result = await client.complete_with_tools(
        system="s",
        user="u",
        tools=[{"name": "t", "description": "d", "input_schema": {"type": "object"}}],
        tool_executor=executor,
    )
    assert result.tool_calls[0].output_serialized == "raw string output"


@pytest.mark.asyncio
async def test_complete_with_tools_max_iterations_terminates_loop():
    """If the model keeps requesting tools past max_iterations, return cleanly."""
    # Three responses all of which are tool_use; max_iterations=2 should stop
    # after iteration 2 with stop_reason="max_iterations".
    api = _ScriptedMessagesAPI(
        [
            _FakeMessage(
                content=[_FakeToolUseBlock(id=f"tu_{i}", name="t", input={})],
                model="m",
                usage=_FakeUsage(input_tokens=1, output_tokens=1),
                stop_reason="tool_use",
            )
            for i in range(5)
        ]
    )
    client = ModelClient(client=_FakeClient(messages=api), model="m")

    async def executor(name: str, args: dict[str, Any]) -> str:
        return "ok"

    result = await client.complete_with_tools(
        system="s",
        user="u",
        tools=[{"name": "t", "description": "d", "input_schema": {"type": "object"}}],
        tool_executor=executor,
        max_iterations=2,
    )
    assert result.stop_reason == "max_iterations"
    assert result.iterations == 2
    assert len(result.tool_calls) == 2


@pytest.mark.asyncio
async def test_complete_with_tools_handles_parallel_tool_use_blocks():
    """A single response with multiple tool_use blocks dispatches all of them."""
    client, api = _make_scripted_client(
        [
            _FakeMessage(
                content=[
                    _FakeToolUseBlock(id="tu_a", name="t", input={"k": "a"}),
                    _FakeToolUseBlock(id="tu_b", name="t", input={"k": "b"}),
                ],
                model="m",
                usage=_FakeUsage(input_tokens=5, output_tokens=2),
                stop_reason="tool_use",
            ),
            _FakeMessage(
                content=[_FakeTextBlock(text="done")],
                model="m",
                usage=_FakeUsage(input_tokens=10, output_tokens=3),
                stop_reason="end_turn",
            ),
        ]
    )

    async def executor(name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"echo": args["k"]}

    result = await client.complete_with_tools(
        system="s",
        user="u",
        tools=[{"name": "t", "description": "d", "input_schema": {"type": "object"}}],
        tool_executor=executor,
    )
    assert len(result.tool_calls) == 2
    assert {tc.id for tc in result.tool_calls} == {"tu_a", "tu_b"}
    second_call_user_msg = api.calls[1]["messages"][2]
    assert second_call_user_msg["role"] == "user"
    assert len(second_call_user_msg["content"]) == 2  # both tool_results in one message


@pytest.mark.requires_anthropic
def test_from_settings_smoke_real_api():
    """Live smoke test — only runs when explicitly enabled."""
    from harnessit.config import load_settings

    settings = load_settings()
    client = ModelClient.from_settings(settings, default_max_tokens=64)
    result = client.complete(
        system="Reply with the single word OK and nothing else.",
        user="ping",
    )
    assert result.text.strip().upper().startswith("OK")
    assert result.input_tokens > 0
    assert result.output_tokens > 0
