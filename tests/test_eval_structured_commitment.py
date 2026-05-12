"""Tests for harnessit.eval.structured_commitment — hermetic.

The scorer is a deterministic substring matcher over an agent's
final response. Tests build crafted text fixtures exercising each
axis individually and in combination.
"""

from __future__ import annotations

from harnessit.eval.structured_commitment import (
    StructuredCommitmentScore,
    axis_names,
    score_structured_commitment,
)


AXES = (
    "verdict",
    "confidence_level",
    "falsification_conditions",
    "symptom_vs_data_alignment",
    "localization_caveat",
    "fabric_health_summary",
)


def test_axis_names_in_canonical_order():
    assert tuple(axis_names()) == AXES


def test_empty_response_has_zero_axes_present():
    score = score_structured_commitment("")
    assert score.axes_present_count == 0
    assert score.all_axes_present is False
    for axis in AXES:
        assert score.axes_present[axis] is False
        assert score.matched_phrases[axis] == ()


def test_verdict_axis_fires_on_diagnosis_keyword():
    score = score_structured_commitment("The diagnosis is ECMP imbalance.")
    assert score.axes_present["verdict"] is True
    assert "diagnosis" in score.matched_phrases["verdict"]


def test_confidence_axis_fires_on_calibrated_band():
    text = "I have high confidence in this diagnosis based on the data."
    score = score_structured_commitment(text)
    assert score.axes_present["confidence_level"] is True
    assert "high confidence" in score.matched_phrases["confidence_level"]


def test_falsification_axis_fires_on_popperian_phrasing():
    text = (
        "Root cause: spine 0 degraded. This would be wrong if the slow "
        "flows didn't share spine 0 as their ECMP target."
    )
    score = score_structured_commitment(text)
    assert score.axes_present["falsification_conditions"] is True


def test_symptom_data_alignment_axis_fires_on_mismatch_flag():
    text = (
        "You described a 30% slow tail, but the data doesn't show "
        "bimodal FCT in this trace — every flow is uniformly slow."
    )
    score = score_structured_commitment(text)
    assert score.axes_present["symptom_vs_data_alignment"] is True


def test_localization_caveat_axis_fires_on_specific_vs_class_phrasing():
    text = (
        "Host 16 has the highest PHY drop count, but this could also "
        "be uniform corruption with traffic concentration on that host."
    )
    score = score_structured_commitment(text)
    assert score.axes_present["localization_caveat"] is True


def test_all_six_axes_can_co_occur_in_one_response():
    """A response that touches each axis once should mark all six
    present. Models the ideal Calibrated Commitment v0.2 output —
    high-confidence cases skip the conditional fabric-health summary,
    but for an A/B fixture we include all six to exercise the scorer."""
    text = """
    Diagnosis: link-layer silent corruption on host 16's incoming link.
    Most likely — the host_counters show 153 drops on host 16
    against a 7-23 baseline across the rest of the fabric, consistent
    with data but not yet confirmed by per-host drops-per-million.
    This would be wrong if host 16's neighbors showed similar
    elevated drop counts, in which case the corruption is uniform
    rather than localized.
    You described "flows that dribble and never finish," and the data
    matches: 14 incomplete flows out of 266.
    Host 16 is the heaviest accumulator, but this could also be uniform
    corruption with traffic concentration on host 16 — without per-link
    breakdown we can't rule out class-level over specific-link.
    What's clear from this trace even setting aside the host-16 question:
    PFC clean across all switches; ECN marks within normal incast bounds.
    """
    score = score_structured_commitment(text)
    assert score.axes_present_count == 6
    assert score.all_axes_present is True


def test_fabric_health_summary_axis_fires_on_health_summary_phrasing():
    """The v0.2 conditional axis fires when the response includes a
    fabric-health summary alongside a refusal or partial-evidence
    verdict."""
    text = (
        "Evidence does not support a fabric-side diagnosis. "
        "What's clear from this trace: PFC counters are zero, "
        "ECN marks are zero, no drops anywhere. What's worth noting "
        "but not diagnostic: leaf-0's uplinks show small per-port "
        "variance, real but within sampling noise for this flow count."
    )
    score = score_structured_commitment(text)
    assert score.axes_present["fabric_health_summary"] is True


def test_axes_independent_a_response_can_miss_some():
    """A naked confident diagnosis without hedging or falsification
    should only mark the verdict axis, not the others."""
    text = "I've found it. The root cause is a degraded spine. Done."
    score = score_structured_commitment(text)
    assert score.axes_present["verdict"] is True
    assert score.axes_present["falsification_conditions"] is False
    assert score.axes_present["localization_caveat"] is False


def test_case_insensitive_matching():
    score = score_structured_commitment(
        "ROOT CAUSE: foo. HIGH CONFIDENCE this is correct."
    )
    assert score.axes_present["verdict"] is True
    assert score.axes_present["confidence_level"] is True


def test_dataclass_is_frozen():
    """StructuredCommitmentScore is frozen so callers can't mutate
    a score after it's returned."""
    import pytest
    score = score_structured_commitment("Diagnosis: x.")
    with pytest.raises(Exception):
        score.axes_present_count = 999  # type: ignore[misc]
