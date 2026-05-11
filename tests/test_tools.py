"""Tests for harnessit.tools — Stage 3 tool surface, hermetic.

Uses a stub DoppelgangerClient that returns canned envelopes. Live MCP
round-trips through the real Adapter are covered by
``test_substrate.py``'s ``requires_substrate`` tests.
"""

from __future__ import annotations

from typing import Any

import pytest

from harnessit.tools import (
    GET_FABRIC_COUNTERS_SCHEMA,
    GET_FLOW_RECORDS_SCHEMA,
    GET_TOPOLOGY_SCHEMA,
    ToolError,
    Tools,
)


class _StubSubstrate:
    """Stand-in for DoppelgangerClient that returns staged envelopes.

    Records each call so tests can assert on argument forwarding.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._next_envelope: dict[str, Any] | None = None

    def stage(self, envelope: dict[str, Any]) -> None:
        self._next_envelope = envelope

    async def get_topology_envelope(self, name: str) -> dict[str, Any]:
        self.calls.append(("get_topology_envelope", {"name": name}))
        if self._next_envelope is None:
            raise AssertionError("test forgot to stage an envelope")
        envelope, self._next_envelope = self._next_envelope, None
        return envelope

    async def get_fabric_counters_envelope(self, name: str) -> dict[str, Any]:
        self.calls.append(("get_fabric_counters_envelope", {"name": name}))
        if self._next_envelope is None:
            raise AssertionError("test forgot to stage an envelope")
        envelope, self._next_envelope = self._next_envelope, None
        return envelope

    async def get_flow_records_envelope(self, name: str) -> dict[str, Any]:
        self.calls.append(("get_flow_records_envelope", {"name": name}))
        if self._next_envelope is None:
            raise AssertionError("test forgot to stage an envelope")
        envelope, self._next_envelope = self._next_envelope, None
        return envelope


# --------------------------------------------------------------- schema

def test_get_topology_schema_takes_no_args():
    """Agent-visible schema must not require args; the harness binds the
    scenario name from EvalContext, agent only asks 'show me the fabric.'"""
    assert GET_TOPOLOGY_SCHEMA["name"] == "get_topology"
    schema = GET_TOPOLOGY_SCHEMA["input_schema"]
    assert schema["type"] == "object"
    assert schema["properties"] == {}
    assert schema["required"] == []


def test_tools_exposes_all_schemas():
    tools = Tools(substrate=_StubSubstrate(), scenario_name="microburst")
    names = [s["name"] for s in tools.schemas]
    assert "get_topology" in names
    assert "get_fabric_counters" in names
    assert "get_flow_records" in names


def test_get_fabric_counters_schema_takes_no_args():
    """Same agent-visible contract as get_topology: no args, harness binds
    the scenario name internally."""
    assert GET_FABRIC_COUNTERS_SCHEMA["name"] == "get_fabric_counters"
    schema = GET_FABRIC_COUNTERS_SCHEMA["input_schema"]
    assert schema["type"] == "object"
    assert schema["properties"] == {}
    assert schema["required"] == []


def test_get_fabric_counters_schema_describes_both_counter_classes():
    """Constraint memory: the schema description must signal that both
    PFC and ECN-CN counters come back together — splitting the
    description across separate tools would re-leak the answer key."""
    description = GET_FABRIC_COUNTERS_SCHEMA["description"].lower()
    assert "pfc" in description
    assert "ecn" in description


def test_get_flow_records_schema_takes_no_args():
    """Agent-visible contract: no args, harness binds the scenario name
    internally."""
    assert GET_FLOW_RECORDS_SCHEMA["name"] == "get_flow_records"
    schema = GET_FLOW_RECORDS_SCHEMA["input_schema"]
    assert schema["type"] == "object"
    assert schema["properties"] == {}
    assert schema["required"] == []


def test_get_flow_records_schema_describes_per_flow_shape_and_summary():
    """The description must signal what's returned: per-flow records
    with 5-tuple + FCT, plus the summary with counts and distribution.
    These are the load-bearing fields for silent-drops + microburst
    diagnostic paths."""
    description = GET_FLOW_RECORDS_SCHEMA["description"].lower()
    assert "fct" in description
    assert "5-tuple" in description or "sip" in description
    assert "summary" in description
    # Should mention completion-status counts as the silent-drops signal
    assert "incomplete" in description or "completion" in description


# ------------------------------------------------------------ execute

@pytest.mark.asyncio
async def test_execute_get_topology_forwards_bound_scenario_name(exporter):
    """Agent calls get_topology() with no args; harness fills in the bound
    scenario name when forwarding to the substrate."""
    substrate = _StubSubstrate()
    substrate.stage({
        "data": {"shape": "leaf-spine", "leaves": 2, "spines": 4},
        "source": "adapter.scenario_topology('microburst')",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "fresh",
    })
    tools = Tools(substrate=substrate, scenario_name="microburst")
    result = await tools.execute("get_topology", {})

    assert result == {"shape": "leaf-spine", "leaves": 2, "spines": 4}
    assert substrate.calls == [("get_topology_envelope", {"name": "microburst"})]


@pytest.mark.asyncio
async def test_execute_get_topology_returns_only_data_to_model(exporter):
    """Envelope metadata stays out of the tool_result; the agent sees data only.
    Source/staleness/confidence are captured on the OTel span instead."""
    substrate = _StubSubstrate()
    substrate.stage({
        "data": {"leaves": 2, "spines": 1},  # post-Task-#8 pfc_storm shape
        "source": "adapter.scenario_topology('pfc-storm')",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "fresh",
    })
    tools = Tools(substrate=substrate, scenario_name="pfc-storm")
    result = await tools.execute("get_topology", {})

    # Result is just data; envelope metadata is not returned to the model
    assert "source" not in result
    assert "confidence" not in result
    assert "staleness_class" not in result


@pytest.mark.asyncio
async def test_execute_unknown_tool_returns_tool_error_payload(exporter):
    """Unknown tools return an error payload (not a raised exception),
    so the model loop can continue and the model can recover."""
    substrate = _StubSubstrate()
    tools = Tools(substrate=substrate, scenario_name="microburst")
    result = await tools.execute("nonexistent_tool", {"x": 1})

    assert isinstance(result, dict)
    assert result["error"] is True
    assert result["tool"] == "nonexistent_tool"
    assert "get_topology" in result["message"]


def test_tool_error_to_payload_shape():
    err = ToolError(tool="foo", message="bad")
    assert err.to_payload() == {"error": True, "tool": "foo", "message": "bad"}


# ---------------------------------------------------- OTel span emission

@pytest.mark.asyncio
async def test_execute_get_fabric_counters_forwards_bound_scenario_name(exporter):
    substrate = _StubSubstrate()
    substrate.stage({
        "data": {
            "scenario": "pfc-storm",
            "ports": [
                {
                    "node_id": 16, "node_type": 1, "if_index": 1,
                    "pfc_pause_sent": 12, "pfc_pause_rcvd": 0,
                    "pfc_resume_sent": 12, "pfc_resume_rcvd": 0,
                    "ecn_marks_sent": 0,
                }
            ],
        },
        "source": "driver.run_scenario('pfc-storm')+counters_aggregate",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "fresh",
    })
    tools = Tools(substrate=substrate, scenario_name="pfc-storm")
    result = await tools.execute("get_fabric_counters", {})

    # No fabric-wide totals row (Stage 5a closing-test finding 2026-05-08:
    # pre-aggregating totals leaked the asymmetry diagnostic).
    assert "totals" not in result
    # Asymmetry preserved: every port record carries both classes
    for rec in result["ports"]:
        assert "pfc_pause_sent" in rec
        assert "ecn_marks_sent" in rec
    assert substrate.calls == [
        ("get_fabric_counters_envelope", {"name": "pfc-storm"})
    ]


@pytest.mark.asyncio
async def test_get_fabric_counters_emits_span_under_harnessit_tools_namespace(exporter):
    substrate = _StubSubstrate()
    substrate.stage({
        "data": {"ports": []},
        "source": "driver.run_scenario('pfc-storm')+counters_aggregate",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "fresh",
    })
    tools = Tools(substrate=substrate, scenario_name="pfc-storm")
    await tools.execute("get_fabric_counters", {})

    from langfuse import get_client
    get_client().flush()
    spans = exporter.get_finished_spans()
    matching = [s for s in spans if s.name == "harnessit.tools.get_fabric_counters"]
    assert len(matching) == 1, (
        f"expected one harnessit.tools.get_fabric_counters span, "
        f"got {[s.name for s in spans]}"
    )


@pytest.mark.asyncio
async def test_get_topology_emits_span_under_harnessit_tools_namespace(exporter):
    """Architecture v0.5 §9.4: every tool call emits an OTel span under
    the harnessit.tools.* namespace."""
    substrate = _StubSubstrate()
    substrate.stage({
        "data": {"shape": "leaf-spine"},
        "source": "adapter.scenario_topology('microburst')",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "fresh",
    })
    tools = Tools(substrate=substrate, scenario_name="microburst")
    await tools.execute("get_topology", {})

    from langfuse import get_client
    get_client().flush()
    spans = exporter.get_finished_spans()
    matching = [s for s in spans if s.name == "harnessit.tools.get_topology"]
    assert len(matching) == 1, (
        f"expected exactly one harnessit.tools.get_topology span, "
        f"got {[s.name for s in spans]}"
    )


@pytest.mark.asyncio
async def test_execute_get_flow_records_forwards_bound_scenario_name(exporter):
    substrate = _StubSubstrate()
    substrate.stage({
        "data": {
            "run_id": "run-abc123",
            "trace_dir": "/traces/run-abc123",
            "summary": {
                "total": 15,
                "completed": 15,
                "incomplete": 0,
                "by_status": {"completed": 15},
                "fct": {
                    "n": 15, "min_ns": 1000, "p50_ns": 1500, "p90_ns": 2000,
                    "p99_ns": 2500, "p999_ns": 2700, "max_ns": 2800,
                    "mean_ns": 1700.0,
                },
            },
            "flows": [
                {
                    "sip": "0b000001", "dip": "0b000201",
                    "sport": 10001, "dport": 10001,
                    "status": "completed",
                    "actual_size_bytes": 7500000,
                    "actual_start_ns": 50_000_000,
                    "fct_ns": 1500,
                    "standalone_fct_ns": 1000,
                    "slowdown": 1.5,
                },
            ],
        },
        "source": "driver.run_scenario('microburst')+fct_parse",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "fresh",
    })
    tools = Tools(substrate=substrate, scenario_name="microburst")
    result = await tools.execute("get_flow_records", {})

    # Per-flow array is present + each record has the expected fields
    assert isinstance(result["flows"], list)
    assert len(result["flows"]) == 1
    record = result["flows"][0]
    for field in ("sip", "dip", "sport", "dport", "status",
                  "fct_ns", "standalone_fct_ns", "slowdown",
                  "actual_size_bytes", "actual_start_ns"):
        assert field in record, f"flow record missing {field}"
    # Summary is surfaced alongside the per-flow array
    assert result["summary"]["total"] == 15
    assert result["summary"]["completed"] == 15
    assert result["summary"]["fct"]["p99_ns"] == 2500
    assert substrate.calls == [
        ("get_flow_records_envelope", {"name": "microburst"})
    ]


@pytest.mark.asyncio
async def test_get_flow_records_emits_span_under_harnessit_tools_namespace(exporter):
    substrate = _StubSubstrate()
    substrate.stage({
        "data": {"run_id": "run-x", "trace_dir": "/traces/run-x",
                 "summary": {"total": 0, "completed": 0, "incomplete": 0,
                             "by_status": {}, "fct": {"n": 0, "min_ns": 0,
                             "p50_ns": 0, "p90_ns": 0, "p99_ns": 0,
                             "p999_ns": 0, "max_ns": 0, "mean_ns": 0.0}},
                 "flows": []},
        "source": "driver.run_scenario('microburst')+fct_parse",
        "observed_at_ns": None,
        "confidence": "high",
        "staleness_class": "fresh",
    })
    tools = Tools(substrate=substrate, scenario_name="microburst")
    await tools.execute("get_flow_records", {})

    from langfuse import get_client
    get_client().flush()
    spans = exporter.get_finished_spans()
    matching = [s for s in spans if s.name == "harnessit.tools.get_flow_records"]
    assert len(matching) == 1, (
        f"expected one harnessit.tools.get_flow_records span, "
        f"got {[s.name for s in spans]}"
    )
