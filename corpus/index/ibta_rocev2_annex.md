# IBTA RoCEv2 Annex (Index Stub)

Canonical RoCEv2 specification: InfiniBand Architecture Specification, Volume 1, Annex A17.

## Storage mode

Index-by-URL + excerpts. Full text never lives in this repository. Excerpts will be captured at stage 6 of the build, sized per stage-6 retrieval-policy decisions, and stored under `corpus/excerpts/ibta/`.

## Source

- **Publisher:** InfiniBand Trade Association (IBTA)
- **Document:** InfiniBand Architecture Specification, Volume 1
- **Section:** Annex A17 (RoCEv2)
- **Access:** IBTA member portal at <https://www.infinibandta.org/ibta-specifications/>
- **Verification needed (Erik):** confirm IBTA membership status; capture the specific Annex A17 PDF download URL once member-portal access is established; record the verified URL in this stub.

## License class

`ibta-copyright-fair-use-excerpts` — IBTA holds copyright; excerpts captured for retrieval purposes are under fair-use treatment. Not redistributable in full.

## Purpose in the corpus

The canonical RoCEv2 spec covers:

- RoCEv2 packet format (UDP encapsulation, port assignment)
- Verb semantics (SEND, WRITE, READ, atomics)
- Queue-pair state machine and transitions
- Completion ordering
- RDMA error codes
- Congestion control (DCQCN integration)

These are referenced extensively by the agent during RDMA investigation; without spec-grounded definitions the agent risks hallucinating semantics that look right but contradict the standard.

## Status

- 2026-05-04: Index stub created. URL TBD pending IBTA membership verification.
- TBD: Erik confirms membership; URL captured here.
- TBD (stage 6): Excerpt fetching mechanics decided; relevant sections (RoCEv2 packet format, congestion control, PFC, ECN) excerpted into `corpus/excerpts/ibta/`.

## Notes

If IBTA membership is not in place, two fallbacks: (a) cite the spec by canonical reference without excerpting (agent has the citation but no excerpt content); (b) substitute with a published academic summary of RoCEv2 if one exists with redistribution rights. (a) is the safer fallback.
