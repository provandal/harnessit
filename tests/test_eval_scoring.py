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
    named telemetry, hedging, coherent order, AND synthesis (concrete
    fabric entities + quantitative reasoning + ruling-out)."""
    text = """
    Host 11.0.0.1 sits on leaf 0 (host id 0). Topology reports asymmetry: false,
    so cable degradation or a slow spine is unlikely — this is dynamic rather
    than structural. I'd want to investigate in this order:

    1. **Check if this is an incast/microburst pattern** — query per-flow
       completion stats for flows targeting 11.0.0.1 to see if many
       senders are hitting the host simultaneously. Look at the FCT
       distribution and tail percentiles (p50/p99/p999). The 1.5x slowdown
       is consistent with one or two extra concurrent senders sharing
       the receiver's 25 Gbps access link.

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

    I'd need access to the network telemetry before I could narrow
    this further.
    """
    score = score_triage_quality(_ctx(), _completion(text))
    assert score.overall_pass is True
    assert score.criteria == {
        "considers_multiple_hypotheses": True,
        "names_telemetry_to_query": True,
        "acknowledges_unknowns": True,
        "coherent_investigation_order": True,
        "synthesizes_available_context": True,
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
    assert "synthesis_hit=" in score.rationale


# ---------- Synthesis criterion (added 2026-05-07) ----------

def test_synthesis_concrete_fabric_entity_signal():
    """Naming concrete fabric entities (host id, node, leaf, spine, IP)
    counts as a synthesis signal."""
    text = (
        "Host 11.0.0.1 is host id 0 on leaf 0 (node 16). Spine 18 is "
        "the closest uplink. Could be incast on the access link, ECMP "
        "polarization, PFC backpressure, or a NIC issue. 1. Check "
        "queue depth. 2. Per-link counters. 3. FCT distribution. "
        "4. PFC pause frames. I'd need more info."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    # Three concrete entity references in one pattern hit
    assert score.criteria["synthesizes_available_context"] is False, (
        "single-signal hit should fall below the 2-signal threshold"
    )


def test_synthesis_quantitative_anchoring_signal():
    """Quantitative reasoning that ties symptom to fabric numbers
    counts as a synthesis signal."""
    text = (
        "On host 11.0.0.1: the 1.5x is consistent with one or two extra "
        "senders on the 25 Gbps link. Could be incast, ECMP polarization, "
        "PFC backpressure, or NIC issue. 1. Queue depth. 2. Per-link "
        "counters. 3. FCT. 4. PFC frames. I'd need more info."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    # Two distinct signals: concrete entity (host 11.0.0.1, 25 Gbps as IP
    # match isn't quite right but quantitative_anchoring's "consistent with"
    # match should fire alongside concrete_fabric_entity)
    assert score.criteria["synthesizes_available_context"] is True, (
        f"expected synthesis PASS with concrete entity + quantitative "
        f"anchoring; got rationale: {score.rationale}"
    )


def test_synthesis_ruling_out_signal():
    """Explicit elimination of hypotheses based on data is a
    synthesis signal."""
    text = (
        "On leaf 0, host 11.0.0.1: the topology reports asymmetry: false, "
        "so cable degradation is unlikely. Rules out structural causes. "
        "Could be incast, ECMP imbalance, PFC backpressure, or a NIC "
        "issue. 1. Queue depth. 2. Per-link counters. 3. FCT. "
        "4. PFC frames. I'd need more info."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    assert score.criteria["synthesizes_available_context"] is True


def test_synthesis_meta_pattern_signal():
    """Identifying meta-patterns (dynamic vs structural) counts as a
    synthesis signal."""
    text = (
        "On leaf 0, host 11.0.0.1: this is dynamic rather than structural. "
        "Could be incast, ECMP imbalance, PFC backpressure, or a NIC "
        "issue. 1. Queue depth. 2. Per-link counters. 3. FCT. "
        "4. PFC frames. I'd need more info."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    # concrete_fabric_entity (leaf 0 + host id-style IP) + meta_pattern
    assert score.criteria["synthesizes_available_context"] is True


def test_enumeration_without_synthesis_fails_synthesis_rubric():
    """Lists hypotheses + telemetry without integrating context — the
    Stage 3 with-topology pattern that prompted the criterion in the
    first place. Generic 'the destination's leaf' / 'a spine' references,
    no quantitative anchoring, no ruling-out via data."""
    text = (
        "The destination's leaf could be saturated. Possible causes: "
        "incast on the access link, ECMP polarization across spines, "
        "PFC propagation, NIC issue, cable/optic degradation. "
        "First, check switch counters. Then look at queue depth. "
        "Next, check PFC frames. After that, per-link drops, ECN marks "
        "on the path, and FCT distribution and tail percentiles. "
        "I'd need more info."
    )
    score = score_triage_quality(_ctx(), _completion(text))
    # Has all 4 original criteria but no synthesis: no concrete IDs, no
    # quantitative reasoning, no ruling-out, no meta-pattern.
    assert score.criteria["considers_multiple_hypotheses"] is True
    assert score.criteria["names_telemetry_to_query"] is True
    assert score.criteria["acknowledges_unknowns"] is True
    assert score.criteria["coherent_investigation_order"] is True
    assert score.criteria["synthesizes_available_context"] is False, (
        f"compliant-but-not-synthesizing response should fail synthesis; "
        f"got rationale: {score.rationale}"
    )
    # Overall must FAIL because synthesis is required
    assert score.overall_pass is False


def test_synthesis_threshold_can_be_tuned():
    """Min-synthesis-signals=1 should pass on a single-signal response
    that the default (2) would fail."""
    text = (
        "Host 11.0.0.1 on leaf 0. Could be incast, ECMP polarization, "
        "PFC backpressure, or NIC issue. 1. Queue depth. 2. Per-link "
        "counters. 3. FCT. 4. PFC frames. I'd need more info."
    )
    strict = score_triage_quality(_ctx(), _completion(text))
    lenient = score_triage_quality(
        _ctx(), _completion(text), min_synthesis_signals=1,
    )
    assert strict.criteria["synthesizes_available_context"] is False
    assert lenient.criteria["synthesizes_available_context"] is True
