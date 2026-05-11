"""Eval scenarios shipped with HarnessIT.

Stage 3 ships microburst-localization in three variants — symptom-only,
symptom-plus-topology (prompt-fed), and symptom-plus-topology-tool
(agent queries via tool). Stage 5a adds an ECN-misconfig gap-measurement
scenario (``pfc_storm_with_counters_tool``) and its production-shaped
counterpart (``pfc_storm_realistic_with_counters_tool``) that read the
substrate's ``pfc_storm(ecn_misconfigured=True)`` fault and give the
agent both topology and fabric-counters tools but no skill.

The 2026-05-11 capability-envelope sweep adds four more
``with_counters_tool`` variants — microburst, asymmetric_path,
hash_polarization, silent_drops — under one harness configuration
(tools=topology+counters, no skill, default topology per scenario,
5-criterion LLM rubric). Together with the Stage 5a-realistic baseline,
they form the 5-row sweep that maps naked-Opus-with-tools capability
across §5.2 fault classes before any Stage 5b skill is designed. See
``project_capability_envelope_sweep_2026_05_11.md`` for the sweep
design + pre-registered predictions.
"""

from harnessit.scenarios.asymmetric_path import (
    asymmetric_path_with_counters_tool,
)
from harnessit.scenarios.hash_polarization import (
    hash_polarization_with_counters_tool,
)
from harnessit.scenarios.microburst import (
    microburst_symptom_only,
    microburst_with_counters_tool,
    microburst_with_topology,
    microburst_with_topology_tool,
)
from harnessit.scenarios.pfc_storm import (
    pfc_storm_realistic_with_counters_tool,
    pfc_storm_with_counters_tool,
)
from harnessit.scenarios.silent_drops import (
    silent_drops_with_counters_tool,
)

__all__ = [
    "microburst_symptom_only",
    "microburst_with_topology",
    "microburst_with_topology_tool",
    "microburst_with_counters_tool",
    "pfc_storm_with_counters_tool",
    "pfc_storm_realistic_with_counters_tool",
    "asymmetric_path_with_counters_tool",
    "hash_polarization_with_counters_tool",
    "silent_drops_with_counters_tool",
]
