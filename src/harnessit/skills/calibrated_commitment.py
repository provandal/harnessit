"""Calibrated Commitment — Stage 5b's first skill.

When loaded onto an ``EvalScenario``, this skill injects a procedural
prompt fragment that asks the agent to make commitment confidence
explicit in its diagnosis. The skill targets a specific failure
pattern observed across the 2026-05-11 → 2026-05-12 sweep evolution:
even when the agent reaches CORRECT diagnoses, it commits at a
strength that's sharper than the evidence supports.

The trace that motivated this skill: silent-drops `25b1e7f9…`
(2026-05-12, post step-2b) reached CORRECT on the mechanism class
("link-layer silent corruption") but over-localized to host 16 as a
"sick link" — when the substrate actually applies uniform 0.001
corruption across all links and host 16 is just the heaviest
receiver. The localization is sharper than the data supports. Same
pattern but inverted: hash-polarization final trace
`d52f08d6aac6b07b8be52c118fcd8bc4` reached CORRECT AND hedged on the
symptom-vs-data mismatch ("either the bimodal histogram is from a
different scenario, or upstream of the network") — that's the
*differential commitment confidence* pattern this skill aims to
make routine.

The skill specifies five axes the agent should make legible in its
response: verdict, confidence level, falsification conditions,
symptom-vs-data alignment, and localization caveat. Order is up to
the agent (don't impose a rigid structure when the response flow
benefits from a different order).

Five-axis design choices:

1. **Verdict** — the agent already produces this; the skill just
   asks them to make it identifiable as the verdict (rather than
   trailing it in a long paragraph of mixed analysis).

2. **Confidence level** — discretized into four bands (high
   confidence / most likely / consistent with data / evidence does
   not support). Discrete bands make A/B comparisons easier than
   free-form "I'd say 80%."

3. **Falsification conditions** — names the single observation that
   would flip the verdict. This is the Popperian framing: if you
   can't name what would falsify you, you don't have a hypothesis.

4. **Symptom-vs-data alignment** — already in the wild on the
   hash-polarization final trace. Making it routine catches the
   class of error where the help-ticket symptom doesn't match the
   trace data and the agent papers over the gap.

5. **Localization caveat** — directly targets the silent-drops
   over-localization pattern. Forces the agent to distinguish
   SPECIFIC ("host 16 is sick") from CLASS ("uniform corruption
   with traffic concentration on host 16").

v0.2 changes (2026-05-12, post first-skill A/B):

6. **Fabric-health summary (conditional)** — addresses the
   observation that NO_DIAGNOSIS responses gave SREs nothing
   actionable. When the confidence band is the refusal or
   consistent-with-data form, the skill mandates a brief summary
   of what IS clear about fabric state, so the SRE has a partial
   picture alongside the refusal.

**Confidence-level narrowing**: v0.1 A/B showed the agent reaching
for "evidence does not support" when the user's symptom magnitude
didn't match the trace, even with visible fabric signal (hash-
polarization trace `aa7a1818…` dismissed a real 1.56x spine
imbalance as "fairly even, no hot spine"). v0.2 narrows the refusal
band to "fabric is genuinely quiescent" — concrete checklist (no
PFC, no ECN, no drops, no asymmetry, no PHY drops) — and routes the
symptom-mismatch case to "consistent with data but not yet
confirmed" instead.

The skill body is kept compact (~300 words at v0.2, up from ~250
at v0.1). Larger skill bodies crowd the agent's context for tool
data; v0.2's growth is justified by the operational utility of the
fabric-health summary axis observed in v0.1 traces where it
appeared organically.
"""

from __future__ import annotations

from dataclasses import dataclass


CALIBRATED_COMMITMENT_NAME = "calibrated-commitment"
CALIBRATED_COMMITMENT_VERSION = "0.2"

