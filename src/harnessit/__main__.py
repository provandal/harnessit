"""HarnessIT CLI — run an eval scenario end-to-end.

Usage::

    python -m harnessit                                # default scenario
    python -m harnessit microburst-symptom-only
    python -m harnessit microburst-with-topology

Stage 2 ships two scenarios that share the same underlying microburst
fault but vary in how much context the user prompt carries. Output is
``format_eval_summary`` text to stdout. Spans + scores emit to Langfuse
Cloud for the trajectory viewer (Stage 4) to render.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from harnessit.config import load_settings
from harnessit.eval import EvalResult
from harnessit.eval.runner import format_eval_summary, run_eval
from harnessit.model import ModelClient
from harnessit.scenarios import microburst_symptom_only, microburst_with_topology
from harnessit.substrate import DoppelgangerClient
from harnessit.tracing import flush_langfuse, init_langfuse

SCENARIO_FACTORIES = {
    "microburst-symptom-only": microburst_symptom_only,
    "microburst-with-topology": microburst_with_topology,
}
DEFAULT_SCENARIO = "microburst-symptom-only"


async def _run(scenario_name: str) -> EvalResult:
    settings = load_settings()
    init_langfuse(settings)
    scenario = SCENARIO_FACTORIES[scenario_name]()
    async with DoppelgangerClient.connect() as substrate:
        model_client = ModelClient.from_settings(settings)
        result = await run_eval(
            scenario=scenario,
            substrate=substrate,
            model_client=model_client,
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
    args = parser.parse_args(argv)

    result = asyncio.run(_run(args.scenario))
    print(format_eval_summary(result))
    return 0 if result.score.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
