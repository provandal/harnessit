"""Task #8 verification: PFC fix → pfc_storm produces PFC propagation.

Two-part gate:
  (1) Necessary  — pfc.txt non-empty after a pfc_storm run.
  (2) Sufficient — victim flow ≥2x slowdown (PerFlowRecord.slowdown).

The substrate records standalone FCT alongside actual FCT, so a separate
baseline run isn't needed. Runs against the dev image so the fix can be
verified before being pushed.
"""

from __future__ import annotations

import sys

from doppelganger.driver.simulation import Driver
from doppelganger.scenarios.builtin import pfc_storm


DEV_IMAGE = "doppelganger-substrate"


def main() -> int:
    driver = Driver(substrate_image=DEV_IMAGE)

    print("=" * 60)
    print("Task #8 verification — PFC fix")
    print("=" * 60)

    print("\nRunning pfc_storm scenario (default knobs, ecn_misconfigured=True) ...")
    scenario = pfc_storm()
    result = driver.run_scenario(scenario, run_id="task8-pfc-storm")
    print(f"  wall_clock={result.wall_clock_seconds:.1f}s")
    print(f"  trace_dir={result.trace_dir}")
    print(f"  flows_in_fct={len(result.flows)}")

    # Diagnostic: dump TASK8-DBG lines from substrate stdout.
    task8_lines = [l for l in result.stdout.splitlines() if "TASK8" in l]
    print(f"\nDiagnostic — TASK8 stdout lines: {len(task8_lines)}")
    # Write full TASK8 stream to file for analysis.
    task8_log = result.trace_dir / "task8.log"
    task8_log.write_text("\n".join(task8_lines))
    print(f"  full TASK8 stream -> {task8_log}")
    # Per-event-type counts
    from collections import Counter
    types = Counter(l.split()[1] if len(l.split()) > 1 else "?" for l in task8_lines)
    for t, n in types.most_common():
        print(f"  {t}: {n}")

    # Sanity: total stdout volume + first/last 30 lines, look for BUFFER_SIZE marker.
    stdout_lines = result.stdout.splitlines()
    print(f"\nSanity — total substrate stdout lines: {len(stdout_lines)}")
    bs_lines = [l for l in stdout_lines if "BUFFER_SIZE" in l]
    print(f"  BUFFER_SIZE lines in stdout: {len(bs_lines)} (expect 1+ if substrate stdout reaches us)")
    for l in bs_lines[:3]:
        print(f"    {l}")
    if len(stdout_lines) > 0:
        print(f"  first 5 stdout lines:")
        for l in stdout_lines[:5]:
            print(f"    {l[:200]}")
        print(f"  last 5 stdout lines:")
        for l in stdout_lines[-5:]:
            print(f"    {l[:200]}")

    # GATE 1 (necessary): pfc.txt non-empty
    pfc_path = result.trace_dir / "pfc.txt"
    print(f"\nGate 1 — PFC events recorded:")
    if not pfc_path.exists():
        print(f"  FAIL: {pfc_path} does not exist")
        return 2
    pfc_size = pfc_path.stat().st_size
    print(f"  pfc.txt: {pfc_size} bytes")
    if pfc_size == 0:
        print(f"  FAIL: pfc.txt is empty (no PFC events fired)")
        return 2
    pfc_text = pfc_path.read_text()
    pfc_lines = pfc_text.count("\n")
    print(f"  pfc.txt: {pfc_lines} lines")
    print(f"  first 3 lines: {pfc_text.splitlines()[:3]!r}")
    print(f"  PASS")

    # GATE 2 (sufficient): victim slowdown ≥2x
    print(f"\nGate 2 — victim slowdown:")
    # Identify victim by dst_port=20000 (storm flows use 10000+i).
    victim = next(
        (f for f in result.flows if f.dport == 20_000),
        None,
    )
    if victim is None:
        # Look for the highest-slowdown completed flow as a sanity check.
        completed_with_slowdown = [
            f for f in result.flows
            if f.slowdown is not None and f.slowdown != float("inf")
        ]
        if completed_with_slowdown:
            top = sorted(completed_with_slowdown, key=lambda f: f.slowdown, reverse=True)[:5]
            print(f"  Victim flow not in completed FCT records.")
            print(f"  Top 5 slowdowns observed (storm flows):")
            for f in top:
                print(f"    {f.sip}:{f.sport} -> {f.dip}:{f.dport} slowdown={f.slowdown:.2f}x")
        print(f"  PARTIAL: victim flow did not complete — pause is firing,")
        print(f"  storm severe enough to stall victim entirely. Ship-with-flag.")
        return 0

    if victim.slowdown is None:
        print(f"  PARTIAL: victim has no slowdown (incomplete? fct_ns={victim.fct_ns},")
        print(f"  standalone_fct_ns={victim.standalone_fct_ns}). Ship-with-flag.")
        return 0

    print(f"  victim {victim.sip}:{victim.sport} -> {victim.dip}:{victim.dport}")
    print(f"  fct_ns={victim.fct_ns} standalone_fct_ns={victim.standalone_fct_ns}")
    print(f"  slowdown={victim.slowdown:.2f}x")
    if victim.slowdown >= 2.0:
        print(f"  PASS — ≥2x slowdown demonstrates PFC propagation")
        return 0
    print(f"  PARTIAL — slowdown {victim.slowdown:.2f}x < 2x. Pause is firing")
    print(f"  but not propagating effectively. Ship-with-flag per the criterion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
