"""Hash-polarization diagnostic eval — capability-envelope sweep variant.

Substrate factory: ``hash_polarization()`` (Doppelgänger
``scenarios/builtin.py``). Default topology has 4 leaves × 4 spines × 4
hosts/leaf — a uniform, symmetric leaf-spine. The fault is engineered
into the *flow population*: many leaf-0 ↔ leaf-1 flows share a small
set of ``dst_port`` values (default 2 distinct ports), which collides
under the substrate's deterministic ECMP hash and concentrates traffic
onto a subset of leaf↔spine links.

The diagnostic surface is **per-link counter asymmetry across
leaf↔spine links** despite an identical full-mesh topology and identical
nominal link capacity. The topology payload's ``asymmetry.present`` field
will be ``False`` — there is no topology-side asymmetry — so the agent
cannot shortcut the analysis the way it might for ``asymmetric_path``.
The mechanism class to name is ECMP polarization driven by flow-tuple
clustering, which requires multi-step reasoning: read counter
imbalance → recognize it's not a topology fault → hypothesize that
flow-tuple distribution is biasing the hash.

Help-ticket framing: bimodal completion times on training jobs, ~30%
of flows take ~2x longer, no hardware or layout change recently. No
mention of ECMP, hashing, polarization, or dst-port distribution.
"""

from __future__ import annotations

from harnessit.eval.scoring import Score, score_triage_quality
from harnessit.eval.types import EvalContext, EvalScenario
from harnessit.model import Completion

SYSTEM_PROMPT = (
    "You are a network-investigation assistant for an RDMA leaf-spine "
    "fabric. Help the user diagnose their issue."
)

TARGET_SCENARIO = "hash-polarization"

USER_TICKET = (
    "Hey network team — some training jobs are noticeably slower than "
    "others even though they look identical workload-wise. Looking at "
    "iteration time histograms it's bimodal: most flows behave fine, "
    "but roughly 30% are ~2x slower. Same source and destination racks, "
    "same job profile. Nothing changed on the network side that I know "
    "of. Can you help figure out what's biasing some flows?"
)


def _build_user_prompt(_context: EvalContext) -> str:
    return USER_TICKET + "\n"


def _score(context: EvalContext, completion: Completion) -> Score:
    return score_triage_quality(context, completion)


def hash_polarization_with_counters_tool() -> EvalScenario:
    """2026-05-11 capability-envelope sweep: hash-polarization + tools, no skill.

    Pre-registered prediction (per
    ``project_capability_envelope_sweep_2026_05_11.md``): HARDER than
    ECN-misconfig. Bimodal FCT recognition requires statistical
    reasoning over the distribution; reaching "ECMP polarization" as
    the mechanism class requires recognizing that uniform topology +
    asymmetric per-link counters means the fault sits in the
    flow-tuple distribution rather than in the fabric. The agent may
    pass the binary "is something wrong" question but miss naming the
    mechanism on first try. Multi-step reasoning is the Voyager-paper
    depth-limit pattern Erik flagged on the pivot — this is the
    scenario most likely to surface that pattern if it surfaces at all.
    """
    return EvalScenario(
        name="hash-polarization-with-counters-tool",
        description=(
            "Symptom + tools (topology + fabric counters), no skill. "
            "hash_polarization substrate (uniform topology, clustered "
            "dst_ports). Tests whether the agent recognizes per-link "
            "counter asymmetry on a symmetric fabric as flow-population "
            "bias rather than a fabric fault."
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
    "hash_polarization_with_counters_tool",
]
