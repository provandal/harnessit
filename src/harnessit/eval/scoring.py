"""Scoring rubrics that enforce Architecture v0.5 §3.8 commitments.

Per Architecture v0.5 §3.8, eval-time comparison must use:

1. **Flow-count delta** as the primary failure signature.
2. **Distribution-aware comparison** (percentile deltas, not means).
3. **Incomplete-operation annotation** — incomplete flows must be
   surfaced separately from completed-flow timing distributions.

These commitments live in ``doppelganger.eval.comparison`` and surface
in the ``compare_runs`` MCP-tool output as ``flow_count_delta``,
``fct_p{50,99,999}_delta_ns``, and per-status counts within the
``baseline_summary`` / ``injected_summary`` blocks.

The scoring functions in this module are deliberately keyword-driven
for Stage 2. They produce a structured ``Score`` whose criteria
correspond directly to the §3.8 commitments — so when the naked model
fails, we can see *which* commitments it missed. Stage 11+ replaces
keyword scoring with LLM-as-judge (or other) methods.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from harnessit.model import Completion


@dataclass(frozen=True)
class Score:
    """Structured grade for one eval run.

    ``criteria`` maps named §3.8-aligned rubrics to bool (passed?).
    ``overall_pass`` is True iff every criterion in ``criteria`` is
    True. ``rationale`` is human-readable explanation.
    """

    overall_pass: bool
    criteria: dict[str, bool] = field(default_factory=dict)
    rationale: str = ""


# Compiled patterns — readable + grep-friendly.
_FAILURE_CLASS_PATTERNS = [
    re.compile(r"\bsilent[-\s]+drop", re.IGNORECASE),
    re.compile(r"\bpacket[-\s]+(loss|drop)", re.IGNORECASE),
    re.compile(r"\blost\s+packets?", re.IGNORECASE),
]

_FLOW_COUNT_PATTERNS = [
    re.compile(r"\bflow[-\s]?count", re.IGNORECASE),
    re.compile(r"\bflow\s+count\s+delta", re.IGNORECASE),
    re.compile(r"\bnumber\s+of\s+flows", re.IGNORECASE),
    re.compile(r"\bfewer\s+flows", re.IGNORECASE),
    re.compile(r"\bmissing\s+flows?", re.IGNORECASE),
]

_INCOMPLETE_FLOW_PATTERNS = [
    re.compile(r"\bincomplete\s+flow", re.IGNORECASE),
    re.compile(r"\bdid\s+not\s+complete", re.IGNORECASE),
    re.compile(r"\bnever\s+completed", re.IGNORECASE),
    re.compile(r"\bunfinished\s+flow", re.IGNORECASE),
]

_DISTRIBUTION_PATTERNS = [
    re.compile(r"\bp(50|90|99|999)\b", re.IGNORECASE),
    re.compile(r"\b(median|percentile|tail|distribution)\b", re.IGNORECASE),
]


def _any_match(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def score_silent_drops_localization(
    comparison: dict[str, Any],
    completion: Completion,
) -> Score:
    """Score the naked model's silent-drops localization attempt.

    Criteria correspond directly to §3.8 commitments:

    * ``identifies_failure_class`` — the model names the failure class
      (silent drops / packet loss).
    * ``cites_flow_count_delta`` — primary signature: did the model
      reference the count gap as the first-order signal?
    * ``acknowledges_incomplete_flows`` — incomplete-operation
      annotation: did the model account for flows that didn't complete?
    * ``cites_distribution_signal`` — distribution-aware: did the model
      reference percentile / tail behavior, not just means?

    Ground truth comes from the comparison payload itself: only require
    the ``incomplete-flow`` rubric if the comparison actually shows
    incomplete flows; only require the distribution rubric if the
    percentile deltas are non-trivial.
    """
    text = completion.text or ""

    # Ground-truth: Doppelgänger reports flow_count_delta. Silent drops
    # produce a non-zero delta (typically negative, since dropped flows
    # never appear in injected fct.txt).
    has_count_divergence = comparison.get("has_count_divergence", False) or (
        comparison.get("flow_count_delta", 0) != 0
    )

    injected_summary = comparison.get("injected_summary", {}) or {}
    baseline_summary = comparison.get("baseline_summary", {}) or {}
    has_incomplete = (
        injected_summary.get("incomplete", 0) > 0
        or baseline_summary.get("incomplete", 0) > 0
    )

    pct_delta_signal = any(
        comparison.get(k) is not None and abs(comparison.get(k) or 0) > 0
        for k in ("fct_p50_delta_ns", "fct_p99_delta_ns", "fct_p999_delta_ns")
    )

    criteria: dict[str, bool] = {
        "identifies_failure_class": _any_match(text, _FAILURE_CLASS_PATTERNS),
    }

    if has_count_divergence:
        criteria["cites_flow_count_delta"] = _any_match(text, _FLOW_COUNT_PATTERNS)
    if has_incomplete:
        criteria["acknowledges_incomplete_flows"] = _any_match(
            text, _INCOMPLETE_FLOW_PATTERNS
        )
    if pct_delta_signal:
        criteria["cites_distribution_signal"] = _any_match(text, _DISTRIBUTION_PATTERNS)

    overall_pass = all(criteria.values()) and len(criteria) > 0

    rationale_parts: list[str] = []
    rationale_parts.append(
        f"flow_count_delta={comparison.get('flow_count_delta')}, "
        f"has_count_divergence={has_count_divergence}, "
        f"incomplete_baseline={baseline_summary.get('incomplete')}, "
        f"incomplete_injected={injected_summary.get('incomplete')}."
    )
    for criterion, passed in criteria.items():
        rationale_parts.append(f"{criterion}: {'PASS' if passed else 'FAIL'}")

    return Score(
        overall_pass=overall_pass,
        criteria=criteria,
        rationale=" ".join(rationale_parts),
    )
