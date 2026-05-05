# HarnessIT Knowledge Corpus — Seed List (v0.5 baseline)

The starter set of documents that seeds the HarnessIT retrieval layer at stage 6 of the build (see Build Plan v0.3 §2.1, stage 6). v0.5 baseline; expansion happens at stage 6 itself and beyond as the eval set surfaces gaps.

## Corpus-construction policy

Three storage modes, picked per-document by license:

- **Copy-in-full** for documents under a redistribution-permissive license — IETF RFCs under BCP 78, and source files under GPL-2.0 / BSD / MIT / Apache when used with the source's notice and attribution requirements. The full text lives in the corpus repository; vector embeddings index it directly.
- **Index-by-URL + excerpts** for copyrighted documents that are not redistribution-permissive but where fair-use comfortably covers a bounded excerpt (some vendor configuration guides, published runbooks). The corpus stores `url`, fetched excerpts, `last_fetched_at`, and `license_class`; full text never lives in the repository.
- **Citation-only** for documents whose license does not permit excerpting, where the project lacks access (paywalled / member-only specs), or where the agent's operational understanding is better served by other sources already in the corpus. The corpus stores only the canonical reference (document, section, title, URL) plus alt-URLs that describe the same material in non-proprietary form.

Retrieval-policy details (chunking strategy, excerpt size limits, refresh cadence, embedding model choice) are left to stage 6 implementation; v0.5 commits to the three-mode shape and the seed list below.

## Implementations as primary semantic source

Where a copyrighted spec describes a protocol that has open-source reference implementations, HarnessIT prefers the implementations as the *operational* source and demotes the spec to a citation. For RDMA / RoCE specifically:

- Linux kernel `drivers/infiniband/` is the authoritative implementation of the IB / RoCE stack on the platform the agent reasons about.
- `linux-rdma/rdma-core` is the userspace verbs API authority — what applications and libraries actually call.
- Wireshark's `epan/dissectors/packet-infiniband.c` is the wire-format authority — how the bytes on the wire are actually interpreted.

These three are the *operational* truth for what the RoCE protocol does in practice. The IBTA RoCEv2 Annex is referenced by canonical citation only; readers with IBTA access follow the citation, while the corpus content the agent retrieves comes from the implementations. This is the same pattern provandal.dev's protocol-visualization project (ProtoViz) has used since 2026-03; for an operations / troubleshooting agent, implementation behavior is more useful than spec text.

## Content Disclaimer

Protocol descriptions in HarnessIT's knowledge corpus are based on open-source implementations (Linux kernel, rdma-core, Wireshark) and public RFCs. No proprietary specification text has been reproduced. IBTA, IEEE, T11/INCITS, and other specification references are provided as citations for further reading; the explanatory content the agent retrieves is derived from open-source sources and original prose. If any content inadvertently reproduces copyrighted material, it will be removed on notice.

## Seed list

