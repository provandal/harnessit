# NVIDIA Cumulus Linux RoCE Configuration Guide (Index Stub)

Operational guide for RoCE configuration on NVIDIA Cumulus Linux switches. Doubles as a runbook for the substrate AIR runs at stage 13.

## Storage mode

Index-by-URL + excerpts. Full text never lives in this repository. Excerpts will be captured at stage 6 of the build, sized per stage-6 retrieval-policy decisions, and stored under `corpus/excerpts/cumulus/`.

## Source

- **Publisher:** NVIDIA
- **Document:** Cumulus Linux RoCE configuration documentation
- **Base URL:** <https://docs.nvidia.com/networking-ethernet-software/cumulus-linux/Network-Solutions/RoCE/>
- **Verification needed (Erik):** confirm the base URL above resolves to current Cumulus Linux RoCE docs at the time of provisioning. NVIDIA reorganizes their docs URL hierarchy occasionally; if the URL has moved, update this stub with the canonical link.

## License class

`vendor-copyright-fair-use-excerpts` — NVIDIA holds copyright; excerpts captured for retrieval purposes are under fair-use treatment. Not redistributable in full.

## Purpose in the corpus

The Cumulus RoCE guide covers operational concerns:

- Lossless mode configuration (PFC + buffer headroom)
- ECN configuration (WRED/RED thresholds)
- DCQCN tuning
- Buffer-pool sizing
- Diagnostic commands (`mlxlink`, `ethtool`, fabric show commands)
- Common failure modes and remediation

This is the operational complement to RFC 3168 / 8087 (which cover the mechanism) and the IBTA spec (which covers the protocol). The agent uses the Cumulus guide when investigating against an actual Cumulus-based fabric, including the AIR substrate at stage 13.

## Status

- 2026-05-04: Index stub created. Base URL captured.
- TBD (stage 6): Excerpt fetching mechanics decided; relevant subsections (RoCE configuration, PFC, ECN, DCQCN, troubleshooting) excerpted into `corpus/excerpts/cumulus/`.

## Notes

The Cumulus guide is also a runbook for the operator (configuration commands, diagnostic patterns), which is why it serves dual purpose — vendor guide and runbook — in the v0.5 corpus seed list. A separate "pure runbook" document is not included in v0.5 baseline; if stage-6 work surfaces a need for non-vendor-attached operational runbooks, candidates are listed in `../docs/corpus_seed_list.md` under "What this seed list deliberately does not include."
