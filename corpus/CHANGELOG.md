# Corpus Changelog

Append-only log of corpus additions and modifications. Newest entries at top.

## 2026-05-04 — Initial provisioning (Stage 0 finalization)

- **RFC 3168** (`rfcs/rfc3168.txt`) — *The Addition of Explicit Congestion Notification (ECN) to IP* (Ramakrishnan, Floyd, Black; September 2001; Standards Track). Mode: copy-in-full. License: BCP 78. Source: <https://www.rfc-editor.org/rfc/rfc3168.txt>. Size: 170,966 bytes / 3,531 lines. Purpose: foundational ECN semantics for the corpus's RoCE/RDMA reasoning content.
- **RFC 8087** (`rfcs/rfc8087.txt`) — *The Benefits of Using Explicit Congestion Notification (ECN)* (Fairhurst, Welzl; March 2017; Informational). Mode: copy-in-full. License: BCP 78. Source: <https://www.rfc-editor.org/rfc/rfc8087.txt>. Size: 46,449 bytes / 1,067 lines. Purpose: companion to RFC 3168; explains why ECN is preferable to drops.
- **IBTA RoCEv2 Annex** (`index/ibta_rocev2_annex.md`) — index stub created. Mode: index-by-URL + excerpts. License: IBTA copyright. Status: canonical URL pending verification of Erik's IBTA membership; excerpt fetching deferred to stage 6.
- **NVIDIA Cumulus Linux RoCE Configuration Guide** (`index/nvidia_cumulus_roce.md`) — index stub created. Mode: index-by-URL + excerpts. License: NVIDIA copyright. Status: base URL captured; excerpt fetching deferred to stage 6.
- **Arista EOS RoCE / RDMA Tuning Guide** (`index/arista_eos_roce.md`) — index stub created. Mode: index-by-URL + excerpts. License: Arista copyright. Status: base URL captured; excerpt fetching deferred to stage 6.
- Corpus directory structure initialized: `rfcs/`, `excerpts/` (empty until stage 6), `index/`. Corpus README and this CHANGELOG written.
