"""Deterministic scorer for the Calibrated Commitment skill's output structure.

Where the rubric LLM judge measures triage *quality* and the
correctness LLM judge measures diagnosis *correctness*, this scorer
measures something specific and fast: does the agent's response
show evidence of each of the five Calibrated Commitment axes
(verdict / confidence / falsification / symptom-vs-data /
localization)?

Deterministic on purpose:

- No LLM in the scoring path → reproducible across runs; cheap; no
  tokens spent;
- The signals are phrase-level patterns the skill explicitly asks
  the agent to use ("high confidence", "most likely", "would change
  my mind", etc.); the scorer searches for those patterns;
- A weak signal (one phrase) counts as evidence the axis is present;
  the scorer doesn't try to grade how *well* an axis is covered —
  that's the LLM judge's domain. This is a presence-check, not a
  quality-check.

Pairs with the skill in `harnessit.skills.calibrated_commitment`.
When the skill is loaded, every response should show the five
axes; this scorer measures how often that contract holds. When the
skill is NOT loaded, this scorer measures the *baseline rate* of
calibrated commitment in naked-Opus responses (the 2026-05-12 final
sweep already showed some baseline rate via the hash-polarization
trace's symptom-mismatch hedge).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


# Phrase signals per axis. Lower-case, matched against lower-cased
# response text. Each axis is "present" if ANY of its signals match —
# multiple phrasings exist for each concept and the scorer is permissive.
#
# Curation principle: prefer specific phrases the skill body uses or
# clearly induces (including section-header phrasings the agent
# produces in practice), not generic words that would fire on any
# response.
#
# Signal-pattern coverage was expanded 2026-05-12 (post-skill A/B)
# after observing that the agent commonly uses section headers like
# "**Confidence: high.**" or "**Localization caveat.** SPECIFIC, not
# class" — the prior signal set missed these because it focused on
# inline hedging phrases rather than the skill's section-header
# vocabulary. Per-axis comments mark which signals are inline (free-
# form prose) vs section-header (skill-induced structure).
_VERDICT_SIGNALS: tuple[str, ...] = (
    # Inline:
    "root cause",
    "diagnosis",
    "mechanism class",
    # Section-header (skill-induced):
    "verdict:",
    "verdict.",
    "verdict —",
    "**verdict**",
    # The skill prompts "name the mechanism class and localization in
    # the form you'd use in a help-ticket reply." Responses without
    # the skill still virtually always include "root cause" or
    # "diagnosis"; this axis is the easiest to satisfy and we expect
    # close to 100% baseline.
)

_CONFIDENCE_SIGNALS: tuple[str, ...] = (
    # The four discrete bands from the skill body:
    "high confidence",
    "most likely",
    "consistent with data",
    "consistent with the data",
    "evidence does not support",
    "evidence isn't there",
    "evidence is not there",
    # Section-header (skill-induced):
    "confidence:",
    "confidence level:",
    "confidence level.",
    "confidence level —",
    "confidence.",
    "**confidence**",
    "**confidence level**",
    # The agent often uses "Confidence: high" or "**Confidence
    # level.** Evidence does not support..." as section headers in
    # post-skill responses.
)

_FALSIFICATION_SIGNALS: tuple[str, ...] = (
    # Inline:
    "would change my mind",
    "would falsify",
    "would change the verdict",
    "would change the diagnosis",
    "would change the answer",
    "this would be wrong if",
    "this would not be",
    "would not be this if",
    "rule this out",
    "rules out",
    "rule out",
    "wrong if",
    "would revise the verdict",
    "would revise the diagnosis",
    "what would flip",
    "would flip me",
    "would flip this",
    "would flip the",
    # Section-header (skill-induced):
    "falsification condition",
    "falsification conditions",
    "**falsification**",
    # Popperian language: agent names what observation would flip the
    # conclusion. Skill says "if you can't name what would falsify
    # you, your verdict isn't a hypothesis." The agent picks up on
    # the literal "what would flip me" phrasing the skill body uses.
)

_SYMPTOM_DATA_MISMATCH_SIGNALS: tuple[str, ...] = (
    # Inline:
    "doesn't match",
    "does not match",
    "mismatch",
    "you described",
    "you reported",
    "the ticket says",
    "the help-ticket",
    "the help ticket",
    "the symptom you described",
    "the symptom doesn't appear",
    "the data doesn't show",
    "data does not show",
    "the evidence in this run does not",
    "doesn't describe the same event",
    "do not describe the same event",
    "trace doesn't match",
    "trace does not match",
    "your verbal characterization",
    # Section-header (skill-induced):
    "symptom-vs-data",
    "symptom vs data",
    "symptom-vs.-data",
    "symptom alignment",
    "**symptom",
    # When help-ticket symptom doesn't match observed trace, agent
    # says so. Already in the wild before the skill landed (hash-
    # polarization 2026-05-12 final trace `d52f08…`).
)

_LOCALIZATION_CAVEAT_SIGNALS: tuple[str, ...] = (
    # Inline alternatives / hedges:
    "could also be",
    "alternatively",
    "or it could be",
    "another possibility",
    "doesn't necessarily mean",
    "does not necessarily mean",
    "uniform corruption",  # silent-drops-specific but useful there
    "traffic concentration",
    "concentration on host",
    "rather than a specific",
    "rather than specific",
    "rather than localized",
    "could be uniform",
    # Specific/class vocabulary the skill body uses:
    "specific vs class",
    "specific vs. class",
    "specific, not class",
    "class, not specific",
    "class-level",
    "class level",
    "specific localization",
    "class localization",
    "specific entity",
    # Section-header (skill-induced):
    "localization caveat",
    "**localization**",
    # When agent commits to a specific entity (host X, port Y), this
    # signals it acknowledged a CLASS-level alternative explanation.
    # Agents often use "Localization caveat." as a section header in
    # post-skill responses without using the inline hedge phrases.
)


_FABRIC_HEALTH_SUMMARY_SIGNALS: tuple[str, ...] = (
    # Section header forms (skill v0.2 induces these directly):
    "fabric-health summary",
    "fabric health summary",
    "**fabric health**",
    "**fabric-health**",
    "fabric health:",
    "fabric-health:",
    # Inline summary forms:
    "what is clear",
    "what's clear",
    "what's worth noting",
    "what is worth noting",
    "worth noting but not diagnostic",
    "subsystems show no",
    "subsystems are clean",
    "from this trace we can",
    "from the trace we can",
    "in this trace we can rule out",
    # Conditional axis (v0.2): only fires when the agent reaches a
    # NO_DIAGNOSIS-class verdict and still gives the SRE a partial
    # fabric-state picture. v0.1 traces showed agents producing this
    # organically (e.g., "Zero PFC, zero ECN, zero drops" alongside
    # a refusal); v0.2 makes it mandatory under the refusal /
    # consistent-with-data confidence bands.
)


_AXES: dict[str, tuple[str, ...]] = {
    "verdict": _VERDICT_SIGNALS,
    "confidence_level": _CONFIDENCE_SIGNALS,
    "falsification_conditions": _FALSIFICATION_SIGNALS,
    "symptom_vs_data_alignment": _SYMPTOM_DATA_MISMATCH_SIGNALS,
    "localization_caveat": _LOCALIZATION_CAVEAT_SIGNALS,
    "fabric_health_summary": _FABRIC_HEALTH_SUMMARY_SIGNALS,
}


@dataclass(frozen=True)
class StructuredCommitmentScore:
    """Per-axis presence flags + a roll-up count.

    ``axes_present`` is a dict of axis-name → bool. ``axes_present_count``
    is the number of axes where at least one signal phrase matched.
    ``all_axes_present`` is convenience for "did all five appear?"
    """

    axes_present: dict[str, bool]
    matched_phrases: dict[str, tuple[str, ...]]

    @property
    def axes_present_count(self) -> int:
        return sum(1 for v in self.axes_present.values() if v)

    @property
    def all_axes_present(self) -> bool:
        return all(self.axes_present.values())


def score_structured_commitment(text: str) -> StructuredCommitmentScore:
    """Score a response for presence of the five Calibrated Commitment axes.

    Case-insensitive substring search per signal phrase. An axis is
    marked present if *any* of its signals matches.

    Parameters
    ----------
    text:
        The agent's final response text (Completion.text).

    Returns
    -------
    StructuredCommitmentScore
        Per-axis booleans + the matched phrases (for trace-review
        legibility — readers can see exactly which phrases triggered
        each axis).
    """
    lowered = text.lower()
    present: dict[str, bool] = {}
    matched: dict[str, tuple[str, ...]] = {}
    for axis, signals in _AXES.items():
        hits = tuple(s for s in signals if s in lowered)
        present[axis] = bool(hits)
        matched[axis] = hits
    return StructuredCommitmentScore(
        axes_present=present,
        matched_phrases=matched,
    )


def axis_names() -> Iterable[str]:
    """Return the canonical axis names in their canonical order. Useful
    for trace-review code that wants to render the scorer's output."""
    return tuple(_AXES.keys())


__all__ = [
    "StructuredCommitmentScore",
    "axis_names",
    "score_structured_commitment",
]
