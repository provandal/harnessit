"""Tests for harnessit.tools — Stage 3 tool surface, hermetic.

Uses a stub DoppelgangerClient that returns canned envelopes. Live MCP
round-trips through the real Adapter are covered by
``test_substrate.py``'s ``requires_substrate`` tests.
"""

from __future__ import annotations

from typing import Any

import pytest

from harnessit.tools import GET_TOPOLOGY_SCHEMA, ToolError, Tools


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


# --------------------------------------------------------------- schema

def test_get_topology_schema_takes_no_args():
    """Agent-visible schema must not require args; the harness binds the
    scenario name from EvalContext, agent only asks 'show me the fabric.'"""
    assert GET_TOPOLOGY_SCHEMA["name"] == "get_topology"
    schema = GET_TOPOLOGY_SCHEMA["input_schema"]
    assert schema["type"] == "object"
    assert schema["properties"] == {}
    assert schema["required"] == []


def test_tools_exposes_get_topology_in_schemas():
    tools = Tools(substrate=_StubSubstrate(), scenario_name="microburst")
    names = [s["name"] for s in tools.schemas]
    assert names == ["get_topology"]


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
