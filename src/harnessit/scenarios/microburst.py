"""Microburst-localization eval — three scenarios sharing one fault.

Three scenarios under the same underlying microburst fault. All
single-run (no paired baseline; real on-call doesn't get pre-paired
comparisons handed to it). They differ only in how the agent gets at
fabric context:

* ``microburst_symptom_only`` — bare ticket, no topology, no tools.
  Naked single-shot LLM call. The agent knows nothing about the fabric
  beyond what an outside observer reports. The honest failure mode is
  "I'd need topology info, telemetry, baseline comparison."
* ``microburst_with_topology`` — same ticket plus a "what we know
  about the fabric" preamble (leaf-spine layout, host assignment, link
  speeds). Naked single-shot. Demonstrates the marginal value of one
  piece of context.
* ``microburst_with_topology_tool`` — same bare ticket as
  symptom-only, but the agent has the ``get_topology`` MCP tool and
  can query fabric structure on demand. **Stage 3 closing test.** The
  pedagogical claim — "the harness adds capability the LLM doesn't
  have alone" — stands or falls on whether this variant scores closer
  to with-topology than to symptom-only. If the agent uses the tool
  and reaches comparable triage quality, the harness has earned its
  weight. If not, either the tool surface is wrong or the model
  doesn't reach for tools naturally; both are findings worth having.

Quantitative anchor: per the 2026-05-06 microburst recon
(traces/recon-microburst), default microburst() produces a 1.44x-2.63x
slowdown across 15 flows targeting host 0 (11.0.0.1) on a 16-host
2-leaf-4-spine fabric. The mean slowdown of ~1.5x is what a sysadmin
watching dashboards would report; we use that as the user-side anchor.
"""

from __future__ import annotations

from harnessit.eval.scoring import Score, score_triage_quality
from harnessit.eval.types import EvalContext, EvalScenario
from harnessit.model import Completion

SYSTEM_PROMPT = (
    "You are a network-investigation assistant for an RDMA leaf-spine "
    "fabric. Help the user diagnose their issue."
)

TARGET_SCENARIO = "microburst"

# The user-side ticket. Phrased as a sysadmin-reported symptom — what
# someone would see in their dashboard or get paged on. No failure-class
# menu, no pre-computed comparison, no per-flow data, no topology.
USER_TICKET = (
    "Hey network team — step time on jobs targeting host 11.0.0.1 is up "
    "about 1.5x compared to baseline. Started this morning around "
    "09:14 UTC. Can you help figure out what's going on?"
)

# The topology preamble for the with-topology variant. Real on-call
# engineers own the network they support; withholding the layout would
# be artificial. We include the actual recon-discovered topology
# (2 leaves × 4 spines × 8 hosts/leaf), with host 11.0.0.1 placed on
# leaf 0 — matching the substrate's actual node assignment.
TOPOLOGY_PREAMBLE = (
    "Fabric layout (what we know):\n"
    "  - 2-leaf, 4-spine RDMA fabric (full mesh leaf <-> spine).\n"
    "  - 8 hosts per leaf (16 hosts total).\n"
    "  - Host 11.0.0.1 is on leaf 0.\n"
    "  - Links: 800 Gbps host <-> leaf, 800 Gbps leaf <-> spine.\n"
    "  - Congestion control: PowerTCP (DCQCN-class) with ECN marking.\n"
    "  - PFC is configured but its trigger threshold is conservative.\n"
)

# Help-ticket for the 2026-05-11 capability-envelope sweep variant. The
# emphasis is the *bursty character* of the symptom (sub-second collapse,
# self-recovery), not a steady step-time anchor — the Stage 3 ticket's
# "step time up 1.5x" framing already proved tractable when the agent had
# topology in hand, and the sweep is interested in whether richer
# telemetry (counters tool) supports recognition when the symptom is
# described in the noisier voice an on-call would hear from the
# application team. No microburst/incast/PFC/ECMP vocabulary.
WITH_COUNTERS_USER_TICKET = (
    "Hey network team — we're getting reports of brief throughput "
    "collapses on training jobs targeting host 11.0.0.1. Iteration time "
    "spikes for a few hundred milliseconds at a stretch and then "
    "recovers on its own; application logs blame the network, our "
    "network team initially read it as a workload pattern. Started "
    "showing up this morning around 09:14 UTC. Can you take a look?"
)


def _build_symptom_only_prompt(_context: EvalContext) -> str:
    return USER_TICKET + "\n"


def _build_with_topology_prompt(_context: EvalContext) -> str:
    return TOPOLOGY_PREAMBLE + "\n" + USER_TICKET + "\n"


def _build_with_counters_prompt(_context: EvalContext) -> str:
    return WITH_COUNTERS_USER_TICKET + "\n"


def _score(context: EvalContext, completion: Completion) -> Score:
    """Delegate to the shared triage-quality rubric.

    Single thin wrapper so we can adjust thresholds per-scenario later
    without touching the rubric itself. For Stage 2 both variants use
    the same defaults — the difference between symptom-only and
    with-topology should manifest in *which* hypotheses the model
    considers and *how specifically* it names telemetry, not in the
    rubric thresholds.
    """
    return score_triage_quality(context, completion)


