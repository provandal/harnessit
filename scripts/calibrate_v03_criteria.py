"""Calibrate v0.3 LLM-judge criteria against anchor traces.

For 5 anchor traces with known correctness verdicts, verify that the
two new criteria (operational_stance_matches_epistemic_state,
hypothesis_preservation_under_insufficient_data) separate CORRECT from
WRONG the way the cross-trace analysis (2026-05-13) predicts.

Expected outcomes:

  silent-drops-skillv02-k2 (CORRECT)        both new criteria PASS
  microburst-skillv02-k1 (CORRECT)          both new criteria PASS
  silent-drops-skillv02-D2fix-k1 (WRONG)    operational_stance FAIL
  silent-drops-skillv02-D2fix-k2 (WRONG)    hypothesis_preservation FAIL
  hash-polarization-skillv02-k3 (WRONG)     hypothesis_preservation FAIL

Existing 5 criteria are run too — they're not the focus, but the
output prints them for context.

Usage::

    python scripts/calibrate_v03_criteria.py
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from harnessit.config import load_settings
from harnessit.eval.judge import Judge


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AnchorTrace:
    """One log file + expectations for the v0.3 criteria."""

    label: str
    log_path: Path
    scenario_module: str  # e.g., "harnessit.scenarios.silent_drops"
    correctness: str  # "CORRECT" or "WRONG"
    expected_operational_stance: str  # "PASS" or "FAIL"
    expected_hypothesis_preservation: str  # "PASS" or "FAIL"


ANCHORS: tuple[AnchorTrace, ...] = (
    AnchorTrace(
        label="silent-drops-skillv02-k2 (variance pass, CORRECT)",
        log_path=WORKSPACE_ROOT / "sweep-logs-2026-05-12-variance" / "silent-drops-skillv02-k2.log",
        scenario_module="harnessit.scenarios.silent_drops",
        correctness="CORRECT",
        expected_operational_stance="PASS",
        expected_hypothesis_preservation="PASS",
    ),
    AnchorTrace(
        label="microburst-skillv02-k1 (variance pass, CORRECT)",
        log_path=WORKSPACE_ROOT / "sweep-logs-2026-05-12-variance" / "microburst-skillv02-k1.log",
        scenario_module="harnessit.scenarios.microburst",
        correctness="CORRECT",
        expected_operational_stance="PASS",
        expected_hypothesis_preservation="PASS",
    ),
    AnchorTrace(
        label="silent-drops-skillv02-D2fix-k1 (D2 verify, WRONG)",
        log_path=WORKSPACE_ROOT / "sweep-logs-2026-05-13-verify-D2-fix-retry" / "silent-drops-skillv02-D2fix-k1.log",
        scenario_module="harnessit.scenarios.silent_drops",
        correctness="WRONG",
        expected_operational_stance="FAIL",
        expected_hypothesis_preservation="FAIL",
    ),
    AnchorTrace(
        # D2 k2 has step 1 that's legitimate verification *of the stated verdict's
        # within-leaf alternatives*; the wrongness lives in the verdict's prior
        # exclusion of fabric-wide. operational_stance grades step 1 against the
        # stated verdict (PASS); hypothesis_preservation catches the upstream
        # exclusion (FAIL). The two criteria do complementary work — D2 k2 is
        # the trace that proves the division of labor.
        label="silent-drops-skillv02-D2fix-k2 (D2 verify, WRONG)",
        log_path=WORKSPACE_ROOT / "sweep-logs-2026-05-13-verify-D2-fix-retry" / "silent-drops-skillv02-D2fix-k2.log",
        scenario_module="harnessit.scenarios.silent_drops",
        correctness="WRONG",
        expected_operational_stance="PASS",
        expected_hypothesis_preservation="FAIL",
    ),
    AnchorTrace(
        label="hash-polarization-skillv02-k3 (variance pass, WRONG)",
        log_path=WORKSPACE_ROOT / "sweep-logs-2026-05-12-variance" / "hash-polarization-skillv02-k3.log",
        scenario_module="harnessit.scenarios.hash_polarization",
        correctness="WRONG",
        expected_operational_stance="FAIL",
        expected_hypothesis_preservation="FAIL",
    ),
)


_OUTPUT_RE = re.compile(
    r"--- model output \([^)]+\) ---\s*\n(.*?)\n--- scoring",
    re.DOTALL,
)


def extract_response_text(log_path: Path) -> str:
    text = log_path.read_text(encoding="utf-8")
    m = _OUTPUT_RE.search(text)
    if not m:
        raise RuntimeError(f"Could not extract model output from {log_path}")
    return m.group(1).strip()


def load_scenario_prompts(module_path: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) by importing the module's constants."""
    import importlib

    mod = importlib.import_module(module_path)
    system_prompt = getattr(mod, "SYSTEM_PROMPT")
    user_ticket = getattr(mod, "USER_TICKET")
    return system_prompt, user_ticket


