"""Asymmetric-path diagnostic eval — capability-envelope sweep variant.

Substrate factory: ``asymmetric_path()`` (Doppelgänger
``scenarios/builtin.py``). Default topology has 4 leaves × 4 spines × 4
hosts/leaf with spine 0 degraded (reduced bandwidth + increased delay
on its leaf↔spine links). Traffic is leaf-0 ↔ leaf-1 paired flows
ECMP-distributed across the 4 spines, so flows landing on spine 0
experience materially worse FCT than flows landing on healthy spines.

The diagnostic surface is **bimodal FCT distribution among
otherwise-identical flows**, with the slower mode correlating to the
ECMP hash landing on the degraded spine. The agent has two paths to
the root cause: read the topology payload's ``asymmetry`` field
directly (the ``slow_spine_indices`` list is exposed), or infer it
from per-spine-link counter imbalance via the counters tool. Whether
the agent uses the topology shortcut or earns it through counter
correlation is part of what the sweep is measuring.

Help-ticket framing: tail latency observed on certain flows, no host
or rack pattern visible. No mention of spine asymmetry, ECMP, or
hashing — the agent has to reach for the explanation.
"""

from __future__ import annotations

from harnessit.eval.scoring import Score, score_triage_quality
from harnessit.eval.types import EvalContext, EvalScenario
from harnessit.model import Completion

SYSTEM_PROMPT = (
    "You are a network-investigation assistant for an RDMA leaf-spine "
    "fabric. Help the user diagnose their issue."
)

TARGET_SCENARIO = "asymmetric-path"

USER_TICKET = (
    "Hey network team — tail latency on RDMA jobs is up on certain "
    "flows. The pattern looks consistent run-to-run but I can't pin "
    "it to a host, a rack, or a specific link — some flows are fine "
    "and some are 2-3x slower for no obvious reason. We haven't "
    "changed the topology or rebalanced traffic. Can you help figure "
    "out what's going on?"
)


def _build_user_prompt(_context: EvalContext) -> str:
    return USER_TICKET + "\n"


def _score(context: EvalContext, completion: Completion) -> Score:
    return score_triage_quality(context, completion)


def asymmetric_path_with_counters_tool() -> EvalScenario:
    """2026-05-11 capability-envelope sweep: asymmetric-path + tools, no skill.

    Pre-registered prediction (per
    ``project_capability_envelope_sweep_2026_05_11.md``): MEDIUM. The
    topology payload exposes ``asymmetry.slow_spine_indices`` directly,
    which gives the agent an explicit signal it could read instead of
    deriving the answer from FCT-vs-spine-hash correlation. The
    interesting measurement: does the agent verify the topology field
    against the per-link counters (operationally responsible — confirm
    the configured degradation actually manifests) or treat the
    topology field as the answer (operationally premature)?
    """
    return EvalScenario(
        name="asymmetric-path-with-counters-tool",
        description=(
            "Symptom + tools (topology + fabric counters), no skill. "
            "asymmetric_path substrate (one degraded spine, leaf-0 to "
            "leaf-1 paired flows). Tests whether the agent reads the "
            "topology asymmetry field directly or correlates via "
            "per-spine-link counters."
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
    "asymmetric_path_with_counters_tool",
]
