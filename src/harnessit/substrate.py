"""MCP client to the Doppelgänger Substrate Adapter.

Stage 2 talks to the substrate exclusively through the Adapter's MCP
surface (per Erik's eval-framework-scope decision 2026-05-05). The
adapter exposes three tools defined in
``doppelganger.adapter.server.build_server`` and documented in
Doppelgänger v0.2 §2.3:

* ``list_scenarios`` — registry of named scenarios
* ``run_scenario(name, run_id)`` — run one scenario end-to-end
* ``compare_runs(baseline_trace_dir, injected_trace_dir)`` — re-parse
  and diff two completed runs

The client unwraps Doppelgänger's response envelope and returns the
``data`` payload. Envelope metadata (``observed_at_ns``, ``source``,
``confidence``, ``staleness_class``) is preserved on the raw result for
callers that need it; eval-framework code currently only needs ``data``.

Use::

    async with DoppelgangerClient.connect() as dopp:
        scenarios = await dopp.list_scenarios()
        baseline = await dopp.run_scenario("spike-burst-baseline")
        injected = await dopp.run_scenario("spike-burst-silent-drops")
        diff = await dopp.compare_runs(
            baseline["trace_dir"], injected["trace_dir"],
        )
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

DEFAULT_COMMAND = "python"
DEFAULT_ARGS: tuple[str, ...] = ("-m", "doppelganger.adapter")


class SubstrateError(RuntimeError):
    """Raised when the Doppelgänger Adapter returns an error or a
    malformed envelope."""


@dataclass(frozen=True)
class Envelope:
    """Doppelgänger v0.2 §2.3 response envelope, minus ``data``.

    ``data`` is returned separately by helper methods so callers don't
    have to reach into the envelope every time.
    """

    source: str
    observed_at_ns: int | None
    confidence: str
    staleness_class: str
    raw: dict[str, Any] = field(repr=False)


class DoppelgangerClient:
    """Async MCP client to the Doppelgänger Substrate Adapter.

    Construct via the ``connect`` async context manager so subprocess
    + session lifecycle is handled correctly. Direct instantiation is
    intended for testing where ``_session`` is monkey-patched.
    """

    def __init__(self, *, session: ClientSession) -> None:
        self._session = session

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        *,
        command: str = DEFAULT_COMMAND,
        args: tuple[str, ...] = DEFAULT_ARGS,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> AsyncIterator["DoppelgangerClient"]:
        """Spawn the adapter subprocess, initialize the session, yield a client.

        ``env`` defaults to ``os.environ.copy()`` so the adapter inherits
        ``PATH`` (Docker / python on Windows + POSIX) and any
        ``ANTHROPIC_API_KEY`` / ``LANGFUSE_*`` keys callers happen to
        export. Pass ``env=...`` explicitly to scope-down for security.
        """
        params = StdioServerParameters(
            command=command,
            args=list(args),
            env=env if env is not None else os.environ.copy(),
            cwd=cwd,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield cls(session=session)

    async def list_tools(self) -> list[str]:
        """Return the names of tools advertised by the adapter."""
        result = await self._session.list_tools()
        return [t.name for t in result.tools]

    async def list_scenarios(self) -> list[dict[str, Any]]:
        """Return the scenario registry (``data`` field of the envelope)."""
        envelope = await self._call("list_scenarios", {})
        return envelope["data"]

    async def get_topology(self, name: str) -> dict[str, Any]:
        """Return the topology declaration of a named scenario.

        Returns the structural payload — ``shape``/``leaves``/``spines``/
        ``leaf_switches``/``spine_switches``/``host_link``/``spine_link``/
        ``asymmetry``/``congestion_control`` — for scenarios with a
        custom topology, or a degraded payload (``shape ==
        "substrate-bundled"``) for spike-burst* scenarios that pin to a
        substrate-shipped topology file.

        Eval ground-truth metadata (intended_symptom, root_cause) is
        deliberately not surfaced; the Adapter filters it out so this
        tool is safe to expose to the agent under tool use.
        """
        envelope = await self._call("get_topology", {"name": name})
        return envelope["data"]

    async def get_topology_envelope(self, name: str) -> dict[str, Any]:
        """Same as ``get_topology`` but returns the full envelope.

        Callers that need the response-envelope metadata
        (``source``/``observed_at_ns``/``confidence``/``staleness_class``)
        — e.g. to attach to a Langfuse span as tool metadata — use this
        variant instead of unwrapping ``data``.
        """
        return await self._call("get_topology", {"name": name})

    async def run_scenario(
        self,
        name: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a named scenario end-to-end. Returns the run-result data dict.

        The returned dict carries the keys documented in
        ``doppelganger.adapter.server.run_scenario``: ``scenario``,
        ``run_id``, ``trace_dir``, ``compiled_config_path``,
        ``wall_clock_seconds``, ``summary``, ``flows``.
        """
        args: dict[str, Any] = {"name": name}
        if run_id is not None:
            args["run_id"] = run_id
        envelope = await self._call("run_scenario", args)
        return envelope["data"]

    async def compare_runs(
        self,
        baseline_trace_dir: str,
        injected_trace_dir: str,
    ) -> dict[str, Any]:
        """Compare two completed runs (re-parses ``fct.txt`` from disk)."""
        envelope = await self._call(
            "compare_runs",
            {
                "baseline_trace_dir": str(baseline_trace_dir),
                "injected_trace_dir": str(injected_trace_dir),
            },
        )
        return envelope["data"]

    async def _call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self._session.call_tool(tool_name, arguments=arguments)
        if getattr(result, "isError", False):
            raise SubstrateError(
                f"Doppelgänger adapter returned error for {tool_name!r}: "
                f"{_render_content(result.content)}"
            )
        return _decode_envelope(tool_name, result.content)


def _decode_envelope(
    tool_name: str,
    content: list[Any],
) -> dict[str, Any]:
    """Pull the JSON-encoded envelope out of an MCP tool result.

    FastMCP serializes dict returns as a single TextContent block whose
    ``.text`` is a JSON-encoded dict. Robust to multi-block responses by
    concatenating text content.
    """
    text = "".join(
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", None) == "text"
    )
    if not text:
        raise SubstrateError(
            f"{tool_name!r} returned no text content: "
            f"{_render_content(content)}"
        )
    try:
        envelope = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SubstrateError(
            f"{tool_name!r} returned non-JSON text: {text[:200]!r}"
        ) from exc
    if not isinstance(envelope, dict) or "data" not in envelope:
        raise SubstrateError(
            f"{tool_name!r} returned malformed envelope (missing 'data'): "
            f"{envelope!r}"
        )
    return envelope


def _render_content(content: list[Any]) -> str:
    return ", ".join(repr(getattr(b, "text", b)) for b in content) or "<empty>"


def envelope_metadata(raw: dict[str, Any]) -> Envelope:
    """Extract the v0.2 §2.3 envelope metadata from a raw call result.

    Helper for callers that need ``source``/``observed_at_ns``/etc. in
    addition to ``data``. Use this when raw access is preserved (the
    private ``_call`` returns the full dict).
    """
    return Envelope(
        source=raw.get("source", ""),
        observed_at_ns=raw.get("observed_at_ns"),
        confidence=raw.get("confidence", "unknown"),
        staleness_class=raw.get("staleness_class", "unknown"),
        raw=raw,
    )
