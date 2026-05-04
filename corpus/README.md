# HarnessIT Knowledge Corpus

The retrieval-layer source-of-truth corpus for HarnessIT. Organized per Architecture v0.5 §3.2 and the seed-list policy at `../docs/corpus_seed_list.md`.

## Structure

```
corpus/
├── README.md            (this file)
├── CHANGELOG.md         (per-document additions, dated)
├── rfcs/                (copy-in-full mode: redistribution-permissive documents)
├── excerpts/            (index-by-URL mode: fair-use excerpts; populated at stage 6)
└── index/               (index-by-URL mode: per-document metadata stubs)
```

## Two storage modes (per Architecture v0.5 §3.2)

**Copy-in-full mode** — for documents under a redistribution-permissive license. Full text lives in `rfcs/` (or another suitable subdirectory if non-RFC permissive documents are added later); embeddings will index the text directly at stage 6 of the build. Currently used for: IETF RFCs under BCP 78.

**Index-by-URL + excerpts mode** — for copyrighted documents (specifications, vendor configuration guides, runbooks). The `index/` subdirectory holds per-document metadata stubs (URL, license class, last-fetched-at, purpose). The `excerpts/` subdirectory will hold fair-use excerpts captured at stage 6 of the build, organized one subdirectory per document. Full text of these documents never lives in this repository.

## Current contents

| Path | Mode | License | Status |
|---|---|---|---|
| `rfcs/rfc3168.txt` | Copy-in-full | BCP 78 (IETF Trust Legal Provisions) | Provisioned 2026-05-04 |
| `rfcs/rfc8087.txt` | Copy-in-full | BCP 78 (IETF Trust Legal Provisions) | Provisioned 2026-05-04 |
| `index/ibta_rocev2_annex.md` | Index-by-URL + excerpts | IBTA copyright | URL captured 2026-05-04; excerpts deferred to stage 6 |
| `index/nvidia_cumulus_roce.md` | Index-by-URL + excerpts | NVIDIA copyright | URL captured 2026-05-04; excerpts deferred to stage 6 |
| `index/arista_eos_roce.md` | Index-by-URL + excerpts | Arista copyright | URL captured 2026-05-04; excerpts deferred to stage 6 |

## Why excerpts are deferred to stage 6

The two-mode policy is committed in v0.5 §3.2; specific excerpt-fetch mechanics (chunking strategy, excerpt size limits, refresh cadence, what to extract from a multi-page vendor doc, embedding-model choice) are stage 6 implementation work because they are coupled to the retrieval layer's architecture. Index stubs that carry just the URL + license class are stage-0-appropriate.

## License notes

- **IETF RFCs** are redistributable under BCP 78 (IETF Trust Legal Provisions Relating to IETF Documents, <https://trustee.ietf.org/license-info>). Copying RFC text into this corpus is explicitly permitted by §3 of the Trust Legal Provisions; this corpus follows the prescribed attribution by preserving the original RFC text including header/footer/copyright notices.
- **Other documents** referenced from `index/` retain their original copyrights; this corpus stores only URLs and (at stage 6) fair-use excerpts. The harnessit repository's overall LICENSE is Apache-2.0; per-file licensing for documents in `rfcs/` follows their respective sources.

## How to add a document

1. Determine license class (redistribution-permissive vs copyrighted).
2. Pick storage mode based on license class.
3. Add the document under `rfcs/` (copy-in-full) or `index/` (index-by-URL stub) with appropriate metadata.
4. Append a `CHANGELOG.md` entry: date, document, mode, source URL, why added.

The seed-list policy (`../docs/corpus_seed_list.md`) names what the v0.5 baseline includes and what is deliberately excluded. Future additions should be evaluated against the same policy.
