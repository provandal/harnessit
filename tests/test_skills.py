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
    assert CALIBRATED_COMMITMENT_VERSION == "0.1"


def test_calibrated_commitment_body_mentions_five_axes():
    body = CALIBRATED_COMMITMENT_BODY.lower()
    # Each of the five axes named in the design must appear somewhere
    # in the prompt body — that's the contract the skill makes with
    # the agent. If a future refactor drops an axis from the body
    # without updating the design, this test catches it.
    for axis_term in (
        "verdict",
        "confidence",
        "falsification",
        "symptom",
        "localization",
    ):
        assert axis_term in body, f"axis {axis_term!r} missing from body"


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
