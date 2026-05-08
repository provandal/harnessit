"""Eval scenarios shipped with HarnessIT.

Stage 3 ships microburst-localization in three variants — symptom-only,
symptom-plus-topology (prompt-fed), and symptom-plus-topology-tool
(agent queries via tool). The first two are naked single-shot; the
third uses the harness tool surface. Stage 5a adds an ECN-misconfig
gap-measurement scenario (``pfc_storm_with_counters_tool``) that
reads the substrate's ``pfc_storm(ecn_misconfigured=True)`` fault and
gives the agent both topology and fabric-counters tools but no skill.
"""

from harnessit.scenarios.microburst import (
    microburst_symptom_only,
    microburst_with_topology,
    microburst_with_topology_tool,
)
from harnessit.scenarios.pfc_storm import (
    pfc_storm_with_counters_tool,
)

__all__ = [
    "microburst_symptom_only",
    "microburst_with_topology",
    "microburst_with_topology_tool",
    "pfc_storm_with_counters_tool",
]