| # | Document / Source | Mode | License | Purpose in the corpus |
|---|---|---|---|---|
| 1 | RFC 3168 — *The Addition of Explicit Congestion Notification (ECN) to IP* | Copy-in-full | BCP 78 (IETF Trust legal provisions); freely redistributable | Foundational ECN semantics: CE-bit, ECT codepoints, transport-layer feedback |
| 2 | RFC 8087 — *The Benefits of Using Explicit Congestion Notification (ECN)* | Copy-in-full | BCP 78 | Companion to RFC 3168: why ECN is preferable to drops; loss-vs-marking trade-offs; deployment guidance |
| 3 | Linux kernel `drivers/infiniband/` (selected files: `core/cm.c`, `core/verbs.c`, `hw/mlx5/qp.c`, `hw/mlx5/main.c`, plus headers in `include/rdma/`) | Copy-in-full | GPL-2.0 with attribution per kernel licensing rules | RDMA implementation authority: QP state machine, CM REQ/REP/RTU exchange, verbs enforcement, mlx5 driver behavior |
| 4 | `linux-rdma/rdma-core` (selected files: `libibverbs/verbs.h`, `libibverbs/cmd.c`, `librdmacm/cma.c`) | Copy-in-full | GPL-2.0 / BSD-2-Clause dual-licensed; attribution preserved | Userspace verbs API authority: `ibv_post_send`, `ibv_poll_cq`, `rdma_create_qp`, `rdma_connect` |
| 5 | Wireshark `epan/dissectors/packet-infiniband.c` | Copy-in-full | GPL-2.0 with attribution | Wire-format authority: BTH / RETH / AETH / IETH / DETH header parsing; what the bytes on the wire actually mean |
| 6 | NVIDIA Cumulus Linux RoCE Configuration Guide (docs.nvidia.com/networking-ethernet-software) | Index-by-URL + excerpts | NVIDIA copyright; excerpts under fair use | Operational guide for the Cumulus-based fabric AIR runs at stage 13; doubles as runbook for ECN/PFC/DCQCN configuration on Cumulus |
| 7 | Arista EOS RoCE / RDMA Tuning Guide (Arista's published RDMA-over-Ethernet documentation) | Index-by-URL + excerpts | Arista copyright; excerpts under fair use | Non-NVIDIA vendor perspective on multi-vendor RoCE configuration patterns; the corpus represents more than one switch-OS dialect |
| 8 | IBTA RoCEv2 Annex (InfiniBand Architecture Specification, Vol 1, Annex A17) | Citation-only | IBTA copyright; member-portal access only; no excerpts | Canonical RoCEv2 spec citation. Agent's operational knowledge of RoCEv2 comes from items 3–5; this entry is the spec pointer for human readers with IBTA access |
| 9 | rdmamojo (rdmamojo.com — Dotan Barak's RDMA blog) and kernel.org InfiniBand docs (docs.kernel.org/infiniband/) | Index-by-URL | Community-published; standard-blog / kernel-docs licensing; bounded fair-use excerpts | Plain-English semantic backup for cases where item 3–5 implementation reading is ambiguous and the IBTA spec citation alone isn't enough |

## What this seed list deliberately does not include

- **Other vendor switch documentation** (Broadcom Tomahawk PFC docs, Cisco Nexus 9000 RoCE configuration). Excluded from the v0.5 baseline because their license terms are typically more restrictive than fair-use excerpting comfortably covers, and Arista already gives the corpus a non-NVIDIA dialect for the agent to reason across. Stage 6+ may add them if eval scenarios surface a need.
- **Academic papers on AI-fabric pathologies** (Meta's SIGCOMM 2024 reporting on disabling DCQCN for LLM training; DeepSeek's reported app-layer-CC approach; NSDI/SIGCOMM RoCE-scaling work). Excluded from v0.5 baseline; will likely land at stage 6+ as the corpus grows. Papers are redistributable under varying conventions; per-paper license-check is needed before adding.
- **Internal runbooks from production environments** (Microsoft Azure GPU networking troubleshooting, AWS PFC tuning, hyperscaler on-call playbooks). Excluded because they are not published; including them would require permissions the project does not have.
- **NCCL collective-pattern documentation.** Excluded because Doppelgänger v0.2 §3.3 explicitly does not model NCCL collectives; including the corpus content without simulating the underlying behavior would teach the agent about a topic it cannot then exercise. Adds value once a future Doppelgänger version models collectives.
- **The IBTA RoCEv2 Annex as content.** Erik does not have IBTA membership through his current employer; the spec stays in the corpus as a citation only (item 8 above). Operational understanding of RoCE comes from items 3–5 (implementations) backed by item 9 (community semantic explanation) where the implementations alone are ambiguous. This is the same approach ProtoViz adopted for the same constraint.

## Provisioning checklist (stage 0 finalization)

This list captures what gets done when stage 0's corpus-provisioning task runs. Each item produces both a corpus entry and a `corpus/CHANGELOG.md` note recording the addition.

- [x] **RFC 3168** — fetched from <https://www.rfc-editor.org/rfc/rfc3168>; stored in `corpus/rfcs/rfc3168.txt` (170,966 bytes); ready to embed at stage 6.
- [x] **RFC 8087** — fetched from <https://www.rfc-editor.org/rfc/rfc8087>; stored in `corpus/rfcs/rfc8087.txt` (46,449 bytes); ready to embed at stage 6.
- [ ] **Linux kernel RDMA files** — fetch the selected files from a stable Linux kernel tag (e.g., v6.8 LTS); store under `corpus/sources/linux/drivers/infiniband/...` preserving directory structure and license headers; record the kernel commit SHA in `corpus/CHANGELOG.md`. License classification: `gpl-2.0-with-attribution`.
- [ ] **rdma-core files** — fetch the selected files from a stable `linux-rdma/rdma-core` tag; store under `corpus/sources/rdma-core/...` preserving directory structure and license headers; record the tag in `corpus/CHANGELOG.md`. License classification: `gpl-2.0-or-bsd-2-clause-with-attribution`.
- [ ] **Wireshark RoCE dissector** — fetch `epan/dissectors/packet-infiniband.c` from a stable Wireshark tag; store under `corpus/sources/wireshark/...` preserving the license header. License classification: `gpl-2.0-with-attribution`.
- [ ] **NVIDIA Cumulus Linux RoCE Configuration Guide** — capture base URL on docs.nvidia.com; identify the RoCE-specific subsections; fetch and excerpt; store in `corpus/excerpts/cumulus/`. License classification: `vendor-copyright-fair-use-excerpts`.
- [ ] **Arista EOS RoCE / RDMA Tuning Guide** — capture base URL on arista.com; identify the RDMA-over-Ethernet documentation pages; fetch and excerpt; store in `corpus/excerpts/arista/`. License classification: `vendor-copyright-fair-use-excerpts`.
- [x] **IBTA RoCEv2 Annex** — index stub at `corpus/index/ibta_rocev2_annex.md` records the canonical citation and alt-URLs; no excerpts captured (citation-only mode). No IBTA membership required.
- [ ] **rdmamojo + kernel.org InfiniBand docs** — capture top-level URLs; identify pages most relevant to RoCEv2 / DCQCN / PFC / verbs semantics; index-by-URL with fair-use excerpts of specific pages where helpful. License classification: `community-published-fair-use-excerpts` for rdmamojo; `gpl-2.0-with-attribution` for kernel.org docs.

## Future expansion

Stage 6 (retrieval implementation) will likely surface gaps where the v0.5 seed list isn't enough — for example, when an eval scenario asks the agent to reason about a specific PFC-storm propagation pattern that isn't in the seed corpus, or about adaptive-routing behavior on Spectrum-X (which Doppelgänger v0.2 §3.3 explicitly does not model but which a SONiC- or AIR-based scenario might exercise). Each gap is an addition opportunity. Stage 6+ work records additions in `corpus/CHANGELOG.md` so the corpus's growth is itself a captured artifact.

The corpus is not expected to remain at nine entries. The expansion path is per-document, each addition individually license-checked and mode-classified.
