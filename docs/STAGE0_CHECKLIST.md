# Stage 0 Finalization Checklist

This checklist captures what's required to declare Stage 0 of the HarnessIT build complete. Items split between automated/local (already done by 2026-05-04) and items that require Erik's hands-on attention.

## ✅ Closed (no further action needed)

- [x] Five GitHub repos created and pushed: `provandal/harnessit`, `provandal/doppelganger`, `provandal/theconstruct`, `provandal/ns3-datacenter` (fork)
- [x] Each repo has Apache-2.0 (or GPL-2.0 for the substrate fork) LICENSE, README, CONTRIBUTING.md (DCO sign-off required), `.gitignore`
- [x] License-boundary discipline documented in `provandal/doppelganger/NOTICE`
- [x] Substrate fork pinned at SHA `4dd55d89a46e742e505a92dc7873f82ded6db638` in `doppelganger/spike/inet-tub.Dockerfile`
- [x] Workspace-level `journal.md` and `STATUS.md` initialized; capture protocol in effect
- [x] RememberIT MCP service access verified (`server_identity` returns 2026-05-04, production us-east-1, all tools available)
- [x] Knowledge corpus directory structure created at `harnessit/corpus/`: `rfcs/`, `excerpts/`, `index/`
- [x] RFC 3168 fetched and stored: `harnessit/corpus/rfcs/rfc3168.txt` (170,966 bytes, BCP 78)
- [x] RFC 8087 fetched and stored: `harnessit/corpus/rfcs/rfc8087.txt` (46,449 bytes, BCP 78)
- [x] Index stubs for index-by-URL documents: `harnessit/corpus/index/ibta_rocev2_annex.md`, `nvidia_cumulus_roce.md`, `arista_eos_roce.md`
- [x] Corpus README and CHANGELOG initialized
- [x] Design documents in canonical .md form: `HarnessIT_Architecture_v0.5.md`, `HarnessIT_BuildPlan_v0.3.md`, `Doppelganger_Design_v0.2.md`. The legacy .docx + .txt files at v0.4/v0.2/v0.1 remain in git history; the .md files are now the source of truth.
- [x] Langfuse Cloud project provisioned (2026-05-05). Self-hosted Langfuse remains deferred to stage 4 per the staged-adoption decision.
- [x] IBTA RoCEv2 Annex resolved as citation-only (2026-05-05). Following ProtoViz precedent, the corpus uses open-source implementations (Linux kernel `drivers/infiniband/`, rdma-core, Wireshark `packet-infiniband.c`) as the primary semantic source for RoCEv2; the IBTA spec is referenced by canonical citation with no excerpts. Architecture v0.5 §3.2, `corpus_seed_list.md`, and `corpus/index/ibta_rocev2_annex.md` updated accordingly. No IBTA membership required.

## ⏳ Requires Erik

(none — all Stage 0 design / provisioning items are resolved as of 2026-05-05. Remaining work is the commit + push of the new / updated design docs and corpus files; that's at Erik's pace.)

## What stays open after this checklist

These are intentionally not in stage 0; they belong to later stages.

- **Self-hosted Langfuse setup** — stage 4 deliverable (per `project_langfuse_decision.md`).
- **Knowledge corpus excerpting and embedding** — stage 6 deliverable (per Architecture v0.5 §3.2). Stage 0 establishes the structure; stage 6 implements the retrieval mechanics.
- **CI placeholders** — not strictly required by stage 0; can land at any later stage when CI is actually wanted (probably stage 2 when first eval-runs need automation).
- **Doppelgänger Driver + Adapter + topology compiler** — stage 1 deliverable.

## Closing milestone

When the new / updated design docs and corpus files are committed + pushed to their repos, Stage 0 is fully complete and the build can move to Stage 1 (Doppelgänger v0.1 implementation).

Update `STATUS.md` to mark Stage 0 closed; append a journal entry capturing the closure date and any surprises encountered.