CALIBRATED_COMMITMENT_BODY = """\
## Skill: Calibrated Commitment (v0.2)

When formulating your diagnosis at the end of an investigation, make
commitment confidence explicit. Your response should make these six
axes identifiable, in whatever order suits the flow of your reasoning:

1. **Verdict.** Name the mechanism class and localization in the form
   you'd use in a help-ticket reply.

2. **Confidence level.** One of:
   - *high confidence* — evidence is overwhelming; multiple signals
     corroborate; no contradictions in the data.
   - *most likely* — evidence supports this hypothesis but at least
     one alternative is internally consistent.
   - *consistent with data but not yet confirmed* — visible signal in
     the data is consistent with a diagnosis (e.g., uneven per-port
     counters consistent with ECMP polarization; pause/resume pattern
     consistent with isolated incast). Use this band when (a) the
     user's symptom magnitude or shape doesn't exactly match the
     trace, or (b) multiple mechanism classes fit the same data.
     Don't dismiss visible signal — articulate that the diagnosis is
     supported by fabric data but not fully confirmed against the
     user's stated symptom.
   - *evidence does not support a fabric-side diagnosis* — use ONLY
     when the fabric is genuinely quiescent. Concretely: no PFC, no
     ECN marks, no drops, no queue buildup, no notable per-port
     asymmetry, no host PHY drops. This is the "fabric isn't doing
     anything wrong" case. Don't reach for this band just because
     the user's symptom magnitude differs from the trace — that's
     what the symptom-vs-data axis (4) is for, used alongside the
     "consistent with data" band above.

3. **Falsification conditions.** Name 1-2 specific observations that
   would change your verdict. E.g., "if host X's PHY drops were
   similar to other hosts, this would be sampling concentration not
   a sick link." If you can't name what would falsify you, your
   verdict isn't a hypothesis — it's a guess.

4. **Symptom-vs-data alignment.** If the user's reported symptom
   doesn't match what you see in the data, say so explicitly. Don't
   paper over the mismatch — "you described X but the trace shows Y;
   either the trace is from a different window, or the cause is
   upstream of what these tools can measure." Calling out the
   mismatch is a hedge, not a refusal — pair it with the
   "consistent with data" band when there IS visible signal.

5. **Localization caveat.** When committing to a specific entity
   (host, port, link), note whether the data supports SPECIFIC vs
   CLASS localization. E.g., "host 16 is the heaviest accumulator
   of PHY drops, but this could also be uniform corruption with
   traffic concentration on host 16."

6. **Fabric-health summary** (CONDITIONAL — include only when your
   confidence level is *evidence does not support* or *consistent
   with data but not yet confirmed*). Briefly note what IS clear
   about fabric state: which subsystems show no anomalies, which (if
   any) show worth-noting-but-not-diagnostic signals, and what the
   SRE can rule out from this trace even without a committed
   diagnosis. Example: "What's clear from this trace: PFC clean
   across all switches; ECN marks within normal incast bounds; no
   host PHY drops above noise. What's worth noting but not
   diagnostic: leaf-0's uplinks show ~1.6x packet imbalance, real
   but small-sample." A NO_DIAGNOSIS response that gives the SRE
   nothing actionable is operationally weaker than one that provides
   a partial fabric picture alongside the refusal.

Aim for honest commitment: commit hard when evidence supports it,
hedge specifically when symptom-vs-data ambiguity exists alongside
visible signal, and refuse explicitly only when the fabric itself
is quiescent.
"""


@dataclass(frozen=True)
class Skill:
    """One loaded skill: name, version, and the prompt-fragment body
    that gets injected into the agent's context.

    Frozen so multiple eval runs can share a Skill instance without
    one accidentally mutating another's state.
    """

    name: str
    version: str
    body: str


def load_calibrated_commitment() -> Skill:
    """Return a ``Skill`` instance for the Calibrated Commitment skill.

    The skill body is fixed at import time; per-SRE customization
    (verbosity / vocabulary / format preferences) is a future
    extension via parameters on this loader function.
    """
    return Skill(
        name=CALIBRATED_COMMITMENT_NAME,
        version=CALIBRATED_COMMITMENT_VERSION,
        body=CALIBRATED_COMMITMENT_BODY,
    )


__all__ = [
    "CALIBRATED_COMMITMENT_BODY",
    "CALIBRATED_COMMITMENT_NAME",
    "CALIBRATED_COMMITMENT_VERSION",
    "Skill",
    "load_calibrated_commitment",
]
