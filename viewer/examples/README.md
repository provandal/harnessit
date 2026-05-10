# Stage 3 Closing-Test Trajectory Examples

Three rendered trajectory views from the HarnessIT Stage 3 closing-test
calibration on **2026-05-07**. They are committed snapshots of live
[Langfuse](https://langfuse.com) traces captured at the close of Stage 3
in the HarnessIT build sequence (Build Plan v0.3 §2.1). Each one shows
the same underlying fault — a network microburst onto host `11.0.0.1`
— investigated under three different harness configurations.

The three side-by-side make the harness's contribution legible at a
glance: the `with-topology-tool` variant has a *Tool lane* and an
extra `Agent → Tool → Agent` round-trip the other two don't.

## The Three Variants

All three start from the same help-ticket prompt to the agent:

> "Hey network team — step time on jobs targeting host 11.0.0.1 is up
> about 1.5x compared to baseline. Started this morning around 09:14
> UTC. Can you help figure out what's going on?"

What differs is how (or whether) the agent gets at fabric context.

| File | Variant | Context source | Tool calls | LLM judge verdict |
|---|---|---|---|---|
| [`microburst-symptom-only.html`](microburst-symptom-only.html) | Bare ticket | None | 0 | **FAIL** (4/5 — fails synthesis) |
| [`microburst-with-topology.html`](microburst-with-topology.html) | Prompt-fed | Topology preamble in user prompt | 0 | **PASS** (5/5) |
| [`microburst-with-topology-tool.html`](microburst-with-topology-tool.html) | Tool-mediated | `get_topology` tool | 1 | **PASS** (5/5) |

Open any of them in a browser. The files are self-contained — Mermaid.js
loads from CDN at view time; no server required.

## What Each File Shows

Each rendered HTML page contains:

1. **Header** — scenario name, trace ID, scoring mode (`llm_judge`),
   target run id, and the eval-run timestamp.
2. **Sequence diagram** — services-as-columns (User / Agent / Tool /
   Judge), time flowing down. Solid arrows are requests; dashed
   arrows are responses. Only active lanes render — no empty
   columns.
3. **Trace-level scores** — the eval's overall pass/fail score with
   the LLM judge's overall rationale.
4. **LLM judge per-criterion rationale** — five criteria
   (multi-hypothesis, telemetry, unknowns, ordering, synthesis) each
   with PASS/FAIL and a citation-of-specific-phrases rationale.
5. **Per-message details** — collapsible blocks with the full
   payload of each message (input, output, envelope metadata).

## The Pedagogical Signal

The point of Stage 3's closing test was to demonstrate that **the
harness adds a capability the LLM doesn't have alone when fabric
context is missing**. Read the three files in order and notice the
diagram structure:

- **Symptom-only**: the agent has nothing to integrate, so it asks
  the user clarifying questions ("What leaf is 11.0.0.1 attached
  to?") rather than reasoning about specifics. The LLM judge fails
  it on `synthesizes_available_context` — there's no context to
  synthesize. The flow is just User → Agent → User → Judge.

- **With-topology**: the agent has a topology preamble pre-loaded in
  the user prompt. It synthesizes via the prompt-fed context — names
  specific link speeds, reasons about leaf-host bottleneck dynamics.
  Same diagram shape as symptom-only (no Tool lane); the synthesis
  comes from the prompt.

- **With-topology-tool**: the agent has *no* topology preamble in
  its user prompt — the user prompt is identical to symptom-only.
  But it has the `get_topology` tool. It calls the tool, retrieves
  the fabric structure, then synthesizes ("Substrate ID 0, attached
  to leaf 0 (node 16)... asymmetry.present = false ... the cause is
  most likely *dynamic* rather than structural"). The diagram shows
  the extra `Agent → Tool → Agent` round-trip. The harness's
  contribution is visible mechanically.

The LLM judge's rationale on the three traces backs this up
— the synthesis criterion is the discriminating one, and the
with-tool variant's synthesis cites concrete entities from the
tool's response payload (which you can see expanded in the
collapsible message details).

## Reproducing These Files

The traces themselves live in the Langfuse Cloud project this build
publishes to. To re-render any of them (with project credentials
configured at `<workspace-root>/.langfuse-credentials`):

```bash
cd harnessit
python -m harnessit.viewer 5db68836ac346eeeed9ac2c056528626 \
    --output viewer/examples/microburst-symptom-only.html
python -m harnessit.viewer bf204faa2834c54c5eef6cc207f72379 \
    --output viewer/examples/microburst-with-topology.html
python -m harnessit.viewer 8c4399b12477966d8ca0ad3fb1a1323d \
    --output viewer/examples/microburst-with-topology-tool.html
```

To run a *new* eval and render its trace:

```bash
# Run the eval (writes a new trace to Langfuse, prints trace_id)
python -m harnessit microburst-with-topology-tool

# Render that trace
python -m harnessit.viewer <trace_id_from_output> --output trace.html
```

## Trace IDs

Pinned for reproducibility. Stage 3 traces live in the Cloud Langfuse
project; the Stage 5a trace lives on the self-hosted Langfuse stack.

| Variant | Trace ID | Backend |
|---|---|---|
| symptom-only | `5db68836ac346eeeed9ac2c056528626` | Cloud |
| with-topology | `bf204faa2834c54c5eef6cc207f72379` | Cloud |
| with-topology-tool | `8c4399b12477966d8ca0ad3fb1a1323d` | Cloud |
| pfc-storm-with-counters-tool | `668a11072f2a9d51814ce55841fca6ef` | Self-hosted |
| pfc-storm-realistic-with-counters-tool | `3ef43138e182c9c84d41f35cc9a353b0` | Self-hosted |
| pfc-storm-realistic-with-counters-tool (SONiC + leak fix) | `c9d82a9829daf2b9e714efe09281206c` | Self-hosted |

## Stage 5a Closing Test (2026-05-08)

[`pfc-storm-with-counters-tool.html`](pfc-storm-with-counters-tool.html)
is the closing-test artifact for **Stage 5a (counters tool)**. The
underlying fault is `pfc_storm(ecn_misconfigured=True)` — KMIN raised
above buffer capacity so DCQCN runs blind, queues build past PFC
headroom, pause frames fire while ECN-CN counters stay at zero. The
agent has both `get_topology` and `get_fabric_counters` available but
no skill loaded.

**Surprise.** Naked Opus 4.7 with both tools nailed the diagnosis
without any skill: it called the tools, observed the PFC/ECN
asymmetry directly from per-port records ("8,288 pauses and 0 marks"),
proposed the correct root-cause class (ECN/WRED threshold raised
above PFC xoff, or marking disabled on the queue), localized leaf 0
as the storm source, and outlined a verification rollback plan.
**The asymmetry-recognition is already in the model.**

The LLM judge still verdicts FAIL — but on different criteria than
the diagnosis itself: the agent fails on hypothesis breadth (locks
in on "ECN misconfig" without weighing incast, ECMP, host-side, or
link-degradation alternatives) and on acknowledging unknowns
(opens with "Found it." — no hedging, no clarifying questions, no
named data gaps). It passes on telemetry specificity, investigation
ordering, and context synthesis.

The implication for the upcoming first skill (Stage 5b) is sharper
than the original framing: the skill cannot be "teach the agent to
read PFC + ECN-CN asymmetry" — Opus 4.7 already does that. The
useful skill is *epistemic discipline*: enumerate alternative
hypotheses, name telemetry breadth, hedge confidently, propose
falsification. That's procedural knowledge the model benefits from
even though it has the domain-specific recognition.

**Caveat: leak vector still present.** The closing-test fabric is
4 leaves × 1 spine × 4 hosts/leaf with only the storm running. The
counter payload contains 2 active ports of activity — no background
traffic, no production-shaped baseline. A more realistic test
(in-progress, "Stage 5a-realistic") will add background flows and
expand the counter set (rx/tx bytes, drops, queue depth, etc.) so
the asymmetry is *relative* rather than *absolute*. The current
closing-test artifact is honest about this constraint; the next
iteration will check whether the diagnosis holds under
production-shaped complexity.

## Stage 5a-realistic Closing Test (2026-05-09)

[`pfc-storm-realistic-with-counters-tool.html`](pfc-storm-realistic-with-counters-tool.html)
is the closing-test artifact for **Stage 5a-realistic** — same fault
class as Stage 5a but on a production-shaped fabric. Three substrate +
Doppelgänger lifts shipped between 2026-05-08 and 2026-05-09:

1. Substrate adds a per-port end-of-sim counter rollup
   (`counters.txt`) carrying rx/tx packets+bytes, drops, and
   `qlen_peak_bytes` for every switch port that saw activity.
2. Doppelgänger's `aggregate_counters` becomes topology-aware: every
   switch port the topology declares appears in the response, zero-filled
   when no events fired. The agent must find the storm port among
   (e.g. for the default 4×1×4 topology) ~24 enumerated ports.
3. `pfc_storm()` adds layered cross-leaf background traffic via
   `background_pairs_per_leaf`; the new `pfc-storm-realistic` factory
   calls it with 2 pairs/leaf so the fabric baseline shows volumetric
   activity on ≥8 distinct ports under healthy ECN config.

**Result: naked Opus 4.7 still nails the diagnosis.** Trace
`3ef43138e182c9c84d41f35cc9a353b0`. The agent identified the storm port
*precisely* (`Leaf 0 (node 16), if_index 5` — the leaf's uplink to the
spine) and the corresponding spine ingress (`Spine (node 20), if_index
1`), used the `qlen_peak_bytes` field from the new counter set to spot
the ~270× depth disparity (684 KB on the storm spine port vs ~2.5 KB
on its siblings), framed the pause/resume symmetry correctly
("pause/resume counts are equal — this isn't a stuck/deadlocked PFC;
it's repeated pause-resume cycling"), proposed the correct root cause
class ("set the PFC threshold below the ECN/WRED marking threshold"),
hedged on platform-specific values, and outlined a falsification
rollback. The qlen_peak signal is *load-bearing* in this response — it
didn't appear in the Stage 5a (toy) closing test because the counter
set didn't include it. Adding the volumetric fields strengthened the
diagnosis rather than hiding it.

The judge verdict matches Stage 5a in shape: FAIL on
`considers_multiple_hypotheses` (still locks in on a single root cause
without weighing incast, ECMP imbalance, NIC/host issues, cable
degradation as alternatives), PASS on every other criterion. One
material change from Stage 5a: `acknowledges_unknowns` flips PASS in
the realistic case — the agent uses hedging language ("almost
certainly", "may have been disabled", "exact numbers depend on
platform") it didn't reach for in the toy scenario.

**The Stage 5a finding is confirmed under realism**: Stage 5b's first
skill is *epistemic discipline*, not RoCE-specific recognition. The
asymmetry-detection capability is in the model. The proactive
enumeration of alternative mechanism classes is the procedural gap.

## Stage 5a SONiC counter expansion + leak fix (2026-05-10)

[`pfc-storm-realistic-with-counters-tool-sonic.html`](pfc-storm-realistic-with-counters-tool-sonic.html)
re-runs the same scenario after two corrections Erik flagged on the
2026-05-09 trace:

1. **Scenario-name leak plugged.** The 2026-05-09 trace caught the
   agent literally quoting "Scenario tag in the counter dump literally
   reads `pfc-storm-16h`" — both the `"scenario"` data field and the
   embedded trace_dir path leaked the answer key. Fix: drop the
   `scenario` field from `get_fabric_counters` and `run_scenario`
   responses; switch Driver auto-generated `run_id` from
   `f"{scenario_name}-{ts}"` to `f"run-{uuid}"`; switch HarnessIT's
   `_default_run_id_prefix` to a matching UUID pattern. Defense in
   depth — every layer that builds a run_id avoids the scenario name.

2. **Counter set rebuilt to align with SONiC's per-port operator surface.**
   The previous 6-field per-port shape (rx/tx packets+bytes, drops,
   qlen_peak) was too lightweight relative to what SONiC's
   `show queue counters` + `show queue watermark` +
   `show priority-group watermark` + `show pfc counters` actually
   show. Substrate adds a per-priority `QbbPfcQ` trace, extends
   pfc.txt to 6 columns (with qIndex), and rebuilds counters.txt as
   per-(switch, port, queue) rows with a new `pg_watermark_bytes`
   column populated by a periodic sampler walking each switch MMU's
   `egress_bytes`/`ingress_bytes` arrays. Doppelgänger reshapes the
   response: each port carries interface state (oper/admin/speed/mtu)
   plus a `queues: [...]` array of 8 per-priority records (each with
   rx/tx packets+bytes, dropped_packets, qlen_peak_bytes,
   pg_watermark_bytes, all four PFC variants, ecn_marks_sent).
   **Aggregates across queues are deliberately omitted** — Erik's
   call (2026-05-10): pre-aggregating counts is itself a
   tool-mediated convenience and forcing the agent to sum queues
   itself preserves naked-LLM measurement integrity for Stage 5b. For
   the default 4-leaf 1-spine 4-host topology that's 24 enumerated
   ports × 8 queues = 192 queue records per response.

**Result: verdict shape flipped on the same scenario.** Trace
`c9d82a9829daf2b9e714efe09281206c`. Naked Opus 4.7 still nails the
diagnosis — but where the 2026-05-09 trace had FAIL on
`considers_multiple_hypotheses` and PASS on `acknowledges_unknowns`,
the 2026-05-10 SONiC trace inverts: PASS on
`considers_multiple_hypotheses` (agent explicitly rules out path
asymmetry, slow links, and wiring issues by reading the topology +
per-queue counter set), FAIL on `acknowledges_unknowns` (high-confidence
single-root-cause assertion without hedging or proposed verification).

The agent's response cites "queue 3" (the lossless RoCE priority)
repeatedly, reads both watermark classes (egress `qlen_peak_bytes`
vs ingress `pg_watermark_bytes`) as separate signals, identifies the
storm port to leaf+if_index granularity (`leaf 16 port 5 = uplink to
spine`, ECN marks zero everywhere across 24 ports × 8 queues), and
explains the per-priority isolation. Zero references to "pfc-storm"
anywhere in the response — leak confirmed plugged.

**Counter-intuitive finding**: the richer telemetry made the diagnosis
*tighter*, not more uncertain. With 192 queue records the agent had
enough evidence to rule out alternatives confidently — passing
multi-hyp by elimination rather than by hedging. **This sharpens
Stage 5b's skill thesis further**: not "enumerate alternatives"
(rich enough data + naked model already does that) but "calibrate
confidence to the underlying evidence quality even when evidence is
overwhelming." The first skill now reads as *Confidence Calibration*:
after naming a root cause, state the strongest supporting evidence,
name the single observation that would falsify it, propose a fallback
diagnosis, hedge platform-specific values explicitly.

## File Sizes

Static HTML, Mermaid.js loaded from CDN at view time, no other assets.

| File | Size |
|---|---|
| `microburst-symptom-only.html` | ~14 KB |
| `microburst-with-topology.html` | ~16 KB |
| `microburst-with-topology-tool.html` | ~18 KB |

The `with-tool` file is largest because it carries the extra
tool-result payload (the structured topology data the agent
retrieved) in addition to the agent's response and the judge's
rationale.

## Stage 3 Build Plan Reference

These artifacts close Build Plan v0.3 §2.1 stage 3 ("Tool surface").
The trajectory viewer that produced them is Stage 4a (the v0.1
trajectory viewer per Architecture v0.5 §11). See the workspace-level
`journal.md` for the full Stage 3 + Stage 4a development arc, including
the rubric-revision episode that surfaced the
`synthesizes_available_context` criterion.
