"""Tests for harnessit.skills — hermetic.

Skills are static prompt fragments, so most tests are content checks
and registry lookups. Runner integration (does the skill body get
injected into system_prompt?) is covered by a fixture-based test
that builds a minimal scenario and watches the model client receive
the merged prompt.
"""

from __future__ import annotations

import pytest

from harnessit.skills import (
    CALIBRATED_COMMITMENT_BODY,
    CALIBRATED_COMMITMENT_NAME,
    CALIBRATED_COMMITMENT_VERSION,
    Skill,
    load_calibrated_commitment,
    load_skill_by_name,
)


# ------------------------------------------------------------ skill content

def test_calibrated_commitment_name_and_version_constants():
    assert CALIBRATED_COMMITMENT_NAME == "calibrated-commitment"
    assert CALIBRATED_COMMITMENT_VERSION == "0.3"


def test_calibrated_commitment_body_mentions_seven_axes():
    body = CALIBRATED_COMMITMENT_BODY.lower()
    # Each of the seven axes (v0.3 added recommended-next-step) must
    # appear somewhere in the prompt body — that's the contract the
    # skill makes with the agent. If a future refactor drops an axis
    # from the body without updating the design, this test catches it.
    for axis_term in (
        "verdict",
        "confidence",
        "falsification",
        "symptom",
        "localization",
        "fabric-health",
        "recommended next step",
    ):
        assert axis_term in body, f"axis {axis_term!r} missing from body"


def test_calibrated_commitment_narrows_refusal_band_to_quiescent():
    """The 'evidence does not support' band must only fire when the
    fabric is genuinely quiescent. The skill body must explicitly name
    the checklist concept (no PFC, no ECN, no drops, no asymmetry,
    no PHY drops) to discourage the v0.1-era overshoot where the agent
    dismissed visible signal because the user's symptom didn't match
    magnitude.
    """
    body = CALIBRATED_COMMITMENT_BODY.lower()
    assert "genuinely quiescent" in body
    body_squished = " ".join(body.split())
    for signal in ("no pfc", "no ecn", "no drops", "asymmetry"):
        assert signal in body_squished, (
            f"refusal-band checklist concept missing: {signal!r}"
        )


def test_calibrated_commitment_fabric_health_is_conditional():
    """The fabric-health summary axis is conditional — only fires
    when the confidence band is the refusal or consistent-with-data
    form. The skill body must signal this, otherwise the agent will
    add health summaries to high-confidence verdicts where they're
    not load-bearing and would crowd the analysis."""
    body = CALIBRATED_COMMITMENT_BODY.lower()
    assert "conditional" in body
    assert "evidence does not support" in body
    assert "consistent with data" in body


def test_calibrated_commitment_v03_recommended_step_axis():
    """v0.3 added axis 7: the first recommended action must distinguish
    live alternatives, not remediate or redirect prematurely. The skill
    body must name verification-before-remediation as the axis 7
    contract."""
    body = CALIBRATED_COMMITMENT_BODY.lower()
    # Axis 7 named and motivated
    assert "recommended next step" in body
    # The skill must contrast verification with remediation/redirect
    assert "remediation" in body
    # Substrate-agnostic phrasing — should mention the two failure
    # modes the variance pass identified
    assert "redirect" in body


def test_calibrated_commitment_v03_epistemic_guardrails_present():
    """v0.3 added the Epistemic guardrails section with mandate A
    (hypothesis preservation) and mandate B (scope exclusions
    narrowly). Both must appear in the body."""
    body = CALIBRATED_COMMITMENT_BODY.lower()
    body_squished = " ".join(body.split())  # collapse line-break hyphenation
    assert "epistemic guardrails" in body
    # Mandate A: hypothesis preservation
    assert "hypothesis preservation" in body
    assert "absence-of-confirmation" in body_squished
    # Mandate B: scope narrowly
    assert "scope exclusions narrowly" in body
    # The temporal-vs-mechanistic distinction is load-bearing
    assert "temporally" in body
    assert "mechanistically" in body


def test_calibrated_commitment_v03_bars_dismissal_moves():
    """The five barred dismissal moves catalogued from WRONG traces
    must each surface in the skill body as concepts the agent should
    not perform. We check for concept-level signals rather than
    verbatim phrases (the body uses prose, not a bulleted enum)."""
    body = CALIBRATED_COMMITMENT_BODY.lower()
    # Counterfactual claims without checking
    assert "counterfactual" in body or "without checking" in body
    # New-asymmetry construction to preserve SPECIFIC
    assert "new distinguishing feature" in body
    # Localization expansion
    assert "enlarging" in body or "encompass visible signal" in body
    # Substrate structural features misread as fault signals
    assert "idle" in body or "structural features" in body
    # Within-trace null as evidence-against
    assert "null result" in body or "within-trace" in body


def test_calibrated_commitment_v03_normalized_rate_in_axis_5():
    """v0.3 sharpens axis 5 (localization caveat) to require normalized-
    rate comparison, not raw count comparison. SPECIFIC must depend on
    per-entity normalized rate being materially distinct from peers."""
    body = CALIBRATED_COMMITMENT_BODY.lower()
    assert "normalized" in body
    # The body should name at least one example denominator to
    # illustrate substrate-agnostic instantiation
    body_squished = " ".join(body.split())
    assert "drops per received packet" in body_squished or "per received packet" in body_squished


def test_calibrated_commitment_body_has_four_confidence_bands():
    """The skill enforces *discrete* confidence bands rather than
    free-form percentages. A/B comparisons depend on which band the
    agent picked; this assertion guards the contract."""
    body = CALIBRATED_COMMITMENT_BODY.lower()
    for band in (
        "high confidence",
        "most likely",
        "consistent with data but not yet confirmed",
        "evidence does not support",
    ):
        assert band in body, f"confidence band {band!r} missing from body"


def test_calibrated_commitment_body_does_not_dictate_order():
    """The skill design says: order is up to the agent. Don't impose a
    rigid structure. This test guards against accidentally hardcoding
    "first verdict, then confidence, then..." which would crowd out
    natural reasoning flow."""
    body = CALIBRATED_COMMITMENT_BODY.lower()
    # If we wanted rigid ordering we'd use words like "must be in
    # this order" or "in sequence". Absence is the assertion.
    assert "in this order" not in body
    assert "in sequence" not in body
    # Affirmative: the body explicitly says axes can be in any order
    assert "whatever order" in body or "any order" in body


# ------------------------------------------------------------ load API

def test_load_calibrated_commitment_returns_skill_dataclass():
    skill = load_calibrated_commitment()
    assert isinstance(skill, Skill)
    assert skill.name == CALIBRATED_COMMITMENT_NAME
    assert skill.version == CALIBRATED_COMMITMENT_VERSION
    assert skill.body == CALIBRATED_COMMITMENT_BODY


def test_load_calibrated_commitment_is_frozen():
    """Skill is a frozen dataclass so that multiple eval runs can share
    a Skill instance without mutation."""
    skill = load_calibrated_commitment()
    with pytest.raises(Exception):  # dataclass FrozenInstanceError
        skill.body = "tampered"  # type: ignore[misc]


def test_load_skill_by_name_resolves_calibrated_commitment():
    skill = load_skill_by_name("calibrated-commitment")
    assert skill.name == "calibrated-commitment"


def test_load_skill_by_name_raises_value_error_for_unknown_name():
    with pytest.raises(ValueError, match="Unknown skill"):
        load_skill_by_name("definitely-not-a-real-skill")