def _verdict_str(b: bool) -> str:
    return "PASS" if b else "FAIL"


async def calibrate_one(judge: Judge, anchor: AnchorTrace) -> dict[str, Any]:
    response = extract_response_text(anchor.log_path)
    system_prompt, user_prompt = load_scenario_prompts(anchor.scenario_module)
    judgment = await judge.score(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        agent_response=response,
    )
    by_name = {c.name: c for c in judgment.criteria}

    op = by_name.get("operational_stance_matches_epistemic_state")
    hp = by_name.get("hypothesis_preservation_under_insufficient_data")
    if op is None or hp is None:
        raise RuntimeError(
            "Judge did not return both new criteria. "
            f"Got: {list(by_name.keys())}"
        )

    op_match = _verdict_str(op.passed) == anchor.expected_operational_stance
    hp_match = _verdict_str(hp.passed) == anchor.expected_hypothesis_preservation

    return {
        "label": anchor.label,
        "correctness": anchor.correctness,
        "operational_stance": {
            "expected": anchor.expected_operational_stance,
            "actual": _verdict_str(op.passed),
            "match": op_match,
            "rationale": op.rationale,
        },
        "hypothesis_preservation": {
            "expected": anchor.expected_hypothesis_preservation,
            "actual": _verdict_str(hp.passed),
            "match": hp_match,
            "rationale": hp.rationale,
        },
        "all_criteria": {
            c.name: {"passed": c.passed, "rationale": c.rationale}
            for c in judgment.criteria
        },
        "overall_pass": judgment.overall_pass,
    }


def render(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"\n=== {report['label']} ===")
    lines.append(f"  correctness (ground truth): {report['correctness']}")
    lines.append(f"  judge overall_pass: {report['overall_pass']}")
    for key in ("operational_stance", "hypothesis_preservation"):
        d = report[key]
        marker = "[OK]" if d["match"] else "[MISMATCH]"
        lines.append(
            f"  {marker} {key}: expected={d['expected']} actual={d['actual']}"
        )
        # First 200 chars of rationale, single-line
        rat = " ".join(d["rationale"].split())[:280]
        lines.append(f"      rationale: {rat}")
    lines.append("  other criteria:")
    for name, c in report["all_criteria"].items():
        if name in ("operational_stance_matches_epistemic_state",
                    "hypothesis_preservation_under_insufficient_data"):
            continue
        lines.append(f"    [{_verdict_str(c['passed'])}] {name}")
    return "\n".join(lines)


async def main() -> int:
    settings = load_settings()
    judge = Judge.from_settings(settings, max_tokens=3072)

    print("=" * 72)
    print("v0.3 LLM-judge criteria calibration against 5 anchor traces")
    print("=" * 72)

    reports: list[dict[str, Any]] = []
    for anchor in ANCHORS:
        try:
            report = await calibrate_one(judge, anchor)
        except Exception as exc:
            print(f"\n=== {anchor.label} ===")
            print(f"  ERROR: {exc!r}")
            reports.append({"label": anchor.label, "error": repr(exc)})
            continue
        print(render(report))
        reports.append(report)

    # Summary
    print("\n" + "=" * 72)
    print("Summary")
    print("=" * 72)
    op_correct = sum(
        1 for r in reports
        if "operational_stance" in r and r["operational_stance"]["match"]
    )
    hp_correct = sum(
        1 for r in reports
        if "hypothesis_preservation" in r and r["hypothesis_preservation"]["match"]
    )
    n = sum(1 for r in reports if "operational_stance" in r)
    print(f"  operational_stance_matches_epistemic_state: {op_correct}/{n} match expectation")
    print(f"  hypothesis_preservation_under_insufficient_data: {hp_correct}/{n} match expectation")

    if op_correct == n and hp_correct == n:
        print("\n  ALL EXPECTATIONS MET — criteria are calibrated; ready for verify sweep.")
        return 0
    print("\n  MISMATCHES PRESENT — see per-trace rationale above; iterate on criterion descriptions before sweep.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
