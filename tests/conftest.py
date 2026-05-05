"""Pytest helpers for harnessit.

Live-credential tests are gated by markers and auto-skipped unless the
corresponding ``HARNESSIT_LIVE_*`` env var is set. This keeps the
default test run hermetic (no network, no API spend) while letting
developers opt into the gated set explicitly.

Marker → env-var mapping:

* ``@pytest.mark.requires_anthropic``  →  ``HARNESSIT_LIVE_ANTHROPIC=1``
* ``@pytest.mark.requires_langfuse``   →  ``HARNESSIT_LIVE_LANGFUSE=1``
* ``@pytest.mark.requires_substrate``  →  ``HARNESSIT_LIVE_SUBSTRATE=1``
"""

from __future__ import annotations

import os

import pytest

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
