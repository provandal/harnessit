# HarnessIT — Build Plan and Capture Protocol

**How we build the system, and how we capture what we learn while building it**

Draft v0.3 · provandal.dev

**Companion to:** HarnessIT Architecture Overview v0.5

---

## 1. The Premise of This Document

The HarnessIT architecture document defines what we are building (Architecture Overview v0.5). It does not say how we build it, in what order, what tier of completion is committed by when, or how we capture what we learn while building it. This document fills that gap.

It deliberately does not include a detailed editorial plan for the eventual blog series. Detailed editorial plans written before the build is complete are wrong in specific, unpredictable ways. They tend to either constrain the build (forcing reality to fit the planned narrative) or get thrown away when the build reveals things the plan did not anticipate. We will write the series after the build, when we know what actually happened.

What this document does instead is define three things, in order of fidelity:

- A high-fidelity build sequence for the order in which components get built and what is true at each tagged commit. Technical dependencies are real and worth getting right.
- A high-fidelity capture protocol for how the three of us — Erik, Claude (chat collaborator), and Claude Code (builder) — work together, and how we record what happens so we have material to write from later. v0.3 reduces this section dramatically; the four-reviewer pressure test on 2026-05-01 found that v0.2's eleven-plus capture rituals would predictably collapse by stage 5, and v0.3 keeps only the load-bearing core.
- A low-fidelity, explicitly capture-only editorial scaffold with rough thematic groupings. v0.3 demotes this from "working hypothesis for the series" to "scaffold that guides what the journal pays attention to," because publishing shape itself is deferred entirely.

Build first. Capture while building. Decide publishing form when running code makes the right form obvious.

---

## 2. Build Sequence

### 2.0 Re-scope: 60-day / 4-month / 12-month Tiers

