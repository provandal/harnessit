"""Tests for triage-quality scoring rubrics.

The Stage 2 v2 scoring measures how the model *would* investigate
given a symptom — multiple hypotheses, named telemetry, acknowledged
unknowns, coherent ordering. These tests fix the rubric thresholds
against representative LLM outputs (good triage / vague guess / single
hypothesis lock-in) so regressions are caught when the rubric drifts.
"""

from __future__ import annotations

from harnessit.eval.scoring import score_triage_quality
from harnessit.eval.types import EvalContext
from harnessit.model import Completion


def _completion(text: str) -> Completion:
    return Completion(
        text=text,
        model="claude-opus-4-7",
        input_tokens=200,
        output_tokens=400,
        stop_reason="end_turn",
    )


def _ctx() -> EvalContext:
    """A minimal context for scoring — the rubric only reads completion.text."""
    return EvalContext(
        target_run={"run_id": "x", "trace_dir": "traces/x"},
        baseline_run=None,
        comparison=None,
        scenario_metadata={},
    )


# ---------- Good triage answers ----------

def test_good_triage_passes_all_rubrics():
    """Representative competent triage response: multiple hypotheses,
    named telemetry, hedging, coherent order."""
    text = """
    Without more information, this could be one of several things. I'd want
    to investigate in this order:

    1. **Check if this is an incast/microburst pattern** — query per-flow
       completion stats for flows targeting 11.0.0.1 to see if many
       senders are hitting the host simultaneously. Look at the FCT
       distribution and tail percentiles (p50/p99/p999).

    2. **Look at queue depth on the leaf switch** that hosts 11.0.0.1.
       If queue occupancy spikes during the burst windows, that's
       buffer pressure. Check PFC pause counters too — if PAUSE frames
       are firing, that's evidence of fabric-wide propagation.

    3. **Per-link counters on leaf<->spine links** — drop counters,
       throughput, ECN marks. Asymmetry would suggest hash polarization
       or a degraded link.

    4. **Check for synchronized application behavior** — is there an
       all-reduce or all-gather collective starting at 09:14? That
       could be an application-side cause masquerading as a network
       problem.

    I'd need access to the network telemetry and topology before I
    could narrow this further.
    """
    score = score_triage_quality(_ctx(), _completion(text))
    assert score.overall_pass is True
    assert score.criteria == {
        "considers_multiple_hypotheses": True,
        "names_telemetry_to_query": True,
        "acknowledges_unknowns": True,
        "coherent_investigation_order": True,
    }


def test_vague_answer_fails_everything():
    """A hedge-filled non-answer. Acknowledges unknown but doesn't
    propose hypotheses or telemetry."""
    text = (
        "I'm not sure what's going on. There could be several reasons. "
        "More information would help."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    assert score.overall_pass is False
    assert score.criteria["considers_multiple_hypotheses"] is False
    assert score.criteria["names_telemetry_to_query"] is False
    assert score.criteria["acknowledges_unknowns"] is True


def test_single_hypothesis_lock_in_fails_multi_hypothesis_rubric():
    """Confidently picks one cause, names some telemetry."""
    text = (
        "This is a microburst. Step 1: check FCT distribution. Step 2: "
        "check queue depth. Step 3: check per-link counters."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    assert score.criteria["considers_multiple_hypotheses"] is False
    assert score.criteria["names_telemetry_to_query"] is True
    assert score.criteria["coherent_investigation_order"] is True
    assert score.overall_pass is False


def test_hypotheses_without_telemetry_fails_telemetry_rubric():
    """Considers many causes but doesn't name what to query."""
    text = (
        "This could be: (1) an incast pattern, (2) PFC propagation, "
        "(3) ECMP hash polarization, (4) a NIC issue on the host, "
        "(5) cable/link degradation. I'd want more information."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    assert score.criteria["considers_multiple_hypotheses"] is True
    assert score.criteria["names_telemetry_to_query"] is False


def test_telemetry_without_hedging_fails_acknowledgment_rubric():
    """Names telemetry but pretends it has the data."""
    text = (
        "This is incast. Looking at the FCT distribution, p99 is up. "
        "Queue depth is high. Per-link counters show drops. PFC is "
        "firing. ECN marks are elevated. ECMP polarization isn't an "
        "issue. The host NIC is fine."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    assert score.criteria["considers_multiple_hypotheses"] is True
    assert score.criteria["names_telemetry_to_query"] is True
    assert score.criteria["acknowledges_unknowns"] is False


def test_unordered_bag_of_points_fails_ordering_rubric():
    """Mentions hypotheses + telemetry + hedging but not as a sequence."""
    text = (
        "Possible causes include incast and ECMP polarization and PFC "
        "propagation issues. Telemetry I would need: FCT distribution, "
        "queue depth, per-link counters. I would want more info."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    assert score.criteria["coherent_investigation_order"] is False


def test_numbered_steps_satisfy_ordering():
    text = (
        "1. Check FCT and per-link counters. 2. Look at queue depth. "
        "3. Check ECMP hash. Possible causes: incast, PFC propagation, "
        "and NIC issues. I'd want more info before concluding."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    assert score.criteria["coherent_investigation_order"] is True


def test_ordinal_words_satisfy_ordering():
    text = (
        "First, query FCT distribution and per-link counters. Then "
        "check queue depth. Finally look at ECMP hash distribution. "
        "Possible: incast, PFC propagation, NIC issue. I'd need more info."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    assert score.criteria["coherent_investigation_order"] is True


def test_thresholds_can_be_tuned():
    """min_hypotheses=2 should pass on a 2-hypothesis answer."""
    text = (
        "Could be incast or ECMP polarization. 1. Check FCT. 2. Look at "
        "queue depth. 3. Per-link counters. 4. Topology query. I'd need more info."
    )
    strict = score_triage_quality(_ctx(), _completion(text))
    lenient = score_triage_quality(_ctx(), _completion(text), min_hypotheses=2)
    assert strict.criteria["considers_multiple_hypotheses"] is False
    assert lenient.criteria["considers_multiple_hypotheses"] is True


def test_rationale_includes_hits():
    text = "Incast or ECMP. 1. FCT. 2. Queue depth. I'd need more info."
    score = score_triage_quality(_ctx(), _completion(text))
    assert "hypotheses_hit=" in score.rationale
    assert "telemetry_hit=" in score.rationale
