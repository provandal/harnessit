"""Tests for harnessit.substrate — MCP client to Doppelgänger Adapter.

Unit tests use a fake ClientSession to exercise envelope decoding and
the public surface without spawning a subprocess. Gated tests spawn
the real ``doppelganger-adapter`` and verify end-to-end MCP wiring;
``requires_substrate`` because they assume the Doppelgänger package is
installed and (for ``run_scenario``) the Docker substrate image exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from harnessit.substrate import (
    DoppelgangerClient,
    Envelope,
    SubstrateError,
    _decode_envelope,
    envelope_metadata,
)


@dataclass
class _FakeTextContent:
    text: str
    type: str = "text"


@dataclass
class _FakeToolResult:
    content: list[Any]
    isError: bool = False


@dataclass
class _FakeListToolsResult:
    tools: list[Any]


@dataclass
class _FakeTool:
    name: str


class _FakeSession:
    def __init__(self) -> None:
        self.tool_call_log: list[tuple[str, dict[str, Any]]] = []
        self._tools: list[_FakeTool] = []
        self._next_result: _FakeToolResult | None = None

    def stage(self, envelope: dict[str, Any], *, is_error: bool = False) -> None:
        text = json.dumps(envelope)
        self._next_result = _FakeToolResult(
            content=[_FakeTextContent(text=text)],
            isError=is_error,
        )

    def stage_raw(self, content: list[Any], *, is_error: bool = False) -> None:
        self._next_result = _FakeToolResult(content=content, isError=is_error)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> _FakeToolResult:
        self.tool_call_log.append((name, arguments))
        if self._next_result is None:
            raise AssertionError("test forgot to stage a result")
        result, self._next_result = self._next_result, None
        return result

    async def list_tools(self) -> _FakeListToolsResult:
        return _FakeListToolsResult(tools=list(self._tools))


# ---------- _decode_envelope ----------

def test_decode_envelope_extracts_data():
    content = [_FakeTextContent(text=json.dumps({"data": [1, 2, 3], "source": "x"}))]
    envelope = _decode_envelope("list_scenarios", content)
    assert envelope["data"] == [1, 2, 3]
    assert envelope["source"] == "x"


def test_decode_envelope_concatenates_multiple_text_blocks():
    content = [
        _FakeTextContent(text='{"data": '),
        _FakeTextContent(text='[1,2]}'),
    ]
    envelope = _decode_envelope("list_scenarios", content)
    assert envelope["data"] == [1, 2]


def test_decode_envelope_raises_on_empty_content():
    with pytest.raises(SubstrateError, match="no text content"):
        _decode_envelope("list_scenarios", [])


def test_decode_envelope_raises_on_non_json():
    content = [_FakeTextContent(text="not json")]
    with pytest.raises(SubstrateError, match="non-JSON"):
        _decode_envelope("list_scenarios", content)


def test_decode_envelope_raises_on_missing_data_key():
    content = [_FakeTextContent(text=json.dumps({"source": "x"}))]
    with pytest.raises(SubstrateError, match="missing 'data'"):
        _decode_envelope("list_scenarios", content)


# ---------- DoppelgangerClient (mocked session) ----------

async def test_list_scenarios_returns_data_field():
    session = _FakeSession()
    client = DoppelgangerClient(session=session)
    session.stage({
        "data": [
            {"name": "spike-burst", "difficulty": "basic"},
            {"name": "spike-burst-silent-drops", "difficulty": "basic"},
        ],
        "source": "adapter.builtin_scenario_registry",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "fresh",
    })
    scenarios = await client.list_scenarios()
    assert len(scenarios) == 2
    assert scenarios[0]["name"] == "spike-burst"
    assert session.tool_call_log == [("list_scenarios", {})]


async def test_run_scenario_passes_run_id_when_provided():
    session = _FakeSession()
    client = DoppelgangerClient(session=session)
    session.stage({
        "data": {"scenario": "spike-burst", "run_id": "abc"},
        "source": "driver.run_scenario",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "fresh",
    })
    data = await client.run_scenario("spike-burst-baseline", run_id="abc")
    assert data["run_id"] == "abc"
    name, args = session.tool_call_log[0]
    assert name == "run_scenario"
    assert args == {"name": "spike-burst-baseline", "run_id": "abc"}


async def test_run_scenario_omits_run_id_when_none():
    session = _FakeSession()
    client = DoppelgangerClient(session=session)
    session.stage({"data": {}, "source": "x", "observed_at_ns": None,
                   "confidence": "high", "staleness_class": "fresh"})
    await client.run_scenario("spike-burst-baseline")
    _, args = session.tool_call_log[0]
    assert args == {"name": "spike-burst-baseline"}


async def test_compare_runs_passes_dirs():
    session = _FakeSession()
    client = DoppelgangerClient(session=session)
    session.stage({
        "data": {"flow_count_delta": -5, "findings": ["…"]},
        "source": "eval.compare_runs(parsed-from-disk)",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "stale",
    })
    data = await client.compare_runs("traces/baseline", "traces/injected")
    assert data["flow_count_delta"] == -5
    name, args = session.tool_call_log[0]
    assert name == "compare_runs"
    assert args == {
        "baseline_trace_dir": "traces/baseline",
        "injected_trace_dir": "traces/injected",
    }


async def test_get_topology_returns_data_field():
    session = _FakeSession()
    client = DoppelgangerClient(session=session)
    session.stage({
        "data": {
            "scenario": "microburst",
            "shape": "leaf-spine",
            "leaves": 2,
            "spines": 4,
            "hosts_per_leaf": 8,
        },
        "source": "adapter.scenario_topology('microburst')",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "fresh",
    })
    data = await client.get_topology("microburst")
    assert data["leaves"] == 2
    assert data["spines"] == 4
    name, args = session.tool_call_log[0]
    assert name == "get_topology"
    assert args == {"name": "microburst"}


async def test_get_topology_envelope_returns_full_envelope():
    """Callers that need source/staleness_class metadata use the envelope variant."""
    session = _FakeSession()
    client = DoppelgangerClient(session=session)
    session.stage({
        "data": {"scenario": "microburst", "shape": "leaf-spine"},
        "source": "adapter.scenario_topology('microburst')",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "fresh",
    })
    env = await client.get_topology_envelope("microburst")
    assert env["data"]["shape"] == "leaf-spine"
    assert env["source"] == "adapter.scenario_topology('microburst')"
    assert env["confidence"] == "high"
    assert env["staleness_class"] == "fresh"


async def test_call_raises_on_isError():
    session = _FakeSession()
    client = DoppelgangerClient(session=session)
    session.stage_raw([_FakeTextContent(text="boom")], is_error=True)
    with pytest.raises(SubstrateError, match="returned error"):
        await client.list_scenarios()


async def test_list_tools_returns_names():
    session = _FakeSession()
    session._tools = [_FakeTool("list_scenarios"), _FakeTool("run_scenario")]
    client = DoppelgangerClient(session=session)
    names = await client.list_tools()
    assert names == ["list_scenarios", "run_scenario"]


# ---------- Envelope helper ----------

def test_envelope_metadata_extracts_fields():
    raw = {
        "data": {"x": 1},
        "source": "test",
        "observed_at_ns": 12345,
        "confidence": "high",
        "staleness_class": "fresh",
    }
    env = envelope_metadata(raw)
    assert isinstance(env, Envelope)
    assert env.source == "test"
    assert env.observed_at_ns == 12345
    assert env.confidence == "high"
    assert env.staleness_class == "fresh"
    assert env.raw is raw


def test_envelope_metadata_defaults_for_missing_fields():
    env = envelope_metadata({"data": None})
    assert env.source == ""
    assert env.observed_at_ns is None
    assert env.confidence == "unknown"
    assert env.staleness_class == "unknown"


# ---------- Live MCP test (gated) ----------

@pytest.mark.requires_substrate
async def test_live_doppelganger_adapter_exposes_expected_tools():
    """Spawn the real ``doppelganger-adapter`` subprocess via MCP stdio.

    Verifies the Stage-1 follow-up "real MCP-client round-trip testing"
    that was deferred from Doppelgänger's stage 1 closeout. Doesn't run
    a scenario, so doesn't need the Docker substrate image — only the
    doppelganger Python package. Stage 3 added ``get_topology``;
    Stage 5a added ``get_fabric_counters``; step 2a (2026-05-11) added
    ``get_flow_records``.
    """
    expected = {
        "list_scenarios", "run_scenario", "get_topology",
        "get_fabric_counters", "get_flow_records", "get_host_counters",
        "compare_runs",
    }
    async with DoppelgangerClient.connect() as client:
        tools = set(await client.list_tools())
        assert expected <= tools


@pytest.mark.requires_substrate
async def test_live_doppelganger_adapter_get_topology_microburst():
    """get_topology against the real Adapter returns the microburst structure."""
    async with DoppelgangerClient.connect() as client:
        data = await client.get_topology("microburst")
        assert data["shape"] == "leaf-spine"
        assert data["leaves"] == 2
        assert data["spines"] == 4
        assert data["total_hosts"] == 16
        # Ground-truth metadata must NOT be exposed
        assert "intended_symptom" not in data
        assert "root_cause" not in data


@pytest.mark.requires_substrate
async def test_live_doppelganger_adapter_lists_scenarios():
    async with DoppelgangerClient.connect() as client:
        scenarios = await client.list_scenarios()
        names = {s["name"] for s in scenarios}
        assert "spike-burst-baseline" in names
        assert "spike-burst-silent-drops" in names