def microburst_symptom_only() -> EvalScenario:
    """Naked single-shot model, symptom only, no topology.

    Expected failure mode: model produces a triage plan but can't
    narrow because it has no context. Should still consider multiple
    hypotheses and name telemetry it would query.
    """
    return EvalScenario(
        name="microburst-symptom-only",
        description=(
            "Symptom-only ticket: 'step time on jobs targeting host "
            "11.0.0.1 up 1.5x.' No topology, no telemetry, no failure-"
            "class menu. Tests the floor of single-shot LLM triage."
        ),
        system_prompt=SYSTEM_PROMPT,
        target_scenario=TARGET_SCENARIO,
        baseline_scenario=None,
        build_user_prompt=_build_symptom_only_prompt,
        score=_score,
        expected_to_pass=False,
    )


def microburst_with_topology() -> EvalScenario:
    """Naked single-shot model, symptom + topology preamble.

    Demonstrates the marginal value of one piece of context. Same
    fault, same symptom; the agent now knows the fabric layout. We
    expect the model to narrow toward leaf-0 / receiver-side / incast
    hypotheses rather than spreading across the full hypothesis space.
    """
    return EvalScenario(
        name="microburst-with-topology",
        description=(
            "Symptom + topology preamble: same ticket as -symptom-only, "
            "with a 'what we know about the fabric' preamble. Tests the "
            "marginal value of one piece of context."
        ),
        system_prompt=SYSTEM_PROMPT,
        target_scenario=TARGET_SCENARIO,
        baseline_scenario=None,
        build_user_prompt=_build_with_topology_prompt,
        score=_score,
        expected_to_pass=False,
    )


def microburst_with_topology_tool() -> EvalScenario:
    """Stage 3 closing test: same bare ticket as symptom-only, but the
    agent has the ``get_topology`` tool.

    The user prompt is exactly ``USER_TICKET`` — no fabric layout, no
    pre-loaded context. The tool surface gives the agent the option to
    query topology on demand. The pedagogical claim is that this
    variant should score closer to ``microburst_with_topology`` (which
    received topology in the prompt) than to ``microburst_symptom_only``
    (which received nothing). If the model retrieves topology via the
    tool and reaches comparable triage quality, the harness has earned
    its weight; if it doesn't reach for the tool, that's a finding.

    ``expected_to_pass`` is True for this variant — distinct from the
    other two — because we're testing whether the harness *closes the
    gap*, not whether the floor is bad.
    """
    return EvalScenario(
        name="microburst-with-topology-tool",
        description=(
            "Symptom + tool: same bare ticket as -symptom-only, but the "
            "agent has the get_topology tool. Tests whether the harness "
            "adds capability the LLM doesn't have alone (vs. the "
            "topology being hardcoded in the prompt)."
        ),
        system_prompt=SYSTEM_PROMPT,
        target_scenario=TARGET_SCENARIO,
        baseline_scenario=None,
        build_user_prompt=_build_symptom_only_prompt,  # SAME ticket as symptom-only
        score=_score,
        expected_to_pass=True,
        uses_tools=True,
    )


def microburst_with_counters_tool() -> EvalScenario:
    """2026-05-11 capability-envelope sweep: microburst + topology +
    fabric counters tools, no skill.

    Stage 3's `microburst_with_topology_tool` already showed that the
    agent passes when given the topology tool alone. This variant pairs
    the same fault with the full Stage 5a tool surface (topology +
    counters) and a different help-ticket framing — the bursty character
    of the symptom rather than the steady step-time anchor — to make
    the sweep's `microburst-with-counters-tool` row comparable to the
    other three sweep rows (`hash-polarization`, `asymmetric-path`,
    `silent-drops`) which all use the same harness configuration.

    Pre-registered prediction (per
    ``project_capability_envelope_sweep_2026_05_11.md``): EASY — Stage 3
    already passed with topology only; adding counters should not regress
    diagnosis quality. If the bursty framing throws the agent off (e.g.,
    it chases application-side hypotheses without consulting the counter
    asymmetry), that's a finding about how prompt framing interacts with
    tool usage.
    """
    return EvalScenario(
        name="microburst-with-counters-tool",
        description=(
            "Symptom + tools (topology + fabric counters), no skill. "
            "Microburst substrate, bursty-framing help-ticket. Sweep row "
            "comparable to hash-polarization, asymmetric-path, silent-drops "
            "under the same harness configuration."
        ),
        system_prompt=SYSTEM_PROMPT,
        target_scenario=TARGET_SCENARIO,
        baseline_scenario=None,
        build_user_prompt=_build_with_counters_prompt,
        score=_score,
        expected_to_pass=False,
        uses_tools=True,
    )


__all__ = [
    "SYSTEM_PROMPT",
    "TARGET_SCENARIO",
    "TOPOLOGY_PREAMBLE",
    "USER_TICKET",
    "WITH_COUNTERS_USER_TICKET",
    "microburst_symptom_only",
    "microburst_with_topology",
    "microburst_with_topology_tool",
    "microburst_with_counters_tool",
]
