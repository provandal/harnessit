"""Tests for harnessit.tracing — Langfuse v4 instrumentation.

Uses OTel's InMemorySpanExporter to capture spans without network. The
underlying Langfuse client is real (talks to a fake exporter), so we
exercise the actual decorator + update_current_generation path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from harnessit.config import Settings
from harnessit.model import Completion, ModelClient
from harnessit.tracing import (
    GENERATION_SPAN_NAME,
    init_langfuse,
    traced_complete,
)


@dataclass
class _FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeMessage:
    content: list[Any]
    model: str
    usage: _FakeUsage
    stop_reason: str | None = "end_turn"


class _FakeMessagesAPI:
    def __init__(self, response: _FakeMessage) -> None:
        self.response = response

    def create(self, **_: Any) -> _FakeMessage:
        return self.response


@dataclass
class _FakeAnthropic:
    messages: _FakeMessagesAPI


def _model_client(text: str = "ack", model: str = "claude-opus-4-7") -> ModelClient:
    response = _FakeMessage(
        content=[_FakeTextBlock(text=text)],
        model=model,
        usage=_FakeUsage(input_tokens=11, output_tokens=3),
    )
    return ModelClient(
        client=_FakeAnthropic(messages=_FakeMessagesAPI(response)),
        model=model,
    )


@pytest.fixture(scope="session")
def in_memory_exporter() -> InMemorySpanExporter:
    """Initialize Langfuse with an in-memory OTel exporter, once per session.

    The Langfuse client is a singleton keyed by public_key, so this
    fixture initializes it the first time and the same exporter is
    reused for every test.
    """
    exporter = InMemorySpanExporter()
    settings = Settings(
        anthropic_api_key="sk-ant-test",
        langfuse_secret_key="sk-lf-test",
        langfuse_public_key="pk-lf-harnessit-tracing-tests",
        langfuse_base_url="https://localhost.invalid",
        model="claude-opus-4-7",
    )
    init_langfuse(settings, span_exporter=exporter, flush_at=1)
    return exporter


@pytest.fixture
def exporter(in_memory_exporter: InMemorySpanExporter) -> InMemorySpanExporter:
    from langfuse import get_client

    # Drain any in-flight spans from prior tests, then clear, so each
    # test starts with a verifiably empty exporter.
    get_client().flush()
    in_memory_exporter.clear()
    yield in_memory_exporter
    get_client().flush()
    in_memory_exporter.clear()


def _flush_and_get_spans(exporter: InMemorySpanExporter):
    from langfuse import get_client

    get_client().flush()
    return exporter.get_finished_spans()


def test_traced_complete_returns_completion(exporter):
    completion = traced_complete(
        _model_client(text="hello world"),
        system="be terse",
        user="ping",
    )
    assert isinstance(completion, Completion)
    assert completion.text == "hello world"
    assert completion.model == "claude-opus-4-7"
    assert completion.input_tokens == 11
    assert completion.output_tokens == 3


def test_traced_complete_emits_generation_span(exporter):
    traced_complete(
        _model_client(text="output text"),
        system="SYS",
        user="USR",
        scenario_name="silent-drops",
    )
    spans = _flush_and_get_spans(exporter)

    matching = [s for s in spans if s.name == GENERATION_SPAN_NAME]
    assert len(matching) == 1, f"expected one generation span, got {[s.name for s in spans]}"
    span = matching[0]

    attrs = span.attributes or {}
    assert attrs.get("langfuse.observation.type") == "generation"


def test_traced_complete_span_records_io_and_usage(exporter):
    traced_complete(
        _model_client(text="OK"),
        system="SYSTEM PROMPT",
        user="USER INPUT",
        scenario_name="silent-drops",
    )
    spans = _flush_and_get_spans(exporter)
    span = next(s for s in spans if s.name == GENERATION_SPAN_NAME)
    attrs = span.attributes or {}

    # Langfuse encodes dicts/lists as JSON strings; primitive values are
    # stored as native OTel attribute types.
    input_payload = json.loads(attrs["langfuse.observation.input"])
    assert input_payload == {"system": "SYSTEM PROMPT", "user": "USER INPUT"}

    assert attrs["langfuse.observation.output"] == "OK"
    assert attrs["langfuse.observation.model.name"] == "claude-opus-4-7"

    usage = json.loads(attrs["langfuse.observation.usage_details"])
    assert usage == {"input": 11, "output": 3}

    assert attrs["langfuse.observation.metadata.scenario_name"] == "silent-drops"
    assert attrs["langfuse.observation.metadata.stop_reason"] == "end_turn"


def test_traced_complete_without_scenario_name(exporter):
    traced_complete(
        _model_client(),
        system="s",
        user="u",
    )
    spans = _flush_and_get_spans(exporter)
    span = next(s for s in spans if s.name == GENERATION_SPAN_NAME)
    attrs = span.attributes or {}
    assert "langfuse.observation.metadata.scenario_name" not in attrs


def test_traced_complete_passes_max_tokens(exporter):
    """max_tokens flows through to the underlying ModelClient.complete."""
    captured: dict[str, Any] = {}

    class _RecordingMessagesAPI:
        def create(self, **kwargs: Any):
            captured.update(kwargs)
            return _FakeMessage(
                content=[_FakeTextBlock(text="x")],
                model="claude-opus-4-7",
                usage=_FakeUsage(input_tokens=1, output_tokens=1),
            )

    client = ModelClient(
        client=_FakeAnthropic(messages=_RecordingMessagesAPI()),
        model="claude-opus-4-7",
    )
    traced_complete(client, system="s", user="u", max_tokens=64)
    assert captured["max_tokens"] == 64


@pytest.mark.requires_langfuse
@pytest.mark.requires_anthropic
def test_traced_complete_live_emits_to_cloud():
    """End-to-end: live Anthropic call, span lands in real Langfuse Cloud."""
    from harnessit.config import load_settings

    settings = load_settings()
    init_langfuse(settings, flush_at=1)
    client = ModelClient.from_settings(settings, default_max_tokens=64)
    completion = traced_complete(
        client,
        system="Reply with the single word OK and nothing else.",
        user="ping",
        scenario_name="harnessit-c3-smoke",
    )
    from langfuse import get_client

    get_client().flush()
    assert completion.text.strip().upper().startswith("OK")
