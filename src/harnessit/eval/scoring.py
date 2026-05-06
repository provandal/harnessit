"""Triage-quality scoring rubrics.

The shift from Stage 2 v1 (which scored "did the model read off the
pre-computed comparison stats?") to v2 (which scores triage quality
under realistic input) is in response to Erik's 2026-05-06 critique:
the v1 prompt leaked the answer key by enumerating failure classes and
handing over a pre-digested comparison. A real on-call ticket reports a
*symptom*, not analytics output. The right test is whether the agent's
response — given only a symptom — would, *if executed*, surface the
ground truth.

Architecture v0.5 §3.8 names the substrate-level commitments: flow-count
delta as primary failure signature, distribution-aware comparison,
incomplete-operation annotation. Those commitments still anchor scoring,
but they shift roles. In v2:

* The substrate signals (target_run, comparison if paired) live in the
  ``EvalContext`` as **ground truth** for grading — the runner has them,
  the model does not.
* The model's response is graded on whether its proposed investigation
  would query the §3.8-aligned signals: per-flow completion stats,
  percentile distributions, incomplete-flow counts, per-link counters.
* Rubrics also measure investigative discipline: multiple hypotheses
  (no premature lock-in), acknowledgment of unknowns, coherent ordering.

Keyword-driven for Stage 2. Stage 11+ replaces with LLM-as-judge or
similar; until then, occasional false-failures where the model's
reasoning is sound but the regex doesn't match its phrasing are an
expected, captured limitation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from harnessit.model import Completion

if TYPE_CHECKING:
    from harnessit.eval.types import EvalContext


@dataclass(frozen=True)
class Score:
    """Structured grade for one eval run.

    ``criteria`` maps named rubrics to bool (passed?). ``overall_pass``
    is True iff every criterion is True (and at least one criterion
    was applicable). ``rationale`` is human-readable explanation.
    """

    overall_pass: bool
    criteria: dict[str, bool] = field(default_factory=dict)
    rationale: str = ""


# ----------------------------------------------------------------------
# Patterns. Compiled once. Each rubric is a list of patterns that count
# as "the model touched this concept." A response only needs to match
# one pattern in a list to credit that rubric.
# ----------------------------------------------------------------------

# Hypothesis classes a savvy network engineer might consider when
# given "host X is slow" without further context. Spans application
# behavior (collective ops), fabric mechanics (PFC, ECMP), and host
# pathologies (NIC). Used to count *how many distinct hypotheses* the
# response mentions — not whether any specific one is right.
_HYPOTHESIS_PATTERNS: dict[str, re.Pattern[str]] = {
    "incast_or_microburst": re.compile(
        r"\b(incast|micro[-\s]?burst|synchronized\s+(burst|incast|"
        r"transmission)|many[-\s]?to[-\s]?one)\b",
        re.IGNORECASE,
    ),
    "synchronized_collective": re.compile(
        r"\b(all[-\s]?reduce|all[-\s]?gather|broadcast\s+pattern|"
        r"barrier|collective\s+(op|operation)|gradient\s+sync|"
        r"synchroniz(ed|ation)\s+(application|workload|job|step|"
        r"collective))\b",
        re.IGNORECASE,
    ),
    "ecmp_or_hashing": re.compile(
        r"\b(ECMP|hash\s+(polariz|imbalance|collision)|flow\s+hash|"
        r"path\s+(asymmetry|imbalance)|polariz(ation|ed))\b",
        re.IGNORECASE,
    ),
    "pfc_or_pause": re.compile(
        r"\b(PFC|pause\s+frame|priority\s+flow\s+control|head[-\s]?of[-\s]?"
        r"line\s+block(ing)?|HOL\s+block)\b",
        re.IGNORECASE,
    ),
    "ecn_or_congestion_marking": re.compile(
        r"\b(ECN|explicit\s+congestion\s+notification|congestion\s+mark|"
        r"DCQCN|congestion\s+control)\b",
        re.IGNORECASE,
    ),
    "buffer_or_queue": re.compile(
        # Hypothesis = fault-state language. Bare "queue depth" or "buffer
        # depth" is a metric, not a hypothesis — those land in the
        # telemetry rubric. Hypothesis credit requires fill/saturation
        # verbs/adjectives.
        r"\b(buffer\s+(pressure|exhaust|exhausted|overrun|"
        r"fill(ing|ed)|saturat(ed|ion))|queue(s)?\s+"
        r"(buildup|build[-\s]?up|fill(ing|ed)|exhaust|exhausted|"
        r"saturat(ed|ion))|deep\s+queue|HOL\s+block(ing)?|"
        r"head[-\s]?of[-\s]?line\s+block)\b",
        re.IGNORECASE,
    ),
    "host_or_nic": re.compile(
        r"\b(NIC\s+(issue|problem|fault|error)|host\s+(config|"
        r"misconfig|issue)|MTU|driver\s+(issue|problem))\b",
        re.IGNORECASE,
    ),
    "link_or_cable": re.compile(
        r"\b(link\s+(error|down|flap|failure)|cable\s+(issue|fault|"
        r"problem)|optical\s+(issue|fault)|FEC\s+errors?|CRC\s+errors?)\b",
        re.IGNORECASE,
    ),
    "silent_drops_or_loss": re.compile(
        r"\b(silent\s+drop|packet\s+(loss|drop)|invisible\s+drop|"
        r"undetected\s+(loss|drop))\b",
        re.IGNORECASE,
    ),
    "topology_or_routing": re.compile(
        r"\b(topology\s+(issue|problem|asymmetry)|routing\s+(issue|"
        r"problem|loop|misconfig)|spine\s+(failure|degraded)|"
        r"leaf\s+(failure|degraded))\b",
        re.IGNORECASE,
    ),
}

# Telemetry sources that map to §3.8-aligned signals. The model's
# triage plan should propose querying *some* of these. We don't require
# all — the rubric credits the response if it names enough of the
# §3.8 dimensions.
_TELEMETRY_PATTERNS: dict[str, re.Pattern[str]] = {
    "flow_completion": re.compile(
        r"\b(flow\s+completions?|FCT|completion\s+(time|rate|status)|"
        r"per[-\s]flow\s+(stats?|telemetry|data)|flow\s+manifests?|"
        r"flow\s+lists?|completed\s+flows?)\b",
        re.IGNORECASE,
    ),
    "distribution_or_percentile": re.compile(
        r"\b(distribution|percentile|p(50|90|95|99|999)|tail\s+"
        r"(latency|FCT)|histogram|CDF|long\s+tail)\b",
        re.IGNORECASE,
    ),
    "per_link_counters": re.compile(
        r"\b(per[-\s]?link\s+(counters?|stats?)|interface\s+"
        r"(counters?|stats?)|link\s+(utilization|throughput|drops?|"
        r"counters?)|TX/RX|tx[-\s]?rx|drops?\s+counters?|"
        r"switch\s+counters?|ports?\s+(counters?|stats?))\b",
        re.IGNORECASE,
    ),
    "queue_depth": re.compile(
        r"\b(queue\s+(depth|length|occupancy)|qlen|buffer\s+"
        r"occupancy|high[-\s]?water[-\s]?mark)\b",
        re.IGNORECASE,
    ),
    "pfc_or_ecn_counters": re.compile(
        r"\b(PFC\s+(counters?|events?|pauses?|firing|frames?|"
        r"telemetry)|pause\s+(counters?|events?|frames?)|"
        r"ECN\s+marks?|ECN\s+counters?|congestion\s+"
        r"(notification|marking|marks?))\b",
        re.IGNORECASE,
    ),
    "incomplete_or_failed_flows": re.compile(
        r"\b(incomplete\s+(flow|operation|transfer)|failed\s+"
        r"(flow|completion)|did\s+not\s+complete|never\s+completed?|"
        r"timeout(s|ed)?|missing\s+flows?)\b",
        re.IGNORECASE,
    ),
    "topology_query": re.compile(
        r"\b(topology|fabric\s+(layout|map)|leaf[-\s]?spine|which\s+"
        r"(switch|leaf|spine)|path\s+(map|attribution|trace)|"
        r"hop[-\s]?count|ECMP\s+bucket)\b",
        re.IGNORECASE,
    ),
}

# Hedging / acknowledgment-of-unknowns phrases. The honest naked-model
# answer says "I'd need X" or "without Y I can't tell." The dishonest
# answer guesses with false confidence. This rubric credits the former.
_ACKNOWLEDGMENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(would\s+need|I'?d\s+(need|want|like\s+to)|need(s|ed)?\s+"
        r"(to\s+)?(see|check|query|gather|collect|access|know))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(without|in\s+the\s+absence\s+of|I\s+(don'?t|do\s+not)\s+"
        r"have)\b[^.]{0,80}(data|telemetry|access|information|"
        r"context|topology)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(insufficient|cannot|unable|can'?t|impossible)\s+to\s+"
        r"(say|determine|tell|localize|identify|pinpoint|narrow)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bmore\s+(info|information|data|context|telemetry)\b"
        r"[^.]{0,30}\b(needed|required|help(ful|s)?|useful|"
        r"would\s+help)\b",
        re.IGNORECASE,
    ),
    # Bare "more information would help" / "more telemetry needed"
    re.compile(
        r"\b(more|additional)\s+(info|information|data|context|"
        r"telemetry)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(clarif(y|ication)|further\s+(question|info|data))\b",
        re.IGNORECASE,
    ),
]

# Sequencing phrases — the response should look like an ordered plan,
# not a list of disconnected musings. We're permissive: any of numbered
# lists, ordinals, or sequence words count.
_SEQUENCING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*(?:[0-9]+|[a-z])[\.\)]\s", re.MULTILINE),
    re.compile(
        r"\b(first|second|third|fourth|next|then|after\s+that|"
        r"finally|lastly|step\s+\d+)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(start\s+(by|with)|begin\s+(by|with)|initial\s+step)\b", re.IGNORECASE),
]


def _count_matches(text: str, patterns: dict[str, re.Pattern[str]]) -> set[str]:
    return {name for name, pattern in patterns.items() if pattern.search(text)}


def _any_match(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def score_triage_quality(
    context: "EvalContext",
    completion: Completion,
    *,
    min_hypotheses: int = 3,
    min_telemetry_sources: int = 4,
) -> Score:
    """Score the model's triage response under realistic on-call input.

    Four rubrics, all required for ``overall_pass``:

    * **considers_multiple_hypotheses** — at least ``min_hypotheses``
      distinct hypothesis classes mentioned. Defends against premature
      lock-in.
    * **names_telemetry_to_query** — at least ``min_telemetry_sources``
      §3.8-aligned signal categories named as things to investigate.
    * **acknowledges_unknowns** — the response hedges or names what it
      doesn't have. Defends against false-confidence guessing.
    * **coherent_investigation_order** — the response is structured as
      a sequence (numbered steps, ordinals, or sequence words), not a
      bag of points.

    The thresholds (3 hypotheses, 4 telemetry sources) are calibrated
    against typical naked-model outputs seen on the spike-burst recon;
    they're tuned to demand a substantive response without requiring
    encyclopedic coverage.
    """
    text = completion.text or ""

    hypotheses_hit = _count_matches(text, _HYPOTHESIS_PATTERNS)
    telemetry_hit = _count_matches(text, _TELEMETRY_PATTERNS)

    criteria: dict[str, bool] = {
        "considers_multiple_hypotheses": len(hypotheses_hit) >= min_hypotheses,
        "names_telemetry_to_query": len(telemetry_hit) >= min_telemetry_sources,
        "acknowledges_unknowns": _any_match(text, _ACKNOWLEDGMENT_PATTERNS),
        "coherent_investigation_order": _any_match(text, _SEQUENCING_PATTERNS),
    }

    overall_pass = all(criteria.values()) and len(criteria) > 0

    rationale_parts = [
        f"hypotheses_hit={sorted(hypotheses_hit)} ({len(hypotheses_hit)}/"
        f"{min_hypotheses} required).",
        f"telemetry_hit={sorted(telemetry_hit)} ({len(telemetry_hit)}/"
        f"{min_telemetry_sources} required).",
    ]
    for criterion, passed in criteria.items():
        rationale_parts.append(f"{criterion}: {'PASS' if passed else 'FAIL'}.")

    return Score(
        overall_pass=overall_pass,
        criteria=criteria,
        rationale=" ".join(rationale_parts),
    )
