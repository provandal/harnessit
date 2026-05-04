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

## ⏳ Requires Erik (in any order)

### 1. Langfuse Cloud project provisioning

**What:** Create a free-tier Langfuse Cloud project for stages 0–3 trace ingestion. Self-hosted Langfuse setup is deferred to stage 4 per the Langfuse staged-adoption decision (`workspace memory: project_langfuse_decision.md`).

**Steps:**

1. Go to <https://cloud.langfuse.com/auth/sign-up>.
2. Sign up with the email of your choice. (GitHub OAuth is fine; or use email + password.)
3. After verification, create an organization (e.g., "provandal" or "harnessit").
4. Create a project named `harnessit` inside the organization.
5. In the project's **Settings → API Keys** page, generate a new API key pair. You'll get a **public key** (starts with `pk-lf-…`) and a **secret key** (starts with `sk-lf-…`).
6. Capture both keys plus the host URL (`https://cloud.langfuse.com`) somewhere safe and not committed:
   - **Recommended:** create `<workspace>/.langfuse-credentials` (workspace-level, gitignored) with:
     ```
     LANGFUSE_HOST=https://cloud.langfuse.com
     LANGFUSE_PUBLIC_KEY=pk-lf-...
     LANGFUSE_SECRET_KEY=sk-lf-...
     ```
   - Or use your existing credential vault / 1Password / similar.
7. When stage 2 (naked model + Langfuse + first eval) starts, the harness reads `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` as environment variables.

**Verify done:** create a project on cloud.langfuse.com; capture both keys; record the storage location in `<workspace>/STATUS.md` under "Where we are." Don't commit keys to any repo.

### 2. Apply the three update memos to their respective .docx files

**What:** Each design document has a memo-form delta enumerating exact updates. Applying them produces the next published draft.

**Order (recommended; order doesn't strictly matter but cross-references resolve cleaner this way):**

1. **`harnessit/docs/v0.5_updates.md`** → `HarnessIT_Architecture_v0.4.docx` → save as `HarnessIT_Architecture_v0.5.docx`. The memo's "Application order" section gives a recommended edit sequence; the verification grep targets at the end let you confirm internal consistency.
2. **`doppelganger/docs/v0.2_updates.md`** → `Doppelganger_Design_v0.1.docx` → save as `Doppelganger_Design_v0.2.docx`. Same shape as the v0.5 memo.
3. **`harnessit/docs/v0.3_updates.md`** → `HarnessIT_BuildPlan_v0.2.docx` → save as `HarnessIT_BuildPlan_v0.3.docx`. Apply this *after* v0.5 because v0.3 references v0.5 stage definitions and the §2.4 stage-mapping table.

**Each memo's "Application order" section walks you through the per-section edits.** Each memo also has a list of verification grep targets (e.g., "search for 'the harness is the car' — should return zero matches") to run after applying the deltas.

**Commit pattern:** when each .docx is saved, commit it to the appropriate repo with a `WHY:` block in the commit message naming which Update sections were applied. The previous .docx version stays in git history.

**Verify done:** all three .docx files updated and committed; each repo's docs/ now has both vN-1 and vN .docx (or vN-1 is replaced by vN, your call).

### 3. IBTA RoCEv2 Annex access path verification

**What:** Confirm your IBTA membership status and capture the specific Annex A17 PDF URL.

**Steps:**

1. Log into the IBTA member portal at <https://www.infinibandta.org/>.
2. Navigate to the InfiniBand Architecture Specification, Volume 1.
3. Locate Annex A17 (RoCEv2). Capture its PDF download URL.
4. Update `harnessit/corpus/index/ibta_rocev2_annex.md` with the verified URL in the "Source" section.
5. Commit the update with a `WHY:` block.

**If membership is not in place** — fallback per the index stub: cite the spec by canonical reference without excerpting. The agent has the citation; excerpts wait until membership lands.

**Verify done:** `corpus/index/ibta_rocev2_annex.md` has a verified URL or a documented fallback.

### 4. Apply the v0.5 / v0.3 / v0.2 memos to the .docx files (covered in item 2 above)

(Same as item 2; listed separately here only for the checklist's completeness.)

## What stays open after this checklist

These are intentionally not in stage 0; they belong to later stages.

- **Self-hosted Langfuse setup** — stage 4 deliverable (per `project_langfuse_decision.md`).
- **Knowledge corpus excerpting and embedding** — stage 6 deliverable (per Architecture v0.5 §3.2). Stage 0 establishes the structure; stage 6 implements the retrieval mechanics.
- **CI placeholders** — not strictly required by stage 0; can land at any later stage when CI is actually wanted (probably stage 2 when first eval-runs need automation).
- **Doppelgänger Driver + Adapter + topology compiler** — stage 1 deliverable.

## Closing milestone

When all four "Requires Erik" items are checked, Stage 0 is fully complete and the build can move to Stage 1 (Doppelgänger v0.1 implementation).

Update `STATUS.md` to mark Stage 0 closed; append a journal entry capturing the closure date and any surprises encountered during the .docx applications (those make great future-Erik orientation material).
