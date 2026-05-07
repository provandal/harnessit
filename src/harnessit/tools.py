"""Stage 3 tool surface — read tools delegating through the Substrate Adapter.

Per Build Plan v0.3 §2.1 stage 3: MCP read tools that let the agent
query topology, fetch counters, read configs, tail logs. v1 of this
module ships exactly one tool — ``get_topology`` — so we can isolate
the marginal value of one tool before adding more (the lesson from
Stage 2 v1: don't ship the whole surface in one commit; let the eval
data tell us which tools matter).

The agent-visible schema for ``get_topology`` takes no arguments — from
the agent's perspective, it's "show me the fabric I'm troubleshooting."
The harness binds the current eval scenario's name internally and
forwards to ``DoppelgangerClient.get_topology(name)``. This indirection
matters: in production the agent doesn't know it's in an eval, so the
tool surface should not require eval-shape inputs.

Every tool invocation is wrapped in a Langfuse/OTel span under the
``harnessit.tools.*`` namespace per Architecture v0.5 §9.4. Span input
captures the agent's arguments + the bound scenario; output captures
the structural data; metadata carries the response-envelope fields
(``source``, ``confidence``, ``staleness_class``, ``observed_at_ns``).

Use::

    tools = Tools(substrate=client, scenario_name="microburst")
    completion = await model_client.complete_with_tools(
        system=...,
        user=...,
        tools=tools.schemas,
        tool_executor=tools.execute,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langfuse import get_client, observe

from harnessit.substrate import DoppelgangerClient


GET_TOPOLOGY_SCHEMA: dict[str, Any] = {
    "name": "get_topology",
    "description": (
        "Return the topology of the RDMA leaf-spine fabric you are "
        "investigating: number of leaves and spines, hosts per leaf, "
        "host-to-leaf assignment (host node IDs), link bandwidth and "
        "delay parameters, ECMP layout, congestion-control mode, and "
        "any path asymmetry. No arguments — equivalent to 'show me the "
        "fabric I'm troubleshooting.'"
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


@dataclass(frozen=True)
class ToolError:
    """Returned to the model as a tool_result when a tool call fails.

    Encoded as JSON in the tool_result content; the model can decide
    how to recover. Errors are *not* raised through the executor —
    that would terminate the loop, and we want the model to be able to
    react.
    """

    tool: str
    message: str

    def to_payload(self) -> dict[str, Any]:
        return {"error": True, "tool": self.tool, "message": self.message}


class Tools:
    """Stage 3 tool surface bound to one eval scenario.

    The agent-visible schemas live on ``schemas``; the dispatcher lives
    on ``execute``. ``scenario_name`` is the eval-time binding the
    harness uses when forwarding agent calls (which carry no scenario
    name) to the Substrate Adapter.
    """

    def __init__(
        self,
        *,
        substrate: DoppelgangerClient,
        scenario_name: str,
    ) -> None:
        self._substrate = substrate
        self._scenario_name = scenario_name

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """Anthropic tool schemas for the ``tools=`` parameter of messages.create."""
        return [GET_TOPOLOGY_SCHEMA]

    async def execute(self, name: str, args: dict[str, Any]) -> Any:
        """Dispatch a tool_use block to the matching executor.

        Returns whatever the executor produces; the caller (the model
        loop in ``ModelClient.complete_with_tools``) is responsible for
        serializing the return value into the ``tool_result`` block.
        Unknown tools return a ``ToolError`` payload rather than
        raising, so the loop can continue and the model can recover.
        """
        if name == "get_topology":
            return await self._get_topology(args)
        return ToolError(
            tool=name,
            message=(
                f"Unknown tool {name!r}. Available tools: "
                + ", ".join(s["name"] for s in self.schemas)
            ),
        ).to_payload()

    @observe(
        name="harnessit.tools.get_topology",
        as_type="span",
        capture_input=False,
        capture_output=False,
    )
    async def _get_topology(self, args: dict[str, Any]) -> dict[str, Any]:
        """Forward to ``DoppelgangerClient.get_topology`` with the bound scenario.

        Surfaces the response-envelope metadata onto the active span as
        Langfuse-side ``metadata`` — that's where SREs need
        ``source``/``staleness_class`` visibility for the trajectory
        viewer (Stage 4) to render tool calls with provenance.
        """
        envelope = await self._substrate.get_topology_envelope(self._scenario_name)
        data = envelope["data"]
        get_client().update_current_span(
            input={
                "agent_args": args,
                "bound_scenario": self._scenario_name,
            },
            output=data,
            metadata={
                "source": envelope.get("source"),
                "confidence": envelope.get("confidence"),
                "staleness_class": envelope.get("staleness_class"),
                "observed_at_ns": envelope.get("observed_at_ns"),
            },
        )
        return data


__all__ = [
    "GET_TOPOLOGY_SCHEMA",
    "ToolError",
    "Tools",
]
