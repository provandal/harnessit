# HarnessIT — Build Plan and Capture Protocol

**How we build the system, and how we capture what we learn while building it**

Draft v0.4 · provandal.dev

**Companion to:** HarnessIT Architecture Overview v0.6

**Supersedes:** v0.3 (2026-05-04). See `v0.4_updates.md` for the changelog.

---

## 1. The Premise of This Document

The HarnessIT architecture document defines what we are building (Architecture Overview v0.6). It does not say how we build it, in what order, what tier of completion is committed by when, or how we capture what we learn while building it. This document fills that gap.

It deliberately does not include a detailed editorial plan for the eventual blog series. Detailed editorial plans written before the build is complete are wrong in specific, unpredictable ways. They tend to either constrain the build (forcing reality to fit the planned narrative) or get thrown away when the build reveals things the plan did not anticipate. We will write the series after the build, when we know what actually happened.

What this document does instead is define three things, in order of fidelity:

- A high-fidelity build sequence for the order in which components get built and what is true at each tagged commit. Technical dependencies are real and worth getting right.
- A high-fidelity capture protocol for how the three of us — Erik, Claude (chat collaborator), and Claude Code (builder) — work together, and how we record what happens so we have material to write from later. The v0.3 reduction (eleven-plus rituals → three rules) held empirically through Stages 0–5; v0.4 keeps it intact.
- A low-fidelity, explicitly capture-only editorial scaffold with rough thematic groupings. Publishing shape itself remains deferred.

Build first. Capture while building. Decide publishing form when running code makes the right form obvious.

**v0.4 publishes after the 60-day Tier 0 target (Stage 5, First Skill) has been hit empirically — see §2.1.** It refreshes the stage map with what actually shipped 2026-05-04 → 2026-05-12, documents three Stage 5-era methodological findings worth carrying forward (matrix-driven tool-coverage audit, operational-stance correctness grading, k≥3-runs-per-cell skill A/B), and points the program at the N₁ tier target (Stage 8, CSM and Screen Capture). Capture protocol unchanged from v0.3.

---

## 2. Build Sequence

### 2.0 Tier Targets — Status

**Plan-of-record (v0.4):**

- **60 days — Tier 0 (bottom). N₀ = Stage 5, First Skill. ✅ HIT (2026-05-12).** The Calibrated Commitment skill v0.2 delivers +33pp correctness, +42pp rubric pass rate, and +65pp structural commitment over baseline across four §5.2 fault classes under the post-step-3 4-tool surface, measured at k=3 per cell. Stage 5b's purpose — demonstrate skill-mediated diagnostic improvement is real and measurable — is achieved. See `project_stage5b_skill_ab_2026_05_12.md` for full A/B + variance pass results.
- **4 months — Tier 1 (mid). N₁ = Stage 8, CSM and Screen Capture.** Stages 6 (retrieval) and 7 (memory) absorbed along the way. Stage 6 is the next-immediate work after the v0.4 publication window.
- **12 months — Tier 2 (top). N₂ = Stage 13, AIR Adapter.** Stages 9–12 absorbed along the way.

**N₀ closure note (2026-05-12).** Stage 5 closed two days after Stage 4 (2026-05-07) and the §5.2 fault-class sweep (2026-05-11). The matrix-driven foundation plan that ran 2026-05-11/12 — diagnosis_correctness LLM axis (step 1), tool-coverage closure (step 2: `get_flow_records`, intended.txt cross-reference, sport leak fix, host-ingress PhyRxDrop instrumentation, `get_host_counters`, session-level run cache), and substrate-fidelity audit (step 3: microburst retracted, silent-drops retracted, hash-polarization parameter bump) — was load-bearing for the Stage 5b result. Each step was empirically motivated and falsifiable. The matrix-as-methodology pattern itself is worth carrying into Stage 6+: when a stage's premise needs verifying, build the §-fault-class × tool-surface coverage table and audit it.

**Partial completion is an honest report, not failure** (unchanged from v0.3). The 60-day target hit at the original-budget date because the substrate-fork spike's velocity datapoint generalized: 2026-05-02's "Day 1 success" foreshadowed 2026-05-07's Stage 3 closure and 2026-05-12's Stage 5 closure. Future tier-target dates may or may not hold the same compression; v0.4 keeps the same "honest report at the date" stance.

### 2.1 Stage Map

