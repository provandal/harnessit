"""One-off recon: run a Doppelgänger scenario, dump ground-truth signals.

Not a unit test, not part of the harness — a discovery script that
answers "what does this scenario look like in this substrate?" so we
can write faithful symptom prompts for the Stage 2 eval reshape.

Usage::

    cd harnessit
    python scripts/microburst_recon.py            # microburst (default)
    python scripts/microburst_recon.py pfc_storm  # PFC storm + victim

Requires the doppelganger-substrate Docker image to be built locally.
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter
from pathlib import Path

from doppelganger.driver.simulation import Driver
from doppelganger.eval.comparison import summarize_run
from doppelganger.scenarios.builtin import microburst, pfc_storm

SCENARIO_FACTORIES = {
    "microburst": microburst,
    "pfc_storm": pfc_storm,
}


def hex_to_dotted(hex_ip: str) -> str:
    """Decode the substrate's 8-hex-digit IP form to dotted decimal."""
    return ".".join(str(int(hex_ip[i : i + 2], 16)) for i in (0, 2, 4, 6))


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "microburst"
    if name not in SCENARIO_FACTORIES:
        print(f"unknown scenario {name!r}; choose from: {list(SCENARIO_FACTORIES)}")
        sys.exit(1)
    driver = Driver()
    scenario = SCENARIO_FACTORIES[name]()
    print(f"Scenario: {scenario.name}")
    print(f"  topology: leaves={scenario.custom_topology.leaves}, "
          f"spines={scenario.custom_topology.spines}, "
          f"hosts/leaf={scenario.custom_topology.hosts_per_leaf}, "
          f"total hosts={scenario.custom_topology.num_hosts}")
    print(f"  intended_symptom: {scenario.intended_symptom}")
    print(f"  root_cause: {scenario.root_cause}")
    print()
    print("Running scenario via Driver (Docker substrate)...")
    result = driver.run_scenario(scenario, run_id=f"recon-{name}")
    print(f"Wall clock: {result.wall_clock_seconds:.1f}s")
    print(f"Trace dir: {result.trace_dir}")
    print()

    summary = summarize_run(result.flows)
    print("=" * 60)
    print("FLOW SUMMARY")
    print("=" * 60)
    print(f"  total flows expected:  {summary.total}")
    print(f"  completed:             {summary.completed}")
    print(f"  incomplete:            {summary.incomplete}")
    print(f"  by status:             {dict(summary.by_status)}")
    print()
    print("FCT distribution (completed flows, ns):")
    print(f"  min:   {summary.fct.min_ns:>15,}")
    print(f"  p50:   {summary.fct.p50_ns:>15,}")
    print(f"  p90:   {summary.fct.p90_ns:>15,}")
    print(f"  p99:   {summary.fct.p99_ns:>15,}")
    print(f"  p999:  {summary.fct.p999_ns:>15,}")
    print(f"  max:   {summary.fct.max_ns:>15,}")
    print(f"  mean:  {summary.fct.mean_ns:>15,.0f}")

    flows = result.flows
    print()
    print("=" * 60)
    print("FLOW DESTINATIONS — does the fault localize to host 0?")
    print("=" * 60)
    by_dst = Counter(hex_to_dotted(f.dip) for f in flows)
    print("Top destinations by flow count:")
    for dst, count in by_dst.most_common(5):
        print(f"  {dst:<20} {count}")

    # FCT distribution split: flows-to-host-0 vs flows-to-other-hosts.
    host0_dst = hex_to_dotted(min((f.dip for f in flows), key=lambda d: int(d, 16)))
    print(f"\nAssuming host 0 has IP {host0_dst}:")
    to_host0 = [f for f in flows if hex_to_dotted(f.dip) == host0_dst]
    to_other = [f for f in flows if hex_to_dotted(f.dip) != host0_dst]

    def _stats(vals: list[int]) -> str:
        if not vals:
            return "(empty)"
        s = sorted(vals)
        return (
            f"n={len(s)} "
            f"min={s[0]:,} "
            f"p50={s[len(s) // 2]:,} "
            f"p99={s[max(0, int(len(s) * 0.99) - 1)]:,} "
            f"max={s[-1]:,} "
            f"mean={statistics.mean(s):,.0f}"
        )

    print(f"  flows TO host 0:    {_stats([f.fct_ns for f in to_host0])}")
    print(f"  flows to OTHER:     {_stats([f.fct_ns for f in to_other])}")
    print()
    print(
        "Slowdown ratio (flow FCT / standalone FCT) for flows-to-host-0:")
    slowdowns = [
        f.fct_ns / f.standalone_fct_ns
        for f in to_host0
        if f.standalone_fct_ns and f.standalone_fct_ns > 0
    ]
    if slowdowns:
        s = sorted(slowdowns)
        print(f"  n={len(s)} "
              f"min={s[0]:.2f}x "
              f"p50={s[len(s) // 2]:.2f}x "
              f"p99={s[max(0, int(len(s) * 0.99) - 1)]:.2f}x "
              f"max={s[-1]:.2f}x")

    # PFC counters
    pfc_path = Path(result.trace_dir) / "pfc.txt"
    print()
    print("=" * 60)
    print("PFC EVENTS")
    print("=" * 60)
    if pfc_path.exists():
        lines = pfc_path.read_text().splitlines()
        print(f"  pfc.txt lines: {len(lines)}")
        if lines:
            print(f"  first line: {lines[0][:120]}")
            print(f"  last line:  {lines[-1][:120]}")
    else:
        print("  pfc.txt missing")

    # Queue lengths
    qlen_path = Path(result.trace_dir) / "qlen.txt"
    print()
    print("=" * 60)
    print("QUEUE LENGTH SAMPLES (qlen.txt)")
    print("=" * 60)
    if qlen_path.exists():
        lines = qlen_path.read_text().splitlines()
        print(f"  qlen.txt lines: {len(lines)}")
        if lines:
            print(f"  first line: {lines[0][:120]}")
            print(f"  last line:  {lines[-1][:120]}")
            # parse and find max queue depth
            max_qlen = 0
            max_line = ""
            for line in lines:
                parts = line.split()
                # format may be: time_ns node_id port qlen — try last numeric
                for p in reversed(parts):
                    try:
                        v = int(p)
                        if v > max_qlen:
                            max_qlen = v
                            max_line = line
                        break
                    except ValueError:
                        continue
            print(f"  max qlen observed: {max_qlen:,}  in line: {max_line[:120]}")
    else:
        print("  qlen.txt missing")


if __name__ == "__main__":
    main()
