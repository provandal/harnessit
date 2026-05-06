"""Silent-drops localization — the first eval scenario.

The naked frontier model is given the aggregate comparison between a
healthy baseline run and an injected run with silent drops. It is
asked to identify the failure class and localize the affected flows.

This scenario is *expected to fail* per Build Plan v0.3 §2.1 stage 2:
"the first eval scenario runs end-to-end and the model fails it
visibly." The naked model has no tools, no per-flow data, and no
topology context — only the aggregate comparison Doppelgänger emits.
The keyword-level §3.8 rubrics may be satisfiable by a good guess, but
the ``localizes_affected_flows`` rubric isn't, because the prompt
deliberately does not include per-flow data. Stage 3 grows tool
surface that turns this from a guess into a verified localization.
"""

from __future__ import annotations

import re
from typing import Any

from harnessit.eval.scoring import Score, score_silent_drops_localization
from harnessit.eval.types import EvalScenario
from harnessit.model import Completion

SCENARIO_NAME = "silent-drops-localization"
BASELINE_SCENARIO = "spike-burst-baseline"
INJECTED_SCENARIO = "spike-burst-silent-drops"

SYSTEM_PROMPT = """\
You are a network-investigation assistant for a leaf-spine RDMA fabric \
running under the Doppelgänger network simulator.

You are given a numerical comparison between two simulation runs:
  - "baseline" — a healthy run with no fault injection
  - "injected" — the same workload with one fault class injected

Your task is to answer two questions:
  1. What failure class was injected?
  2. Which flows are affected, and how would you localize them?

Reason only from the data provided. Be specific about which signals \
support your answer (flow-count delta, percentile shifts, incomplete-flow \
counts, etc.). If the data is insufficient to localize specific flows, \
say so explicitly and explain what you would need.

Possible failure classes (per Doppelgänger v0.2 §5.2):
  silent drops, microburst, PFC storm, asymmetric path,
  hash polarization, link flap, buffer misconfig.
"""


def build_user_prompt(comparison: dict[str, Any]) -> str:
    """Render the comparison data as a structured user prompt.

    Per Architecture v0.5 §3.8, the primary failure signature is
    ``flow_count_delta``; tail-distribution shifts and incomplete-flow
    counts are the secondary signals. We surface all three explicitly.
    Per-flow data is *not* included — that would let the naked model
    do set-difference localization without tools, which Stage 3 is
    intended to demonstrate.
    """
    baseline = comparison.get("baseline_summary", {}) or {}
    injected = comparison.get("injected_summary", {}) or {}
    findings = comparison.get("findings", []) or []

    return (
        "## Comparison summary\n"
        "\n"
        f"flow_count_delta: {comparison.get('flow_count_delta')} "
        "(injected − baseline; negative = fewer flows in injected)\n"
        f"has_count_divergence: {comparison.get('has_count_divergence')}\n"
        "\n"
        "## FCT percentile deltas (injected − baseline, nanoseconds)\n"
        "\n"
        f"  p50:  {comparison.get('fct_p50_delta_ns')}\n"
        f"  p99:  {comparison.get('fct_p99_delta_ns')}\n"
        f"  p999: {comparison.get('fct_p999_delta_ns')}\n"
        "\n"
        "## Per-run summaries\n"
        "\n"
        f"baseline: total={baseline.get('total')} "
        f"completed={baseline.get('completed')} "
        f"incomplete={baseline.get('incomplete')}\n"
        f"  by_status: {baseline.get('by_status')}\n"
        f"  fct: {baseline.get('fct')}\n"
        "\n"
        f"injected: total={injected.get('total')} "
        f"completed={injected.get('completed')} "
        f"incomplete={injected.get('incomplete')}\n"
        f"  by_status: {injected.get('by_status')}\n"
        f"  fct: {injected.get('fct')}\n"
        "\n"
        "## Comparison findings\n"
        "\n"
        + ("\n".join(f"  - {f}" for f in findings) if findings else "  (none)")
        + "\n\n"
        "Per the system prompt, identify the failure class and explain "
        "how you would localize the affected flows.\n"
    )


# Per-flow localization is gated separately because per-flow data is
# deliberately absent from the prompt; passing this rubric would
# require the model to either fabricate flow tuples or hedge.
_LOCALIZATION_PATTERNS = [
    # Specific 4-tuple patterns: 10.0.0.1:4444 or src=...:port
    re.compile(r"\b\d+\.\d+\.\d+\.\d+:\d+\b"),
    # Concrete (sip, dip, sport, dport) tuples
    re.compile(r"\(\s*\d+\.\d+\.\d+\.\d+\s*,", re.IGNORECASE),
    # Honest "I cannot localize specific flows" — credit for honesty.
    re.compile(
        r"(insufficient|cannot|unable|can't|impossible)[^.]{0,80}"
        r"(localize|identify\s+specific|per[-\s]flow)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(no|without)\s+per[-\s]?flow\s+data",
        re.IGNORECASE,
    ),
    re.compile(
        r"would\s+need[^.]{0,80}(per[-\s]flow|tool|access)",
        re.IGNORECASE,
    ),
]


def score(comparison: dict[str, Any], completion: Completion) -> Score:
    """Score the model's silent-drops localization attempt.

    Combines the four §3.8 rubrics from
    ``score_silent_drops_localization`` with one additional
    Stage-2-specific rubric: ``localizes_affected_flows``. The naked
    model is expected to fail this — either by claiming localization
    it can't justify, or (the better failure mode) by acknowledging
    the prompt doesn't carry per-flow data and naming what it would
    need. Both honest acknowledgment and concrete-tuple localization
    pass; vague gestures fail.
    """
    base = score_silent_drops_localization(comparison, completion)
    text = completion.text or ""
    localizes = any(p.search(text) for p in _LOCALIZATION_PATTERNS)

    criteria = dict(base.criteria)
    criteria["localizes_affected_flows"] = localizes
    overall_pass = all(criteria.values()) and len(criteria) > 0

    rationale = base.rationale + (
        f" localizes_affected_flows: {'PASS' if localizes else 'FAIL'}"
    )
    return Score(overall_pass=overall_pass, criteria=criteria, rationale=rationale)


def silent_drops_localization() -> EvalScenario:
    """Factory for the silent-drops localization scenario."""
    return EvalScenario(
        name=SCENARIO_NAME,
        description=(
            "Naked frontier model attempts to localize silent drops "
            "given only aggregate comparison data. Expected to fail the "
            "localization rubric because per-flow data is intentionally "
            "withheld."
        ),
        system_prompt=SYSTEM_PROMPT,
        baseline_scenario=BASELINE_SCENARIO,
        injected_scenario=INJECTED_SCENARIO,
        build_user_prompt=build_user_prompt,
        score=score,
        expected_to_pass=False,
    )
