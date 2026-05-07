"""Eval scenarios shipped with HarnessIT.

Stage 3 ships microburst-localization in three variants — symptom-only,
symptom-plus-topology (prompt-fed), and symptom-plus-topology-tool
(agent queries via tool). The first two are naked single-shot; the
third uses the harness tool surface. Stage 4+ adds scenarios as the
agent grows further capability.
"""

from harnessit.scenarios.microburst import (
    microburst_symptom_only,
    microburst_with_topology,
    microburst_with_topology_tool,
)

__all__ = [
    "microburst_symptom_only",
    "microburst_with_topology",
    "microburst_with_topology_tool",
]
