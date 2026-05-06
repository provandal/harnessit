"""Microburst-localization eval — two scenarios sharing one substrate run.

Stage 2 v2 ships two scenarios under the same underlying microburst
fault. Both single-run (no paired baseline; real on-call doesn't get
pre-paired comparisons handed to it). Both naked (single-shot LLM call,
no tools, no retrieval, no memory). They differ only in the user-prompt
context:

* ``microburst_symptom_only`` — bare ticket. The agent knows nothing
  about the fabric beyond what an outside observer reports. The honest
  failure mode here is "I'd need topology info, telemetry, baseline
  comparison."
* ``microburst_with_topology`` — same ticket plus a "what we know about
  the fabric" preamble (leaf-spine layout, host assignment, link
  speeds). Demonstrates the marginal value of one piece of context.

Stage 3 will add a third variant where the topology comes from a tool
the agent can query, rather than being baked into the prompt — that's
where the harness starts adding capability the LLM doesn't have alone.

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


def _build_symptom_only_prompt(_context: EvalContext) -> str:
    return USER_TICKET + "\n"


def _build_with_topology_prompt(_context: EvalContext) -> str:
    return TOPOLOGY_PREAMBLE + "\n" + USER_TICKET + "\n"


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


__all__ = [
    "SYSTEM_PROMPT",
    "TARGET_SCENARIO",
    "TOPOLOGY_PREAMBLE",
    "USER_TICKET",
    "microburst_symptom_only",
    "microburst_with_topology",
]
