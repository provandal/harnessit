"""HarnessIT CLI — run an eval scenario end-to-end.

Usage::

    python -m harnessit                                # default scenario
    python -m harnessit microburst-symptom-only
    python -m harnessit microburst-with-topology
    python -m harnessit microburst-with-topology-tool

Stage 3 ships three scenarios that share the same underlying microburst
fault but vary in how the agent gets at fabric context: nothing
(symptom-only), pre-loaded in the prompt (with-topology), or available
on demand via a tool (with-topology-tool). Output is
``format_eval_summary`` text to stdout. Spans + scores emit to Langfuse
Cloud for the trajectory viewer (Stage 4) to render.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

# Force UTF-8 on stdout. Judge rationales routinely include unicode
# arrows / glyphs that crash cp1252 on Windows consoles when piped
# through tee. Failure (e.g., stdout is a detached file handle on some
# platforms) is non-fatal.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

from dataclasses import replace

from harnessit.config import load_settings
from harnessit.eval import EvalResult
from harnessit.eval.correctness import CorrectnessJudge
from harnessit.eval.judge import Judge
from harnessit.eval.runner import format_eval_summary, run_eval
from harnessit.model import ModelClient
from harnessit.skills import load_skill_by_name
from harnessit.scenarios import (
    asymmetric_path_with_counters_tool,
    hash_polarization_with_counters_tool,
    microburst_symptom_only,
    microburst_with_counters_tool,
    microburst_with_topology,
    microburst_with_topology_tool,
    pfc_storm_realistic_with_counters_tool,
    pfc_storm_with_counters_tool,
    silent_drops_with_counters_tool,
)
from harnessit.substrate import DoppelgangerClient
from harnessit.tracing import flush_langfuse, init_langfuse

SCENARIO_FACTORIES = {
    "microburst-symptom-only": microburst_symptom_only,
    "microburst-with-topology": microburst_with_topology,
    "microburst-with-topology-tool": microburst_with_topology_tool,
    "microburst-with-counters-tool": microburst_with_counters_tool,
    "pfc-storm-with-counters-tool": pfc_storm_with_counters_tool,
    "pfc-storm-realistic-with-counters-tool": pfc_storm_realistic_with_counters_tool,
    "asymmetric-path-with-counters-tool": asymmetric_path_with_counters_tool,
    "hash-polarization-with-counters-tool": hash_polarization_with_counters_tool,
    "silent-drops-with-counters-tool": silent_drops_with_counters_tool,
}
DEFAULT_SCENARIO = "microburst-symptom-only"


async def _run(
    scenario_name: str,
    *,
    use_judge: bool,
    use_correctness: bool,
    judge_model: str | None,
    skill_names: tuple[str, ...],
) -> EvalResult:
    settings = load_settings()
    init_langfuse(settings)
    scenario = SCENARIO_FACTORIES[scenario_name]()
    if skill_names:
        loaded_skills = tuple(load_skill_by_name(n) for n in skill_names)
        scenario = replace(scenario, skills=scenario.skills + loaded_skills)
    judge = (
        Judge.from_settings(settings, model=judge_model) if use_judge else None
    )
    correctness_judge = (
        CorrectnessJudge.from_settings(settings, model=judge_model)
        if use_correctness else None
    )
    async with DoppelgangerClient.connect() as substrate:
        model_client = ModelClient.from_settings(settings)
        result = await run_eval(
            scenario=scenario,
            substrate=substrate,
            model_client=model_client,
            judge=judge,
            correctness_judge=correctness_judge,
        )
    flush_langfuse()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harnessit",
        description="Run a HarnessIT eval scenario end-to-end.",
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        default=DEFAULT_SCENARIO,
        choices=sorted(SCENARIO_FACTORIES),
        help="Scenario to run (default: %(default)s).",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help=(
            "Disable LLM-as-judge scoring; use keyword scoring only. "
            "Useful for fast iteration when you don't need the calibration "
            "table."
        ),
    )
    parser.add_argument(
        "--no-correctness",
        action="store_true",
        help=(
            "Disable diagnosis-correctness LLM scoring (orthogonal axis "
            "to the rubric). The rubric runs independently; this flag "
            "only affects correctness."
        ),
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help=(
            "Override the judge model id (default: claude-opus-4-7). "
            "Applied to both the rubric judge and the correctness judge."
        ),
    )
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "Load a skill by name and inject its body into the agent's "
            "system prompt. Can be specified multiple times to load "
            "more than one skill. Currently available: calibrated-commitment."
        ),
    )
    args = parser.parse_args(argv)

    result = asyncio.run(
        _run(
            args.scenario,
            use_judge=not args.no_judge,
            use_correctness=not args.no_correctness,
            judge_model=args.judge_model,
            skill_names=tuple(args.skill),
        )
    )
    print(format_eval_summary(result))
    return 0 if result.score.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
