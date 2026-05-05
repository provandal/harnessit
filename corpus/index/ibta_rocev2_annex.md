# IBTA RoCEv2 Annex (Citation-Only)

Canonical RoCEv2 specification: InfiniBand Architecture Specification, Volume 1, Annex A17.

## Storage mode

**Citation-only.** Full text never lives in this repository; no excerpts are captured. The corpus references the spec by canonical citation for human readers who have IBTA access. The agent's operational knowledge of RoCEv2 comes from the open-source implementations in the corpus (Linux kernel `drivers/infiniband/`, `linux-rdma/rdma-core`, Wireshark `packet-infiniband.c`) backed by community semantic references (rdmamojo, kernel.org InfiniBand docs) for cases where implementation reading alone is ambiguous.

This is the same pattern provandal.dev's protocol-visualization project (ProtoViz) adopted in 2026-03 for the same constraint. For an operations / troubleshooting agent, what the kernel actually does with a packet is more useful than what the spec says it should do. The IBTA citation remains so a human reader with access can look up the canonical text; the agent does not need it.

## Source citation

- **Publisher:** InfiniBand Trade Association (IBTA)
- **Document:** InfiniBand Architecture Specification, Volume 1
- **Section:** Annex A17 (RoCEv2)
- **Access:** IBTA member portal at <https://www.infinibandta.org/ibta-specifications/>
- **Note on access:** IBTA membership is not held by the project. No verified PDF URL is recorded; the spec is referenced by name and section only.

## Alt-URLs (non-proprietary semantic references)

For sections of RoCE behavior where the spec text would normally be the authoritative reference, the following provide non-proprietary explanations:

- **rdmamojo** — <https://www.rdmamojo.com/> — Dotan Barak's RDMA blog. Definitional explanations of verbs, QP states, completion semantics, transport modes (RC / UC / UD / RD), CQE encoding. Plain English; no spec text reproduced.
- **kernel.org InfiniBand documentation** — <https://docs.kernel.org/infiniband/> — Linux kernel project's published RDMA / InfiniBand documentation. Covers verbs API, user-space device handling, kernel-side QP management.
- **Mellanox Community RoCE articles** — <https://community.mellanox.com/s/topic/0TO50000000XmgwGAC/rdma> — Vendor community articles explaining RoCE semantics, configuration, and troubleshooting.
- **Linux kernel source** (in the corpus): `drivers/infiniband/core/cm.c` (CM REQ/REP/RTU exchange), `drivers/infiniband/hw/mlx5/qp.c` (QP state machine), `drivers/infiniband/core/verbs.c` (verbs enforcement). The implementation is the operational truth.
- **rdma-core source** (in the corpus): `libibverbs/verbs.h`, `librdmacm/cma.c`. The userspace API is the application-facing truth.
- **Wireshark dissector** (in the corpus): `epan/dissectors/packet-infiniband.c`. The wire format is what the bytes actually mean.

## License class

`citation-only` — IBTA holds copyright; no excerpts taken; no fair-use claim made on this entry. The citation itself is a factual reference (publisher, document name, section number) and carries no copyright concern.

## Purpose in the corpus

The IBTA RoCEv2 Annex is the canonical specification for:

- RoCEv2 packet format (UDP encapsulation, port 4791 assignment)
- Verb semantics (SEND, WRITE, READ, atomics)
- Queue-pair state machine and transitions (RESET → INIT → RTR → RTS)
- Completion ordering
- RDMA error codes (NAK reasons, completion-with-error encodings)
- Congestion control hooks (DCQCN integration points)

This entry serves human readers who want to consult the canonical spec. The agent's retrieval queries on these topics resolve against the implementations and community references listed above; the IBTA entry returns the citation as a "see also" pointer, not as content.

## Status

- 2026-05-04: Index stub created.
- 2026-05-05: Switched to citation-only mode; alt-URLs and implementation references documented. IBTA membership verification dropped as a Stage 0 blocker.

## Notes

If IBTA membership is later established (Erik's company joining IBTA, or a project sponsor providing access), the entry can be promoted to `index-by-URL + excerpts` mode and the spec's verified PDF URL captured. Until then, the corpus operates without spec excerpts and the agent's behavior is exercised against the implementations.