Stages 0–5 are closed as of v0.4 publication. Stages 6–13 are forward work. The structure is unchanged from v0.3; status reflects 2026-05-12.

| Stage | Name | Status | Tier |
|---|---|---|---|
| 0 | Foundations | ✅ Closed 2026-05-05 | 0 |
| 1 | Doppelgänger v0.1 | ✅ Closed 2026-05-05 (substantially) → 2026-05-12 (substrate fidelity audit) | 0 |
| 2 | Naked model + Langfuse + first eval | ✅ Closed 2026-05-06 | 0 |
| 3 | Tool surface | ✅ Closed 2026-05-07 → 2026-05-12 (tool-coverage closure to 4 agent-facing tools) | 0 |
| 4 | Trajectory viewer v0.1 + Langfuse self-host transition | ✅ Closed 2026-05-07 (4a viewer + 4b self-host) | 0 |
| 5 | First skill (Tier 0 target — N₀) | ✅ **HIT 2026-05-12** | 0 |
| 6 | Retrieval | ⏳ NEXT | 1 |
| 7 | Memory via RememberIT | ⏳ Forward | 1 |
| 8 | CSM and screen capture (Tier 1 target — N₁) | ⏳ Forward | 1 |
| 9 | Orchestration: three patterns | ⏳ Forward | 2 |
| 10 | Multi-agent readiness | ⏳ Forward | 2 |
| 11 | Security and guardrails | ⏳ Forward | 2 |
| 12 | Eval dashboard + kickoff panel | ⏳ Forward | 2 |
| 13 | AIR Adapter (Tier 2 target — N₂) | ⏳ Forward | 2 |

#### What each closed stage actually shipped

These are honest field reports — what landed, what diverged from the v0.3 stage description.

**Stage 0 (closed 2026-05-05).** Five repos + initial commits, Langfuse Cloud project provisioned, RememberIT context provisioned, design docs in canonical .md form (v0.5/v0.3/v0.2). One v0.3 commitment was retracted: IBTA RoCEv2 Annex access moved from "obtain via membership" to "citation-only" (the v0.5 corpus uses Linux kernel + rdma-core + Wireshark dissector as primary RoCEv2 semantic source; IBTA spec is a citation pointer). No membership required.

**Stage 1 (closed 2026-05-05 → 2026-05-12).** Driver + Adapter pair shipped per Doppelgänger v0.2 §9.1. **5/7 §5.2 failure classes** end-to-end (originally targeted ≥3): silent drops, microburst, PFC storm (reframed as ECN-misconfig diagnostic), asymmetric path, hash polarization. **2/7 deferred** on substrate gaps: link flap (substrate parses LINK_DOWN but never schedules NetDevice::SetDown), buffer misconfig (substrate has global BUFFER_SIZE only, no per-switch override). Substrate fork commits (`4dd55d8 → 1a7b9d0`) closed multiple trace-output gaps (pfc.txt, mix.tr, qlen.txt empty-file root cause); added EcnMark trace source + ecn.txt; added per-port counter rollup + counters.txt; added SONiC-shaped per-(switch, port, queue) counters with PG watermarks and per-priority PFC; added intended-flow trace (intended.txt) for §4.2 incomplete-flow surfacing; added host-ingress PhyRxDrop instrumentation (host_counters.txt). 2026-05-12 substrate-fidelity audit narrowed Step 3 of the foundation plan to one fix: bumped `hash_polarization()` `repetitions_per_pair` from 4 to 32 to produce visibly bimodal FCT.

**Stage 2 (closed 2026-05-06).** Naked Opus 4.7 + Langfuse v4 + first eval ran end-to-end against the real substrate. Eval-discipline reshape: v1 scenario leaked the answer key (compare_runs output in user prompt); v2 reshape (microburst-with-topology vs symptom-only) showed the delta empirically. The reshape happened same-day in response to a four-reviewer pressure test critique. Build-plan implication: eval-discipline pressure-testing should happen at every stage, not just stage 2.

**Stage 3 (closed 2026-05-07 → 2026-05-12).** Started as one tool (`get_topology`) per v0.3 minimum-viable approach. Closed at v0.3 publication with 5-criterion LLM judge rubric (keyword scorer hit a noise floor of ~2 criteria; LLM judge produces structured rationale per criterion). 2026-05-12 expanded the agent-facing tool surface from 2 to 4 tools (added `get_flow_records` per Doppelgänger §4.2 closure, `get_host_counters` for host-ingress PHY drop signal). Now also includes a **session-level run cache**: the Driver checks for a complete set of substrate output files in `trace_dir` and short-circuits to parse-from-disk if present. The runner threads `target_run_id` through every agent tool call so substrate runs per eval session drop from N+1 to 1 — both a performance win and a correctness fix (stochastic scenarios produced decorrelated data across independent runs).

