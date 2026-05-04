# HarnessIT Knowledge Corpus — Seed List (v0.5 baseline)

The starter set of documents that seeds the HarnessIT retrieval layer at stage 6 of the build (see Build Plan v0.3 §2.1, stage 6). v0.5 baseline; expansion happens at stage 6 itself and beyond as the eval set surfaces gaps.

## Corpus-construction policy

Two storage modes, picked per-document by license:

- **Copy-in-full** for documents under a redistribution-permissive license (notably IETF RFCs under BCP 78). The full text lives in the corpus repository; vector embeddings index it directly.
- **Index-by-URL + excerpts** for copyrighted documents (IBTA specifications, vendor configuration guides, published runbooks). The corpus stores `url`, fetched excerpts (limited per document, fair-use), `last_fetched_at`, and `license_class`; full text never lives in the repository. Retrieval queries hit the excerpts; the agent follows URLs for deeper context when needed.

Retrieval-policy details (chunking strategy, excerpt size limits, refresh cadence, embedding model choice) are left to stage 6 implementation; v0.5 commits to the two-mode shape and the seed list below.

## Seed list

| # | Document | Mode | License | Purpose in the corpus |
|---|---|---|---|---|
| 1 | RFC 3168 — *The Addition of Explicit Congestion Notification (ECN) to IP* | Copy-in-full | BCP 78 (IETF Trust legal provisions); freely redistributable | Foundational ECN semantics: CE-bit, ECT codepoints, transport-layer feedback |
| 2 | RFC 8087 — *The Benefits of Using Explicit Congestion Notification (ECN)* | Copy-in-full | BCP 78 | Companion to RFC 3168: why ECN is preferable to drops; loss-vs-marking trade-offs; deployment guidance |
| 3 | IBTA RoCEv2 Annex (InfiniBand Architecture Specification, Vol 1, Annex A17) | Index-by-URL + excerpts | IBTA copyright; specification accessed via IBTA member portal | Canonical RoCEv2 spec: verb semantics (SEND/WRITE/READ/atomics), completion ordering, RDMA error codes, queue-pair state machine |
| 4 | NVIDIA Cumulus Linux RoCE Configuration Guide (docs.nvidia.com/networking-ethernet-software) | Index-by-URL + excerpts | NVIDIA copyright; excerpts under fair use | Operational guide for the Cumulus-based fabric AIR runs at stage 13; doubles as runbook for ECN/PFC/DCQCN configuration on Cumulus |
| 5 | Arista EOS RoCE / RDMA Tuning Guide (Arista's published RDMA-over-Ethernet documentation) | Index-by-URL + excerpts | Arista copyright; excerpts under fair use | Non-NVIDIA vendor perspective on multi-vendor RoCE configuration patterns; the corpus represents more than one switch-OS dialect |

## What this seed list deliberately does not include

- **Other vendor switch documentation** (Broadcom Tomahawk PFC docs, Cisco Nexus 9000 RoCE configuration). Excluded from the v0.5 baseline because their license terms are typically more restrictive than fair-use excerpting comfortably covers, and Arista already gives the corpus a non-NVIDIA dialect for the agent to reason across. Stage 6+ may add them if eval scenarios surface a need.
- **Academic papers on AI-fabric pathologies** (Meta's SIGCOMM 2024 reporting on disabling DCQCN for LLM training; DeepSeek's reported app-layer-CC approach; NSDI/SIGCOMM RoCE-scaling work). Excluded from v0.5 baseline; will likely land at stage 6+ as the corpus grows. Papers are redistributable under varying conventions; per-paper license-check is needed before adding.
- **Internal runbooks from production environments** (Microsoft Azure GPU networking troubleshooting, AWS PFC tuning, hyperscaler on-call playbooks). Excluded because they are not published; including them would require permissions the project does not have.
- **NCCL collective-pattern documentation.** Excluded because Doppelgänger v0.2 §3.3 explicitly does not model NCCL collectives; including the corpus content without simulating the underlying behavior would teach the agent about a topic it cannot then exercise. Adds value once a future Doppelgänger version models collectives.

## Provisioning checklist (stage 0 finalization)

This list captures what gets done when stage 0's corpus-provisioning task runs. Each item produces both a corpus entry and a `corpus/CHANGELOG.md` note recording the addition.

- [ ] **RFC 3168** — fetch text from <https://www.rfc-editor.org/rfc/rfc3168>; store in `corpus/rfcs/rfc3168.txt`; embed.
- [ ] **RFC 8087** — fetch text from <https://www.rfc-editor.org/rfc/rfc8087>; store in `corpus/rfcs/rfc8087.txt`; embed.
- [ ] **IBTA RoCEv2 Annex** — record canonical access URL (IBTA member portal); fetch the Annex A17 PDF; capture excerpts of the RoCEv2-specific sections (RoCEv2 packet format, congestion control, PFC, ECN); store excerpt text + metadata in `corpus/excerpts/ibta/`. Verify Erik's IBTA membership status before fetch.
- [ ] **NVIDIA Cumulus Linux RoCE Configuration Guide** — capture base URL on docs.nvidia.com; identify the RoCE-specific subsections; fetch and excerpt; store in `corpus/excerpts/cumulus/`. License classification: `vendor-copyright-fair-use-excerpts`.
- [ ] **Arista EOS RoCE / RDMA Tuning Guide** — capture base URL on arista.com; identify the RDMA-over-Ethernet documentation pages; fetch and excerpt; store in `corpus/excerpts/arista/`. License classification: `vendor-copyright-fair-use-excerpts`.

## Future expansion

Stage 6 (retrieval implementation) will likely surface gaps where the v0.5 seed list isn't enough — for example, when an eval scenario asks the agent to reason about a specific PFC-storm propagation pattern that isn't in the seed corpus, or about adaptive-routing behavior on Spectrum-X (which Doppelgänger v0.2 §3.3 explicitly does not model but which a SONiC- or AIR-based scenario might exercise). Each gap is an addition opportunity. Stage 6+ work records additions in `corpus/CHANGELOG.md` so the corpus's growth is itself a captured artifact.

The corpus is not expected to remain at five documents. The expansion path is per-document, each addition individually license-checked and mode-classified.