The original v0.2 build plan implicitly assumed a single timeline that would take HarnessIT through all 14 stages plus the eventual blog series. The 2026-05-01 four-reviewer pressure test independently estimated that timeline at 18–30 months realistic for one engineer with two stateless AI collaborators (synthesis §1.1) and ~3% probability of completion (Pragmatist's calibrated estimate). v0.3 adopts a re-scoped plan-of-record: three explicit completion tiers, each terminating at a *defined stage* in the §2.1 sequence, with partial completion treated as honest field reports rather than project failure.

**Plan-of-record:**

- **60 days — Tier 0 (bottom).** Working code at the bottom-tier stage *N₀ = Stage 5, First Skill*. By 60 days from the v0.3 publication date, the harness exercises its central idea end-to-end on a single substrate (Doppelgänger): tool surface (stage 3) + trajectory viewer (stage 4) + first skill loaded by the harness (stage 5), with eval scores measurable against the eval framework that exists from stage 2. Stage 0 (foundations) and stage 1 (Doppelgänger v0.1) are partially complete from work already done before v0.3 publishes (spike, repo bring-up, decision memos); they consume some of the 60-day budget but not all of it.
- **4 months — Tier 1 (mid).** Working code at the mid-tier stage *N₁ = Stage 8, CSM and Screen Capture*. The marquee build milestone for the architecture's most distinctive components: the agent compounds across sessions (memory), reasons about visual input (screen capture), and the working subset of context is actively managed (CSM). Stages 6 (retrieval) and 7 (memory) are absorbed along the way.
- **12 months — Tier 2 (top).** Working code at the top-tier stage *N₂ = Stage 13, AIR Adapter*. The credibility moment: HarnessIT runs against a real Cumulus fabric in NVIDIA AIR via the AIR Adapter (the project's second Substrate Adapter, see §2.1 stage 13), with the harness unchanged from how it ran against Doppelgänger. Stages 9–12 (orchestration, multi-agent readiness, security, eval dashboard / kickoff panel) are absorbed along the way.

**Why this tier choice.** The 60/4/12 tier compression of the Pragmatist's 90/6/18 proposal is informed by the 2026-05-02 fork-spike velocity datapoint (Day 1 success on `inet-tub/ns3-datacenter`; 5-minute cold builds; substantially compressed substrate-build risk) and by the project's stated learning-and-teaching-primary intent (the deliverable at each tier is *working code at stage N* plus *whatever is honestly capture-able from the journey*, not feature-complete-harness commitments).

**Why named stage targets, not vague tier descriptions.** v0.4 architecture and v0.2 build plan together provided no commitment about *what is true* at any tier-end date. Naming N₀, N₁, N₂ as specific stages gives every collaborator a falsifiable target: at 60 days, the question is "did we reach stage 5 with eval-measurable behavior" (yes/no), not "is the harness sufficiently along to call it tier 0" (handwave).

**Partial completion is an honest report, not failure.** Under learning-and-teaching-primary intent, the deliverable at each tier-end date is the working code that exists at that point plus whatever capture material has accumulated. If by 60 days the harness has only reached stage 4 (trajectory viewer) rather than stage 5 (first skill), the field report says so, names what was learned that slowed the trajectory, and updates the plan accordingly. The tier targets are commitments to honesty about progress, not commitments to ship-or-fail.

**Publication form for tier outcomes is deferred.** v0.3 does not commit to a per-tier blog post, a per-tier "Harness Illustrated" segment, or any other specific publishing form. The form will be chosen when running code makes the right form obvious. Capture (per §3) produces material that enables publication if/when the form decision lands.

### 2.1 Stage Map

HarnessIT is built in fourteen stages (0–13), scoped into three completion tiers per §2.0. Each stage produces something runnable. Each stage ends at a tagged commit that the next stage builds on. Stages are sequenced by technical dependency: nothing in a later stage requires anything that has not yet been built.

The sequence intentionally introduces eval discipline early (stage 2, not the end), so that every subsequent component change can be measured against it. This is a deviation from a naive "build everything, then add discipline" sequence, and it is deliberate. Discipline is cheaper to install early than to retrofit late.

| Stage | Name | What is true at the end of this stage | Tier |
|---|---|---|---|
| 0 | Foundations | Five GitHub repos exist with initial commits: `provandal/harnessit`, `provandal/doppelganger`, `provandal/theconstruct` (Apache-2.0); `provandal/ns3-datacenter` (GPL-2.0 fork of inet-tub, pinned at `4dd55d8…`). **Langfuse Cloud project provisioned** (free tier; project ID and API key documented in the workspace credential vault). Self-hosted Langfuse setup is deferred to stage 4 per Architecture v0.5 §9.1's staged-adoption framing. RememberIT context `harnessit-agent-memory` provisioned (the second context `harnessit-build-journal` was retired in v0.3 §3 in favor of workspace-level `journal.md`). Architecture document v0.5 published. Build plan v0.3 published. Doppelgänger design v0.2 published. Workspace-level `journal.md` and `STATUS.md` initialized. CONTRIBUTING files in each repo require DCO sign-off. License-boundary discipline (Doppelgänger Apache-2.0; substrate fork GPL-2.0; Docker image is mere aggregation under GPL §2) documented in `provandal/doppelganger/NOTICE`. **Substantially complete as of 2026-05-04**, the v0.3 publication date; remaining items are Langfuse Cloud project provisioning and corpus seed-list provisioning. | 0 |
| 1 | Doppelgänger v0.1 | The Doppelgänger Substrate Adapter exists as a Driver/Adapter pair (per Doppelgänger v0.2 §9.1): the Driver is pure-Python wrapping the substrate fork via subprocess + text files (`fct.txt`, `mix.tr`, `pfc.txt`, `qlen.txt`); the Adapter is the MCP server delegating to the Driver. The substrate fork (`provandal/ns3-datacenter` at `4dd55d8…`) is pinned in the Dockerfile. The Driver compiles topology + scenario declarations into the substrate's `config-burst.txt` format and parses output traces. At least three of the seven §5.2 failure classes (silent drops confirmed by spike; PFC storm and microburst as the targets here) are end-to-end working. Per-Flow Records (§4.2) include incomplete-flow accounting per the eval-discipline finding. Eval-time comparison primitives (flow-count delta, distribution comparison) implemented per Doppelgänger v0.2 §6.3. **Partially complete as of v0.3 publication**: fork chosen, Dockerfile pinned, parse_fct.py works end-to-end; remaining work is the Driver/Adapter pair, the topology compiler, and the failure-class inventory. | 0 |
| 2 | Naked model + Langfuse + first eval | A frontier base model is wired in with a basic system prompt. Langfuse instrumentation captures every span from the very first model call. The first eval scenario runs end-to-end and the model fails it visibly. Eval framework exists (scenario format, runner, scoring). The eval set has at least one scenario. The eval-scoring layer enforces the Architecture §3.8 substrate-level commitments (flow-count delta as primary failure signature; distribution comparison; incomplete-operation annotation). Traces visible in Langfuse's standard waterfall view. | 0 |
| 3 | Tool surface | MCP tool surface implemented with read tools that delegate through the Doppelgänger Substrate Adapter. The agent can query topology, fetch counters, read configs, tail logs. The eval scenario from stage 2 now passes some fraction of runs because the agent has reach. Every tool call emits an OTel span to Langfuse using the `harnessit.*` namespace per Architecture v0.5 §9.4. Tool conventions documented (response envelope, freshness/confidence/source metadata, staleness class). | 0 |
| 4 | Trajectory viewer v0.1 + Langfuse self-host transition | The sequence-diagram trajectory viewer ships. Queries Langfuse via API, transforms spans into the sequence-diagram representation, renders investigations as services-as-columns with time flowing down. From this point forward, every behavior change in the agent is visible in the viewer. The viewer renders gate decisions, gate denials (per Architecture v0.5 §3.7's `GateDenial` payload), and Substrate Adapter calls as first-class arrows. **Self-hosted Langfuse setup ships in this stage** per Architecture v0.5 §9.1 staged-adoption: a documented `docker compose up`-style setup (Postgres + ClickHouse + Redis + OTel collector); the trajectory viewer is exercised against both managed-Cloud and self-hosted backends; stage-0-through-3 traces are either migrated from Cloud or archived in Cloud with stage-4-onward traces flowing to self-hosted. The substrate-substitution lesson is concrete here, prefiguring the Doppelgänger → AIR Substrate Adapter transition at stage 13. | 0 |
| 5 | First skill (Tier 0 target — N₀) | TheConstruct repository contains its first skill, dispatched by the orchestrator's Router/Classifier (Architecture v0.5 §3.6) when the matching task class is detected. Skill loading uses progressive disclosure (manifest at start, body loaded on demand per Architecture v0.5 §3.3). Composition contract is in place: `invoke_skill(name, params) -> SkillResult` with stack-frame composition. The agent's behavior on that task class is visibly more disciplined, observable in both eval scores and the trajectory viewer. **Tier 0 (60 days) terminates here.** | 0 |
| 6 | Retrieval | RAG over the starter knowledge corpus (the five-document seed list at `harnessit/docs/corpus_seed_list.md` per Architecture v0.5 §3.2 — RFC 3168 + RFC 8087 in copy-in-full mode; IBTA RoCEv2 Annex, NVIDIA Cumulus Linux RoCE Configuration Guide, Arista EOS RoCE / RDMA Tuning Guide all in index-by-URL + excerpts mode). The agent can look up protocol semantics it does not already know. Retrieval is observably distinct from skills — facts versus procedures. Eval scenarios added that require retrieval to pass. Hybrid retrieval (BM25 + vector), reranking, and query rewriting are *not* in scope per Architecture v0.5 §3.2; v0.6 absorbs those upgrades. Corpus additions at this stage and beyond land in `corpus/CHANGELOG.md`. | 1 |
| 7 | Memory via RememberIT | Two-tier memory implemented over the `harnessit-agent-memory` RememberIT context. Memory is the *backing store*; CSM (stage 8) is the *cache* per Architecture v0.5 §3.4 / §3.5. Short-term memory holds the active investigation; long-term accumulates across sessions. Memory consultation is visible in the trajectory viewer. The agent recognizes a recurring symptom from a prior session in at least one eval scenario. | 1 |
| 8 | CSM and screen capture (Tier 1 target — N₁) | Context State Manager owns the context window. Token budgets per content class enforced. CSM evicts to Memory when budget pressure crosses threshold; reloads from Memory when content is needed again. Screen capture is wired in as consent-mediated, on-demand. The eval set includes a scenario where a screenshot input is required. The marquee build milestone for the architecture's most distinctive components. **Tier 1 (4 months) terminates here.** | 1 |
| 9 | Orchestration: three patterns | ReAct is the default loop. Bisection / Structured Investigation activates when the Router/Classifier detects a localization task with a clear partition function (Architecture v0.5 §3.6). Planner-Actor activates when the next proposed action exceeds a blast-radius threshold, with a verification ReAct loop wrapped around each plan step. Action gates implemented; gate-denial contract returns `GateDenial` payloads to the orchestrator (Architecture v0.5 §3.7). Investigation-checkpoint primitive persists orchestrator state + CSM working set + working memory state to RememberIT for resumable multi-day-gated runs. The agent can propose changes, get them approved, apply them, verify, and roll back on regression. | 2 |
| 10 | Multi-agent readiness | Multi-agent decomposition validated as a *capability the architecture supports* (per Architecture v0.5 §5, downgraded from "from day one, used lightly"). v1 ships single-agent; this stage documents the coordination contract that future multi-agent work would inherit (supervisor-delegation candidate, message-passing structure, shared-substrate access discipline). No multi-agent code ships in v1 unless a v1 scenario surfaces that requires it. | 2 |
| 11 | Security and guardrails | All five §7.1 security posture commitments are enforced in code, not just documented. Adversarial input handling is in place for retrieval, tool outputs, and screen captures. Memory and trajectory protection is active. Eval set includes adversarial scenarios. Confidence/freshness reasoning is exercised via Doppelgänger's adversarial-telemetry injection (per Doppelgänger v0.2's live-feel-replay-mode mitigations). | 2 |
| 12 | Eval dashboard + kickoff panel | The remaining UI components ship. Eval dashboard shows pass/fail/regression status across versions, eval set growth over time. Kickoff panel allows new investigations to start with low friction. Eval-governance dimensions named in Architecture v0.5 §3.8 (curation, scoring stack, contamination, replay-vs-distillation) are surfaced in the dashboard's metadata. | 2 |
| 13 | AIR Adapter (Tier 2 target — N₂) | The AIR Adapter is the project's second Substrate Adapter, satisfying the same MCP contract Doppelgänger does. Internally it has the same Driver/Adapter split: a Python AIR Driver that wraps NVIDIA AIR's REST + SSH interfaces, and an MCP-server Adapter shell. HarnessIT runs against a real Cumulus fabric in NVIDIA AIR; the harness does not know it is talking to AIR rather than Doppelgänger. Per Architecture v0.5 §6.1, the credibility moment for the substrate-abstraction discipline. **Tier 2 (12 months) terminates here.** | 2 |

### 2.2 What This Sequence Optimizes For

**Runnable at every stage.** There is no point in the build where the system is broken because of a half-finished refactor. Every tagged commit is a coherent state.

**Eval-measurable from stage 2.** Once Langfuse is instrumented and the eval framework exists, every subsequent stage produces measurable behavior change. We see whether each new component actually helps.

**Trajectory viewer early.** Stage 4 ships the sequence-diagram trajectory viewer. From that point forward, every behavior change is visible, not just measurable. We can use the viewer to debug the rest of the build, not just to demonstrate it at the end. This is a deliberate departure from the naive ordering that would build the UI last.

**Marquee moment placement.** Stage 8 (CSM + screen capture) is the build's most pedagogically important moment for the architecture's most distinctive components. It earns its weight because of what comes before. Stage 13 (AIR Adapter) is the credibility moment that demonstrates HarnessIT against a real fabric.

**Security in the sequence, not at the end.** Stage 11 places security after most components exist (so the threat surface is real to test against) but before the final demonstration stage (so we are not demonstrating an insecure system). Some security work happens earlier in lighter form — basic least-privilege from stage 3, basic redaction from stage 7 — but the comprehensive security pass is stage 11.

**Substrate dependencies provisioned in stages, with stage-0 setup pressure minimized.** The RememberIT context `harnessit-agent-memory` is provisioned at stage 0 (the second `harnessit-build-journal` context that v0.2 referenced was retired in v0.3 §3 in favor of workspace-level `journal.md`). Langfuse is provisioned in two stages per Architecture v0.5 §9.1: managed Langfuse Cloud at stage 0 (signing up for a free-tier project takes minutes; API key in place from the very first model call), then self-hosted Langfuse at stage 4 when the trajectory viewer ships and the managed-to-self-hosted transition becomes a teachable substrate-substitution moment. This still encounters Langfuse's real operational characteristics — just at the stage where they teach something — without paying the substrate-burden cost at stage 0 where reader-abandonment risk is highest.

### 2.3 What This Sequence Does Not Promise

The sequence does not promise that each stage takes the same amount of time. Some stages are days; some are weeks. The 2026-05-02 fork-spike compressed stage 1 (Doppelgänger v0.1) significantly relative to v0.2's "probably weeks" estimate — the substrate fork is chosen and the Dockerfile is pinned, leaving Driver, Adapter, and topology compiler as the remaining stage-1 work. Stage 2 (naked model + Langfuse + first eval) is plausibly a day. Stage 7 (Memory) and Stage 8 (CSM and screen capture) are individually multi-week stages. Stage 13 (AIR Adapter) is the most variable: it might be days if the AIR REST + SSH adapter work goes smoothly, or its own multi-week effort if substrate-divergence work surfaces. v0.3 §2.0 names the tier-target stages without committing per-stage durations beyond these directional estimates.

The sequence also does not promise that we get every stage right on the first try. Some stages will produce a v0.1 that we end up rebuilding after a later stage reveals a design problem. The build sequence is the intended order; the working journal (`<workspace>/journal.md`) will record where reality diverged from intent. The position report (`<workspace>/STATUS.md`) reflects the current divergence at any moment.

The sequence does not promise per-stage publishing. Capture is per §3 (workspace-level journal + position report + WHY blocks); publication is deferred. At any tier-target date, what's available for publication is whatever the journal has accumulated plus selectively-edited extracts; what publication form is *chosen* is decided when running code makes the right form obvious.

### 2.4 Stage Mapping: Build Plan ↔ Architecture

The Architecture document organizes its roadmap (§11) around eight editorial stages corresponding to the eight acts a reader experiences. The Build Plan organizes its sequence (§2.1) around fourteen stages corresponding to tagged commits in the build. The two are operating at different granularities. Architecture v0.5 §11.0 points at this section as the canonical mapping table; v0.3 of the Build Plan owns it.

The mapping:

| Build Plan stage | Stage name | Architecture editorial stage | Editorial act |
|---|---|---|---|
| 0 | Foundations | 0 | Foundations |
| 1 | Doppelgänger v0.1 | 1 | Foundations posts (continued) |
| 2 | Naked model + Langfuse + first eval | 1 | Foundations posts (continued) — naked-model baseline |
| 3 | Tool surface | 2 | Sensing posts |
| 4 | Trajectory viewer v0.1 | 2 | Sensing posts (continued) |
| 5 | First skill | 2 | Sensing posts (concluded) |
| 6 | Retrieval | 3 | Memory posts |
| 7 | Memory via RememberIT | 3 | Memory posts (continued) |
| 8 | CSM and screen capture | 3 | Memory posts (concluded) — marquee CSM post |
| 9 | Orchestration: three patterns | 4 | Action posts |
| 10 | Multi-agent readiness | 4 | Action posts (continued) |
| 11 | Security and guardrails | 5 | Security posts |
| 12 | Eval dashboard + kickoff panel | 6 | Discipline posts |
| 13 | AIR Adapter | 7 | Demonstration posts |

The roughly-2:1 average ratio reflects the difference in granularity: the Architecture talks about acts that contain several posts; the Build Plan talks about commits that contain several days of work. Stages 6, 7, 8 all map to Architecture stage 3 because the editorial act on memory and remembering covers retrieval, memory across sessions, and the CSM marquee post together — the editorial framing is "knowing and remembering" (per Architecture v0.5 §11 and §4 editorial sketch).

No Build Plan stage crosses the 60/4/12 plan-of-record tier boundary except by reference: tier boundaries are a Build Plan concern (§2.0), not an editorial concern. The Architecture document does not commit to per-tier publishing form; per-tier capture is per the workspace-level `journal.md` and per WHY blocks in commit messages.

---

## 3. Capture Protocol

Three rules and one informal practice. The capture protocol's job is to produce material that *enables* eventual writing without forcing it, while keeping daily friction below the threshold at which discipline collapses. The four-reviewer pressure test on 2026-05-01 found that v0.2's eleven-plus rituals would predictably collapse by stage 5; v0.3 keeps only the load-bearing core.

### 3.1 The Three-Way Collaboration

Three participants, three distinct roles:

**Erik.** The author, the lead engineer, the only state-bearing collaborator. Decides what is worth doing and what is worth keeping.

**Claude (chat collaborator).** Designs and pressure-tests in conversation. Produces drafts, frameworks, and pushback. Re-grounded at the start of each session by `STATUS.md` (the position report) and selectively from `journal.md` (recent entries). Stateless across sessions in long-term memory; auto-memory provides cross-session continuity within the workspace.

**Claude Code (builder).** Implements the actual code, runs tests, produces artifacts. Works inside the repository with file-level visibility. Stateless across sessions; oriented at the start of each session by a brief.

The fault line that matters: Claude Code knows what got built. Claude (chat) knows why we wanted to build it. Erik knows both, and is the bottleneck for translating between us. The capture protocol exists to widen that bottleneck while staying light enough to actually run.

### 3.2 The Three Rules

**Rule 1: WHY blocks in non-trivial commits.**

Every commit that changes intent (not just code) carries a `WHY:` block in the commit message. The block captures: what was tried, why this approach, what alternatives were considered, what's worth defending later. Trivial commits (typo fixes, formatting, dependency bumps) are exempt. The bar is roughly: would future-Erik or a future collaborator need this context to understand the diff?

WHY blocks live in git history — durable, attached to the diff, automatically searchable. They publish automatically with the commit; commit messages are public artifacts in the GitHub repos. Sensitive content is restructured to keep it out of committed artifacts before commit, not added to a redacted-WHY layer.

**Rule 2: A workspace-level `journal.md`, append-only, one entry per work session.**

Format per session:

```
## YYYY-MM-DD — short title
What I did.
What surprised me.
What's next.
```

Location: `<workspace>/journal.md` — at the workspace root, not in any pushed repository. Private by default; selective extracts can be edited and published later if Erik decides. Cost: roughly five minutes at the end of each work session.

The journal is the canonical narrative of the build. It is the source of truth that future writing draws from. RememberIT-side mirroring is possible later if the agent itself ever needs to consult the journal, but the markdown file is canonical regardless. The dominant access pattern is grep + sequential read, which is what flat markdown is for.

**Rule 3: A workspace-level `STATUS.md`, updated when the situation changes.**

The drift-correction artifact. Single page. Says: where we are now (the active stage and what's true at this moment), what the next two stages look like *now* (not as originally planned), what's parked, what we recently learned that contradicts the architecture.

Location: `<workspace>/STATUS.md` — workspace root, private by default. Updated when the answer to "where are we" changes, not on a fixed cadence. Cost: minutes when something changes; nothing otherwise.

This is the document Claude (chat) reads first when re-grounding in a new conversation. The architecture document is the north star; `STATUS.md` is the position report.

### 3.3 Architecture Decision Records (ADRs), Emergent-Only

When a decision will shape later work in ways that need to be defended or revisited, write an ADR. Format: numbered markdown files under `<repo>/docs/adrs/` (e.g., `0003-orchestration-blast-radius.md`); short; title, context, decision, consequences. Format matters less than discipline of writing one when the situation calls for it.

No numerical target. v0.2 budgeted "maybe a dozen across the whole project" — the budget itself is the failure mode (it pressures writing ADRs that aren't load-bearing). v0.3 makes ADRs emergent-only: write one when you catch yourself wanting to argue with a past decision, and not otherwise.

### 3.4 What v0.3 Dropped From v0.2 — and why

The four-reviewer pressure test identified the following v0.2 §3 items as ceremony rather than load-bearing. v0.3 drops them:

- **Per-section consolidation passes** (v0.2 §3.7) — happens once around stage 3, then drifts.
- **Per-section summary files** (v0.2 §3.7) — same drift pattern.
- **Reframing markers** (v0.2 §3.4) — depends on the chat collaborator remembering across re-groundings; not realistic for a stateless collaborator.
- **"This matters" tagging** (v0.2 §3.5) — depends on Erik having the metacognitive bandwidth mid-flow; he won't.
- **Decision summaries as a session-end ritual** (v0.2 §3.4) — decisions naturally land in the journal as Decision-typed entries when they happen; making a separate ritual at session end is redundant.
- **Failure-capture notes as a separate convention** (v0.2 §3.3) — failures naturally land in the journal as the "what surprised me" line in a session entry; making a separate ritual is redundant.
- **Weekly journal harvests** (v0.2 §3.7) — assumes someone is consuming the journal weekly; nobody is. The journal is consumed in bulk at writing time, not weekly.
- **Voice notes** (v0.2 §3.5) — a fantasy of a different person's discipline. Erik does not record voice notes as part of his existing workflow; adopting voice-note discipline specifically for this project will fail.
- **Two-context RememberIT structure for journaling** (v0.2 §3.2) — the operational `harnessit-agent-memory` context stays (it serves agent runtime, not the build journal). The `harnessit-build-journal` context is dropped in favor of `journal.md` as canonical.
- **Numeric ADR budget** (v0.2 §3.6) — "expected count: maybe a dozen" — replaced with "however many actually surface" (see §3.3).

Three v0.2 items were promoted to load-bearing rules in v0.3: WHY blocks (Rule 1), the journal (Rule 2), and the drift-correction position report (new — promoted from being a v0.2 gap that the Pragmatist flagged in `_reviews/04` Axis 4).

The shape of work the protocol expects, end-to-end: WHY blocks accumulate in git history; the journal accumulates as one entry per work session in chronological order; `STATUS.md` is overwritten in place each time the situation shifts; ADRs appear when actually needed. Across the whole build, this produces grep-able material in flat files. Writing the eventual series — if and when — is editorial work on existing artifacts, not reconstruction.

---

## 4. Provisional Editorial Sketch (Capture-Only Scaffold)

v0.3 demotes this section's role from "working hypothesis for the eventual series" to "capture-only scaffold." Publishing shape is deferred entirely: the eventual form may be a section-by-section blog series, a "Harness Illustrated" interactive explainer, per-stage field reports, the running code itself, or none-of-the-above. v0.3 does not commit to any of those forms. The section that follows is retained because the act-level structure is useful for *guiding what the journal pays attention to*, not because the structure is committed.

### 4.1 Working Hypothesis: Six Acts (Capture-Guidance Only)

The six-act structure is retained as a capture-guidance hypothesis. If the eventual publishing form turns out to be a blog series in this shape, the journal will already have material organized for it; if the form turns out to be different, the journal entries are still chronological and grep-able and reorganizable.

| Act | Theme | What the reader learns |
|---|---|---|
| 0 | Why we are here | The framing post. What HarnessIT is, why fine-tuning is the wrong primary investment, what the reader is signing up for, what the running example is. |
| I | Sensing and seeing | The naked model. The first tool. Many tools and the planning gap. The first skill and the leverage it provides. By the end of this act, the reader has seen the agent become coherent. |
| II | Knowing and remembering | Retrieval as distinct from skills. Memory across sessions. The marquee post on CSM and screen capture. By the end, the reader has seen the agent compound across sessions and reason about visual input. |
| III | Acting safely | Gated action. ReAct as default; Bisection for localization; Planner-Actor for high-blast-radius work; verification ReAct loops wrapping plan steps. Multi-agent readiness. By the end, the agent can propose, plan, execute, verify, and roll back. |
| IV | Securing and trusting | The full security treatment. Guardrails distinct from gates. Adversarial inputs. Memory and trajectory as security artifacts. The substrate trust boundary. |
| V | Discipline and demonstration | Evals as the only honest answer to "is the harness getting better." Trajectories as audit trail and teaching artifact. The trajectory viewer. Running HarnessIT against NVIDIA AIR. What we learned. What is next. |

### 4.2 Why This Sketch Is Useful Even Though It Will Change

Three reasons to have a sketch even though we know it is provisional:

- **It shapes capture.** If we know the eventual form will probably have an act-shape on memory and remembering, we pay closer attention to the moments when memory behavior changes. Without any editorial sketch, capture is unfocused.
- **It catches gaps early.** If a planned act has nothing in it after a build stage that should have produced material for it, that is signal. Either the act is wrong, or the build is missing something, or we under-captured. The sketch creates the contrast that surfaces the problem.
- **It invites reframing.** v0.3 explicitly expects the publishing form to differ from what the sketch assumes. Reframing is the *expected* outcome, not a worst-case scenario. The sketch's existence is what makes that reframing visible — you cannot reframe the absence of a structure.

### 4.3 What v0.3 Is Deliberately Not Deciding

- **Whether there is a blog series at all.** Publishing form is deferred until running code makes the right form obvious.
- **Whether the form is series-shaped, interactive-explainer-shaped, or per-stage-field-report-shaped.** The decision is empirical and will be made when the harness reaches a tier-target stage that has enough material to demonstrate something coherent.
- **Post count, post titles, post-level theses, publishing cadence.** All deferred.
- **Linear-vs-branching narrative.** v0.2 §4.4 committed to linear-only; v0.3 retracts that commitment because it was a publishing-shape commitment in disguise. Whether the eventual form is linear or branching depends on the form chosen.

---

## 5. Closing

This document defines the working model for HarnessIT through the build phase. The build sequence (section 2, including the §2.0 re-scope and the §2.4 stage mapping) tells us what to build, in what order, and what completion tier each stage belongs to. The capture protocol (section 3) tells us how the three of us work together and how we record what we learn. The capture-only editorial scaffold (section 4) gives us a hypothesis for guiding capture without committing to a publishing form.

With Build Plan v0.3 published — companion to Architecture v0.5 and Doppelgänger v0.2 — the foundational thinking is in a state where stage 0's remaining items can complete (Langfuse self-host setup, knowledge corpus seed list provisioning, any remaining repository scaffolding) and stage 1 work can continue against the substrate fork already chosen and pinned.

The plan is the scaffold. The journal is the truth. (The journal is now `<workspace>/journal.md` — workspace-level, append-only, private by default. The position report is `<workspace>/STATUS.md`. Both are referenced from §3.)
