"""Silent-drops diagnostic eval — capability-envelope sweep variant.

Substrate factory: ``spike_burst_silent_drops()`` (Doppelgänger
``scenarios/builtin.py``), default ``rate=0.001`` (0.1% per-packet
silent drops on every link). Substrate runs the 256-host bundled
``spike-burst-256`` topology with the bundled burst flow pattern.
The diagnostic signature is the 2026-05-02 spike's eval-discipline
finding (Doppelgänger v0.2 §6.3): a subset of flows fail to complete
because their packets are dropped before completion, surviving flows
show elevated FCT tail and increased retransmissions. Aggregate FCT
statistics computed over completed flows alone can mislead — the
*absence* of the slowest flows from the completed-set can make the
injected run look faster than baseline.

**Substrate-bundled topology limitation**: this scenario uses the
substrate's bundled ``topology-256.txt`` rather than a custom
``Topology`` Python object. Two consequences for the agent's tool
surface:

1. ``get_topology`` returns the degraded ``shape=substrate-bundled``
   payload — no structured leaf/spine/host enumeration, only the
   topology-file path and the introspection-not-available notice.
2. ``get_fabric_counters`` runs the scenario but the per-port
   zero-fill is skipped (no ``scenario.custom_topology`` for the
   Adapter to enumerate against). The agent sees whatever per-port
   records the substrate emitted; ports with no activity won't appear.

The first is a sweep variable rather than a bug — an SRE looking at a
fabric they don't have a structured-topology export for is a realistic
situation. The second means the diagnostic surface for silent drops
leans more heavily on FCT-incomplete records than on counter
enumeration. Both effects are part of what the sweep is measuring;
neither is a blocker for running the closing test.

Help-ticket framing: some flows never finish — they don't error, they
just dribble. No firmware or topology change recently. No mention of
silent drops, link errors, or completion-status statistics.
"""

from __future__ import annotations

from harnessit.eval.scoring import Score, score_triage_quality
from harnessit.eval.types import EvalContext, EvalScenario
from harnessit.model import Completion

SYSTEM_PROMPT = (
    "You are a network-investigation assistant for an RDMA leaf-spine "
    "fabric. Help the user diagnose their issue."
)

TARGET_SCENARIO = "spike-burst-silent-drops"

USER_TICKET = (
    "Hey network team — we have flows on the AI cluster that just "
    "never finish. They don't error out cleanly, they don't time out "
    "fast, they just dribble — bytes keep moving for a while and then "
    "the flow sits there. Other flows on the same hosts are fine. "
    "Started a couple of weeks ago. No firmware update, no topology "
    "change we're aware of. Can you help track this down?"
)


def _build_user_prompt(_context: EvalContext) -> str:
    return USER_TICKET + "\n"


def _score(context: EvalContext, completion: Completion) -> Score:
    return score_triage_quality(context, completion)


def silent_drops_with_counters_tool() -> EvalScenario:
    """2026-05-11 capability-envelope sweep: silent-drops + tools, no skill.

    Pre-registered prediction (per
    ``project_capability_envelope_sweep_2026_05_11.md``): MEDIUM.
    Requires joining per-link error counters with FCT incomplete-flow
    records — multi-source correlation, which is where Voyager-style
    depth limits might surface. Two additional measurement axes
    unique to this scenario:

    * Will the agent notice the FCT-incomplete count divergence
      (substrate emits incomplete records explicitly per Doppelgänger
      v0.2 §4.2) and resist computing aggregates over completed flows
      alone? The 2026-05-02 spike's eval-discipline finding lives or
      dies on this question.
    * The degraded topology payload (bundled topology, no structured
      enumeration) and the missing per-port zero-fill (no
      ``custom_topology`` for the Adapter to enumerate against) are
      degraded-telemetry conditions the other three sweep rows don't
      face. Whether the agent acknowledges that gap or papers over it
      is itself a signal about epistemic discipline under degraded
      tools.
    """
    return EvalScenario(
        name="silent-drops-with-counters-tool",
        description=(
            "Symptom + tools (topology + fabric counters), no skill. "
            "spike-burst-silent-drops substrate (256-host bundled "
            "topology, 0.1% per-packet silent drops). Tests whether the "
            "agent joins FCT-incomplete records with per-link error "
            "counters and notices the completed-set aggregation trap."
        ),
        system_prompt=SYSTEM_PROMPT,
        target_scenario=TARGET_SCENARIO,
        baseline_scenario=None,
        build_user_prompt=_build_user_prompt,
        score=_score,
        expected_to_pass=False,
        uses_tools=True,
    )


__all__ = [
    "SYSTEM_PROMPT",
    "TARGET_SCENARIO",
    "USER_TICKET",
    "silent_drops_with_counters_tool",
]
