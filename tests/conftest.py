"""Pytest helpers for harnessit.

Two responsibilities:

1. **Live-test gating.** Tests carrying ``requires_anthropic``,
   ``requires_langfuse``, or ``requires_substrate`` are auto-skipped
   unless the matching ``HARNESSIT_LIVE_*`` env var is set. Default
   ``pytest`` runs are hermetic — no network, no API spend.

2. **Shared Langfuse + InMemorySpanExporter fixture.** Langfuse v4
   uses a singleton client per public_key; spawning multiple test-only
   clients across test files trips on each other. This conftest owns
   the single test client + exporter at session scope, and exposes a
   per-test ``exporter`` fixture that drains and clears between tests.

Marker → env-var mapping:

* ``@pytest.mark.requires_anthropic``  →  ``HARNESSIT_LIVE_ANTHROPIC=1``
* ``@pytest.mark.requires_langfuse``   →  ``HARNESSIT_LIVE_LANGFUSE=1``
* ``@pytest.mark.requires_substrate``  →  ``HARNESSIT_LIVE_SUBSTRATE=1``
"""

from __future__ import annotations

import os

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from harnessit.config import Settings
from harnessit.tracing import init_langfuse

_GATES = {
    "requires_anthropic": "HARNESSIT_LIVE_ANTHROPIC",
    "requires_langfuse": "HARNESSIT_LIVE_LANGFUSE",
    "requires_substrate": "HARNESSIT_LIVE_SUBSTRATE",
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        for marker_name, env_var in _GATES.items():
            if marker_name in item.keywords and not os.environ.get(env_var):
                item.add_marker(
                    pytest.mark.skip(
                        reason=f"set {env_var}=1 to run {marker_name} tests"
                    )
                )


@pytest.fixture(scope="session")
def in_memory_exporter() -> InMemorySpanExporter:
    """Initialize the Langfuse test client + exporter exactly once."""
    exporter = InMemorySpanExporter()
    settings = Settings(
        anthropic_api_key="sk-ant-test",
        langfuse_secret_key="sk-lf-test",
        langfuse_public_key="pk-lf-harnessit-tests",
        langfuse_base_url="https://localhost.invalid",
        model="claude-opus-4-7",
    )
    init_langfuse(settings, span_exporter=exporter, flush_at=1)
    return exporter


@pytest.fixture
def exporter(in_memory_exporter: InMemorySpanExporter) -> InMemorySpanExporter:
    """Per-test exporter wrapper that drains pending spans + clears.

    The OTel BatchSpanProcessor queues spans across the @observe
    decorator boundary; flushing before clearing guarantees a clean
    start regardless of whether the prior test asserted on spans.
    """
    from langfuse import get_client

    get_client().flush()
    in_memory_exporter.clear()
    yield in_memory_exporter
    get_client().flush()
    in_memory_exporter.clear()
