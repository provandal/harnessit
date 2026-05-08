"""ECN-misconfiguration localization eval — gap-measurement variant.

The Stage 5a closing scenario. Substrate: ``pfc_storm`` with default
``ecn_misconfigured=True`` (KMIN bumped above buffer capacity, QCN
enabled but DCQCN running blind because no CE marks fire). The
SRE-recognizable signature in fabric counters is **PFC pause_sent
elevated alongside ECN marks_sent near zero** — the asymmetry is the
diagnostic.

Single variant ships at Stage 5a: ``with_topology_and_counters_tool``
gives the agent both ``get_topology`` and ``get_fabric_counters`` but
no skill. Predicted behavior: agent fetches counters, sees PFC
elevated, concludes "PFC storm" without checking ECN-CN. **That gap
is what Stage 5b's first skill closes.** If the agent reaches the
right diagnosis here, the skill is over-engineered; if it doesn't,
Stage 5b has something concrete to demonstrate.

Help-ticket framing follows the Stage 2 reshape: sysadmin-reported
symptoms only. No mention of PFC, ECN, marking, storm, or the new
QoS rollout's specific knob — the agent has to infer "config rollout
last night → fabric is misbehaving" from the temporal correlation
and reason about the counter signature on its own.
"""

from __future__ import annotations

from harnessit.eval.scoring import Score, score_triage_quality
from harnessit.eval.types import EvalContext, EvalScenario
from harnessit.model import Completion

SYSTEM_PROMPT = (
    "You are a network-investigation assistant for an RDMA leaf-spine "
    "fabric. Help the user diagnose their issue."
)

TARGET_SCENARIO = "pfc-storm"

# Sysadmin help-ticket. The "QoS rollout last night" is the temporal
# correlation a real on-call engineer would see in their change log;
# it's a substantial hint without being the answer. No PFC/ECN/storm
# vocabulary — those are for the agent to reach for when it inspects
# the fabric.
USER_TICKET = (
    "Hey network team — RDMA training jobs are seeing throughput "
    "collapse and a bunch of incomplete iterations on the AI cluster. "
    "Started early this morning, right after the network team rolled "
    "out the new buffer/QoS settings on the leaf switches overnight. "
    "Bottom-pod racks are hit hardest. Can you help figure out what "
    "broke?"
)


def _build_user_prompt(_context: EvalContext) -> str:
    return USER_TICKET + "\n"


def _score(context: EvalContext, completion: Completion) -> Score:
    return score_triage_quality(context, completion)


def pfc_storm_with_counters_tool() -> EvalScenario:
    """Stage 5a closing test: tools but no skill, ECN-misconfig substrate.

    The agent has ``get_topology`` and ``get_fabric_counters``. The
    underlying fault is ``pfc_storm(ecn_misconfigured=True)``. Counter
    payload will show PFC pause_sent > 0 alongside ECN marks_sent == 0.
    Whether the agent reads the asymmetry as "ECN is failing to
    throttle, look at the marking config" rather than "PFC storm,
    senders are overwhelming the fabric" is the load-bearing question.

    ``expected_to_pass`` left False — Stage 5a is a *measurement*
    scenario, not a pass-or-ship gate. The result calibrates Stage 5b's
    skill demonstration.
    """
    return EvalScenario(
        name="pfc-storm-with-counters-tool",
        description=(
            "Symptom + tools (topology + fabric counters), no skill. "
            "ECN-misconfigured pfc_storm substrate. Tests whether tools "
            "alone close the diagnostic gap, or whether the skill at "
            "Stage 5b carries the weight."
        ),
        system_prompt=SYSTEM_PROMPT,
        target_scenario=TARGET_SCENARIO,
        baseline_scenario=None,
        build_user_prompt=_build_user_prompt,
        score=_score,
        expected_to_pass=False,
        uses_tools=True,
    )


def pfc_storm_realistic_with_counters_tool() -> EvalScenario:
    """Stage 5a-realistic closing test: same fault, production-shaped fabric.

    Identical to :func:`pfc_storm_with_counters_tool` except the
    underlying scenario is ``pfc-storm-realistic`` — full per-port
    counter set (rx/tx bytes+packets, drops, qlen peak), every switch
    port enumerated and zero-filled, plus layered cross-leaf background
    traffic so the fabric baseline shows ECN marks distributed across
    many ports under healthy config.

    The Stage 5a closing test (trace
    ``668a11072f2a9d51814ce55841fca6ef``) found that naked Opus 4.7
    nailed the diagnosis from a 2-port toy payload. This variant asks
    whether the same model still nails it when the fabric looks
    production-shaped: hundreds of ports active, ECN firing on
    background flows, asymmetry visible only as a *relative* anomaly
    between storm ports and baseline. The result calibrates Stage 5b's
    skill thesis: epistemic discipline (if the model still nails it) or
    RoCE-specific recognition under realistic noise (if it doesn't).
    """
    return EvalScenario(
        name="pfc-storm-realistic-with-counters-tool",
        description=(
            "Symptom + tools, no skill. Production-shaped pfc-storm: "
            "full counter set + topology-aware port enumeration + layered "
            "background traffic. Asymmetry is relative, not absolute."
        ),
        system_prompt=SYSTEM_PROMPT,
        target_scenario="pfc-storm-realistic",
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
    "pfc_storm_with_counters_tool",
    "pfc_storm_realistic_with_counters_tool",
]
