"""Tests for harnessit.model — fake Anthropic client, no network."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from harnessit.model import Completion, ModelClient, _to_completion


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
