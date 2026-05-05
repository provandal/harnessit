"""Tests for eval scoring rubrics.

Verifies that the silent-drops scorer correctly identifies which §3.8
commitments the model output references, and that the rubrics are
gated on whether the comparison data actually contains those signals
(no point demanding "incomplete-flow acknowledgment" if there are no
incomplete flows).
"""

from __future__ import annotations

from harnessit.eval.scoring import score_silent_drops_localization
from harnessit.model import Completion


def _completion(text: str) -> Completion:
    return Completion(
        text=text,
        model="claude-opus-4-7",
        input_tokens=10,
        output_tokens=20,
        stop_reason="end_turn",
    )


def _comparison(
    *,
    flow_count_delta: int = -5,
    has_count_divergence: bool | None = None,
    fct_p50: int | None = 12_000,
    fct_p99: int | None = 50_000,
    fct_p999: int | None = 100_000,
    incomplete_baseline: int = 0,
    incomplete_injected: int = 0,
) -> dict:
    if has_count_divergence is None:
        has_count_divergence = flow_count_delta != 0
    return {
        "flow_count_delta": flow_count_delta,
        "has_count_divergence": has_count_divergence,
        "fct_p50_delta_ns": fct_p50,
        "fct_p99_delta_ns": fct_p99,
        "fct_p999_delta_ns": fct_p999,
        "baseline_summary": {"incomplete": incomplete_baseline},
        "injected_summary": {"incomplete": incomplete_injected},
    }


def test_perfect_answer_passes_all_rubrics():
    text = (
        "I see silent drops in the injected run: there are 5 missing flows "
        "compared to the baseline (flow-count delta of -5). Several flows "
        "are incomplete — they did not complete. The p99 tail latency also "
        "shifts, suggesting distribution-level impact."
    )
    score = score_silent_drops_localization(
        _comparison(incomplete_injected=3),
        _completion(text),
    )
    assert score.overall_pass is True
    assert score.criteria == {
        "identifies_failure_class": True,
        "cites_flow_count_delta": True,
        "acknowledges_incomplete_flows": True,
        "cites_distribution_signal": True,
    }


def test_naked_model_failure_mode_fails_all_rubrics():
    """A vague hand-wavy answer that names no signal: fails everything."""
    text = (
        "Based on the data, something looks off. The injected run shows "
        "different behavior than the baseline. I would investigate further "
        "by collecting more telemetry."
    )
    score = score_silent_drops_localization(
        _comparison(incomplete_injected=2),
        _completion(text),
    )
    assert score.overall_pass is False
    assert score.criteria["identifies_failure_class"] is False
    assert score.criteria["cites_flow_count_delta"] is False
    assert score.criteria["acknowledges_incomplete_flows"] is False
    assert score.criteria["cites_distribution_signal"] is False


def test_partial_credit_failure_class_only():
    text = "This looks like packet loss but I can't tell why."
    score = score_silent_drops_localization(
        _comparison(),
        _completion(text),
    )
    assert score.overall_pass is False
    assert score.criteria["identifies_failure_class"] is True
    assert score.criteria["cites_flow_count_delta"] is False


def test_rubric_skipped_when_signal_absent():
    """If the comparison shows no incomplete flows, that rubric isn't required."""
    text = (
        "Silent drops are dropping packets and produce fewer flows in the "
        "injected run. The p99 tail shifts."
    )
    score = score_silent_drops_localization(
        _comparison(incomplete_baseline=0, incomplete_injected=0),
        _completion(text),
    )
    assert "acknowledges_incomplete_flows" not in score.criteria
    assert score.overall_pass is True


def test_distribution_rubric_skipped_when_no_percentile_signal():
    text = "Silent drops, fewer flows."
    score = score_silent_drops_localization(
        _comparison(fct_p50=0, fct_p99=0, fct_p999=0, incomplete_injected=0),
        _completion(text),
    )
    assert "cites_distribution_signal" not in score.criteria
    assert score.criteria["identifies_failure_class"] is True
    assert score.criteria["cites_flow_count_delta"] is True
    assert score.overall_pass is True


def test_count_rubric_skipped_when_no_divergence():
    """If baseline and injected have the same flow count, no count-rubric."""
    text = "Latency-only regression at the p99 tail."
    score = score_silent_drops_localization(
        _comparison(flow_count_delta=0, has_count_divergence=False, incomplete_injected=0),
        _completion(text),
    )
    assert "cites_flow_count_delta" not in score.criteria


def test_rationale_includes_ground_truth_signals():
    score = score_silent_drops_localization(
        _comparison(flow_count_delta=-7, incomplete_injected=4),
        _completion("nothing useful"),
    )
    assert "flow_count_delta=-7" in score.rationale
    assert "has_count_divergence=True" in score.rationale
    assert "incomplete_injected=4" in score.rationale


def test_silent_drop_phrase_with_hyphen_or_space():
    for phrase in ["silent drops", "silent-drops", "Silent Drop"]:
        score = score_silent_drops_localization(
            _comparison(incomplete_injected=0),
            _completion(f"{phrase} fewer flows p99"),
        )
        assert score.criteria["identifies_failure_class"] is True, phrase