**Stage 4 (closed 2026-05-07).** Split into 4a (trajectory viewer v0.1) + 4b (self-hosted Langfuse). 4a ships `harnessit.viewer` as static HTML + Mermaid.js sequence diagrams, services-as-columns. 4b ships a six-service docker-compose stack pinned by tag + sha256 digest (Postgres, ClickHouse, Redis, MinIO, Langfuse web, Langfuse worker). Substrate-substitution property empirically verified by flipping `.langfuse-credentials` between Cloud and self-hosted and re-rendering identical trace IDs. **Architecture-doc drift discovered**: v0.5 §9.1 says Langfuse needs OTel collector; reality is MinIO (Langfuse v3 ingests via its own SDK, not OTLP). Reconciled in v0.6 architecture §9.1.

**Stage 5 (closed 2026-05-12).** First skill (Calibrated Commitment, v0.2) shipped at `harnessit/src/harnessit/skills/calibrated_commitment.py`. CLI accepts `--skill <name>`. EvalScenario gains `skills: tuple[Skill, ...]` field; runner appends skill bodies to system_prompt. Scoring stack grew to **three axes**: keyword + LLM rubric (triage quality, 5 criteria from Stage 3); diagnosis_correctness LLM judge (operational-stance grading, added Stage 5b step 1); structured_commitment deterministic scorer (6-axis substring scorer for the skill's mandated structure). Per-trace OTel spans for each axis. v0.2 of the skill validated at k=3 per cell across 4 fault classes: +33pp correctness, +42pp rubric, +65pp structural commitment over baseline. One scenario (silent-drops) remains 1/3 correct even with skill — deferred to v0.3 of the skill or a substrate-side intervention (derived drops-per-million counter).

### 2.2 Forward Stages — Brief Re-statements

For Stages 6–13 the v0.3 scope language still applies. Two stages get explicit notes from Stage 5 learnings:

**Stage 6 (Retrieval).** Starter corpus seed list is the five-document v0.5 baseline (RFCs 3168/8087, IBTA RoCEv2 Annex citation-only, NVIDIA Cumulus and Arista RoCE guides). Hybrid retrieval / reranking / query rewriting all defer to v0.6+/stage-6+ unchanged. New Stage 5-era input: the tool-coverage-matrix methodology generalizes — Stage 6's "is retrieval useful here" question is empirical and falsifiable per fault class. Plan to build a `§5.2 fault-class × retrieval-utility` matrix as part of Stage 6 audit work.

**Stage 8 (CSM + screen capture, Tier 1 target — N₁).** Unchanged in scope. Methodology carry-over from Stage 5: skill A/B and any future eval comparisons use k≥3 per cell by default — single-trace conclusions on skill effects are unreliable per the 2026-05-12 Stage 5b variance pass.

### 2.3 What This Sequence Does Not Promise

Unchanged from v0.3. Three caveats: stages take variable time; some stages produce a v0.1 that gets rebuilt; no per-stage publishing commitment.

### 2.4 Stage Mapping: Build Plan ↔ Architecture

Unchanged from v0.3. The mapping table at v0.3 §2.4 is canonical; v0.6 architecture's §11 (editorial stages) maps onto it.

---

## 3. Capture Protocol

Three rules and one informal practice. **Unchanged from v0.3 — held empirically through Stages 0–5.** The pressure test that motivated v0.3's reduction (2026-05-01 four-reviewer review) predicted v0.2's eleven-plus rituals would collapse by stage 5; v0.3's three-rule core (WHY blocks, journal, STATUS) ran clean through actual Stage 5 closure. No additions needed.

One small clarification carried in from practice: **the trajectory viewer render belongs in the post-eval-run checklist alongside the journal entry.** A 2026-05-12 workflow gap (no new `viewer/examples/*.html` between 2026-05-10 and 2026-05-12, coinciding with the self-hosted Langfuse transition) showed that viewer rendering can drift if it's not part of the routine. The fix is procedural, not structural: after running a substantive eval, `python -m harnessit.viewer <trace_id> --output viewer/examples/<name>.html`. The viewer module itself works against both managed and self-hosted Langfuse.

### 3.1 The Three-Way Collaboration

Unchanged from v0.3 §3.1.

### 3.2 The Three Rules

Unchanged from v0.3 §3.2. (Rule 1: WHY blocks in non-trivial commits. Rule 2: workspace-level `journal.md` append-only. Rule 3: workspace-level `STATUS.md` updated on situation changes.)

### 3.3 Architecture Decision Records (ADRs), Emergent-Only

Unchanged from v0.3 §3.3.

### 3.4 What v0.4 Adds (Methodology Carry-overs)

Three Stage 5-era findings worth carrying into Stages 6+ as methodology:

**Methodology 1: Matrix-driven coverage audit.** When a stage's premise depends on the agent having a path through the toolset to a diagnostic signature, build the fault-class × tool-surface coverage table and audit it BEFORE designing skills or scoring axes. The 2026-05-11 sweep showed that "rubric ≠ correctness" wasn't a rubric flaw — it was a tool-coverage gap (silent-drops needed FCT records; substrate had them but the agent couldn't query them). The matrix made the gap concrete and produced a falsifiable claim ("after these N tools land, every fault class has a path"). Generalizable beyond §5.2: any Stage X premise that depends on agent capability over a fault class deserves a coverage audit.

**Methodology 2: Operational-stance grading > strict verdict-string matching.** The 2026-05-12 v0.1 skill A/B looked like a correctness regression under strict verdict-matching but mostly dissolved under operational grading ("would an SRE following this advice reach the right fault class?"). The strict grader missed two cases where the agent's verification/recommendation steps WOULD lead to the right answer despite an over-specific or non-committal verdict. v0.2 of the correctness judge ships operational grading. Carry into Stage 6+: any LLM-judge axis that grades the agent's *output* should evaluate operational consequences, not surface form.

**Methodology 3: k≥3 runs per cell for skill A/B.** Single-trace skill comparisons surfaced spurious "regressions" in the 2026-05-12 v0.1 A/B that disappeared at k=3. The variance pass (k=3 × 4 scenarios × 2 conditions) made the skill's actual effect legible: +33pp correctness, +42pp rubric, +65pp structure. Carry into any future skill or eval comparison: a single trace is preliminary; production-quality conclusions require k≥3, and the session-level run cache makes this affordable. Future stages comparing skills (Stage 7+, possibly Stage 9 orchestration patterns) should budget for k≥3 by default.

These three are not new capture protocols — they're methodology for how the build measures itself. They live in v0.4 because they emerged from Stage 5 and apply to every subsequent stage that compares agent behavior across conditions.

### 3.5 What v0.3 Already Dropped — and Why It Stayed Dropped

The list of items v0.3 dropped from v0.2 (per-section consolidation passes, summary files, reframing markers, "this matters" tagging, decision-summary rituals, weekly journal harvests, voice notes, two-context RememberIT structure, numeric ADR budget) held through Stages 0–5 without regret. No re-adoption candidates surfaced. The shape of work the v0.3 protocol expects — WHY blocks in git history, journal entries per session, STATUS overwritten in place, ADRs when load-bearing — produced grep-able material in flat files. Writing the eventual series will be editorial work, not reconstruction.

---

## 4. Provisional Editorial Sketch (Capture-Only Scaffold)

**Unchanged from v0.3.** Publishing shape remains deferred. The six-act capture-guidance hypothesis is retained as a grouping aid for the journal. No changes to §4.1, §4.2, §4.3 from v0.3.

Three reasons the sketch is still useful even though it will change (unchanged from v0.3 §4.2): it shapes capture, catches gaps early, invites reframing.

---

## 5. Closing

Tier 0 hit. Tier 1 is the forward window. The build sequence (§2.1) tells us what's closed and what's next. The capture protocol (§3) held through 60 days of intense build. The methodology carry-overs in §3.4 are the durable extractions from the Stage 5 era — matrix-driven coverage audits, operational-stance grading, k≥3 per-cell skill A/B — and they apply to every stage that follows.

Build Plan v0.4 publishes alongside Architecture v0.6 and Doppelgänger Design v0.3. The companion update memos (`v0.4_updates.md`, `v0.6_updates.md`, `v0.3_updates.md`) document the changelog for each.

The plan is the scaffold. The journal is the truth. (Journal at `<workspace>/journal.md`; position report at `<workspace>/STATUS.md`. Both referenced from §3.)
