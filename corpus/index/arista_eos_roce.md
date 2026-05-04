# Arista EOS RoCE / RDMA Tuning Guide (Index Stub)

Non-NVIDIA vendor perspective on RoCE configuration; lets the corpus represent more than one switch-OS dialect.

## Storage mode

Index-by-URL + excerpts. Full text never lives in this repository. Excerpts will be captured at stage 6 of the build, sized per stage-6 retrieval-policy decisions, and stored under `corpus/excerpts/arista/`.

## Source

- **Publisher:** Arista Networks
- **Document:** Arista EOS RoCE / RDMA-over-Ethernet documentation (also called "AI / ML Networking" docs in some Arista materials)
- **Base URL:** <https://www.arista.com/en/support/product-documentation> (entry point — the specific RoCE/RDMA guide URL needs verification at provisioning time)
- **Verification needed (Erik):** locate the current canonical Arista RoCE/RDMA configuration document; capture the specific URL into this stub. Arista tends to publish guides on their support portal and TOI (Technology of Interest) pages; the right entry point may be either the product-documentation portal or a specific AI/ML networking page.

## License class

`vendor-copyright-fair-use-excerpts` — Arista holds copyright; excerpts captured for retrieval purposes are under fair-use treatment. Not redistributable in full.

## Purpose in the corpus

The Arista guide provides the non-NVIDIA dialect of RoCE configuration:

- Arista-specific PFC and ECN configuration commands and conventions
- Arista's buffer model and tuning parameters
- DCQCN and AI-fabric-specific guidance per Arista's published reference architectures
- Diagnostic commands (`show interfaces`, `show qos`, `show qos interfaces` Arista-specific outputs)

The agent benefits from cross-vendor exposure even when the active substrate is single-vendor: the *concepts* (PFC, ECN, lossless, DCQCN) are vendor-neutral, but the *operational dialect* (commands, output formats, terminology) varies. A corpus that only knows one vendor will produce an agent that hallucinates other vendors' command shapes.

## Status

- 2026-05-04: Index stub created. Base URL captured (entry point only; specific RoCE-doc URL pending Erik's verification at provisioning time).
- TBD (stage 6): Excerpt fetching mechanics decided; relevant sections excerpted into `corpus/excerpts/arista/`.

## Notes

Arista is the v0.5 baseline's only non-NVIDIA dialect. If stage-6 work surfaces a need for additional vendor coverage (Broadcom Tomahawk, Cisco Nexus, Juniper QFX), candidates and exclusion rationale are documented in `../docs/corpus_seed_list.md`. Adding a vendor to the corpus is a per-document license check + index-stub creation.
