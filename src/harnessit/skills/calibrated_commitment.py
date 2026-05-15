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

v0.3 changes (2026-05-13, post k=3 variance pass + D2-field-presence
verify):

The variance pass closed at silent-drops 1/3 CORRECT under v0.2 and
the D2 field-presence verify closed at 0/3 CORRECT — adding the
`drops_per_million` field to the tool surface did not lift correctness
because the field gave the agent a new lever for rationalization
rather than fixing the reasoning. Cross-trace analysis (10 traces:
3 CORRECT, 5 WRONG, 2 edge cases) identified two binding epistemic
mandates that separate CORRECT from WRONG independently of the
substrate.

7. **Recommended next step (verification before remediation)** — the
   first recommended action must be a data check that distinguishes
   the mechanism classes currently held alive in the verdict.
   Remediation belongs at step 2+ under any verdict where alternative
   classes remain live. The WRONG traces consistently fail this by
   making step 1 either a remediation chain or a redirect to a
   different subsystem.

**Epistemic guardrails (new section)**. Two moves produce
operationally wrong stances even when the response shape looks
complete:

  - *Hypothesis preservation under insufficient data* (Guardrail A):
    absence-of-confirmation is not presence-of-evidence-against. Five
    barred dismissal moves catalogued from WRONG traces — assume-away,
    new-asymmetry construction, localization expansion, substrate-
    structural-feature-as-fault-signal, within-trace-null-as-evidence-
    against.
  - *Scope exclusions narrowly* (Guardrail B): under apparent fabric
    quiescence, phrase the exclusion *temporally* (this trace window)
    rather than *mechanistically* (the fabric is not the cause). The
    microburst k1 CORRECT trace and hash-pol k3 WRONG trace used the
    same "evidence does not support" confidence band; the difference
    was temporal vs. mechanistic exclusion and what step 1 did with
    that scoping.

**Axis 5 normalization update**. The localization caveat is sharpened
to require *normalized rate* comparison, not raw count comparison —
SPECIFIC requires the per-entity normalized rate (drops per received
packet, load per flow-bucket, pauses per priority, etc.) to be
materially distinct from peers. This bars the silent-drops failure
mode where the agent saw raw-count outliers and committed SPECIFIC
without normalization.

**Substrate-agnostic phrasing**. v0.3 deliberately strips silent-drops-
specific example phrasings from the skill body — denominators and
specific check phrasings vary per failure class; the agent instantiates
per scenario. The empirical evidence behind the mandates is in the
docstring rather than the body to keep the body transferable to
non-silent-drops scenarios (hash-polarization, microburst, asymmetric-
path, and future scenarios on real-hardware substrates like AIR).

The skill body grew to ~485 words at v0.3 (from ~310 at v0.2) — the
new axis and guardrails are load-bearing per the cross-trace analysis;
growth is justified.
"""

from __future__ import annotations

from dataclasses import dataclass


CALIBRATED_COMMITMENT_NAME = "calibrated-commitment"
CALIBRATED_COMMITMENT_VERSION = "0.3"

CALIBRATED_COMMITMENT_BODY = """\
## Skill: Calibrated Commitment (v0.3)

When formulating your diagnosis at the end of an investigation, make
commitment confidence explicit. Your response should make these seven
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
   would change your verdict. If you can't name what would falsify
   you, your verdict isn't a hypothesis — it's a guess.

4. **Symptom-vs-data alignment.** If the user's reported symptom
   doesn't match what you see in the data, say so explicitly. Don't
   paper over the mismatch — "you described X but the trace shows Y;
   either the trace is from a different window, or the cause is
   upstream of what these tools can measure." Calling out the
   mismatch is a hedge, not a refusal — pair it with the
   "consistent with data" band when there IS visible signal.

5. **Localization caveat.** When committing to a specific entity
   (host, port, link, switch), note whether the data supports
   SPECIFIC vs CLASS localization. SPECIFIC requires that the
   per-entity *normalized* rate (not raw counts) is materially
   distinct from peers on the denominator appropriate for this
   failure class — drops per received packet for PHY corruption,
   load per flow-bucket for ECMP hashing, pauses per priority for
   QoS misconfig, etc. If the normalized rate is comparable across
   peers, the verdict is CLASS-level with SPECIFIC named as a
   downgraded possibility, not the other way around.

6. **Fabric-health summary** (CONDITIONAL — include only when your
   confidence level is *evidence does not support* or *consistent
   with data but not yet confirmed*). Briefly note what IS clear
   about fabric state: which subsystems show no anomalies, which (if
   any) show worth-noting-but-not-diagnostic signals, and what the
   SRE can rule out from this trace even without a committed
   diagnosis. A NO_DIAGNOSIS response that gives the SRE nothing
   actionable is operationally weaker than one that provides a
   partial fabric picture alongside the refusal.

7. **Recommended next step — type must match epistemic state.** The
   first recommended action must be a data check whose outcome would
   distinguish the mechanism classes currently held alive in your
   verdict. Remediation (swap optic, replace cable, change config)
   belongs at step 2+ under any verdict where alternative classes
   remain live. Redirect to a different subsystem ("check the host
   side", "look at the application layer") belongs at step 2+ unless
   you have *quantitatively eliminated* the current class — not
   merely failed to confirm it within this trace window.

## Epistemic guardrails

Two moves produce operationally wrong stances even when the response
shape above looks complete. Bar them.

**A. Hypothesis preservation under insufficient data.** If visible
signal in the trace is *consistent with* a mechanism class but the
trace cannot *confirm* it, that class stays alive in your verdict
(as CLASS-level, named-as-alternative, or both). Absence-of-confirmation
is not presence-of-evidence-against. Specifically barred:

- Counterfactual claims about the substrate used without checking
  ("the counters don't show X, so X isn't happening")
- Constructing a new distinguishing feature to preserve a SPECIFIC
  localization when the normalized rate is comparable to peers
- Enlarging the localized hypothesis to encompass visible signal
  while still excluding the broader class
- Misreading substrate structural features (which entities are
  silent, which links saw traffic) as fault asymmetry signals —
  quiet entities may simply be idle, not healthy
- Using a within-trace null result as license to exclude the class
  ("the imbalance doesn't correlate with FCT, so it isn't the
  cause") when the trace window or volume is too small to test

If the trace cannot distinguish a candidate class from your
preferred verdict, the candidate stays in the response.

**B. Scope exclusions narrowly.** When the fabric appears quiescent,
phrase the exclusion *temporally* (the fabric is healthy in this
trace window), not *mechanistically* (the fabric is not the cause of
your symptom). Under temporal exclusion, step 1 is the right-window
capture or correlation that would actually test fabric involvement
during the incident — not a redirect to a different subsystem.

Aim for honest commitment: commit hard when evidence is overwhelming
and alternatives are quantitatively eliminated; hedge specifically
when visible signal is consistent with multiple classes; refuse
explicitly only when the fabric is genuinely quiescent in the window
of interest and you have asked for the right window if needed.
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
