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

Pinned for reproducibility. All in the harnessit Cloud Langfuse project.

| Variant | Trace ID |
|---|---|
| symptom-only | `5db68836ac346eeeed9ac2c056528626` |
| with-topology | `bf204faa2834c54c5eef6cc207f72379` |
| with-topology-tool | `8c4399b12477966d8ca0ad3fb1a1323d` |

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
