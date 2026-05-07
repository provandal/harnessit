# Self-hosted Langfuse for HarnessIT

A pinned, single-machine docker-compose stack that runs Langfuse v3 locally so
HarnessIT can store traces without depending on Langfuse Cloud.

## Why this exists (and why it's not the only option)

HarnessIT supports **two equally first-class observability backends**:

1. **Langfuse Cloud** — managed, free tier, sign up and you're tracing in 60
   seconds. Ideal for quick repros, one-off demos, anyone who just wants to
   see what's going on without standing up infrastructure.
2. **Self-hosted Langfuse** — this directory. Trace data lives on your disk.
   Your ownership, your retention, your privacy boundary. Works offline. Stays
   working if upstream changes free-tier terms or disappears entirely. The
   pedagogical point of HarnessIT's substrate-substitution design (see
   `docs/HarnessIT_Architecture_v0.5.md` §9.1) is that observability shouldn't
   lock the harness in — and the test of "shouldn't lock in" is whether the
   alternative actually works. This is that alternative.

Either way, the harness reads its endpoint and keys from the workspace-level
`.langfuse-credentials` file. **Switching backends is a credential-file edit,
not a code change.**

## What's in the stack

Six containers:

| Service          | Image (pinned)                                            | Role                                                |
|------------------|-----------------------------------------------------------|-----------------------------------------------------|
| `postgres`       | `postgres:17.9`                                           | Langfuse metadata: orgs, projects, users, keys      |
| `clickhouse`     | `clickhouse/clickhouse-server:26.4.2.10`                  | Trace + observation analytics store (the bulk data) |
| `redis`          | `redis:7.4.9`                                             | Ingestion queue + worker coordination               |
| `minio`          | `cgr.dev/chainguard/minio` (digest-pinned)                | S3-compatible blob storage for events/media/exports |
| `langfuse-web`   | `langfuse/langfuse:3.172.1`                               | Next.js UI + ingestion API on port 3000             |
| `langfuse-worker`| `langfuse/langfuse-worker:3.172.1`                        | Async ingestion / batch / cleanup worker            |

Every image is pinned by tag *and* `@sha256` digest in `docker-compose.yml`,
so the same bytes pull next month even if upstream re-tags.

(Note vs. `HarnessIT_Architecture_v0.5.md` §9.1, which lists "Postgres +
ClickHouse + Redis + OTel collector": Langfuse v3 ingests via its own SDK —
no OTel collector. MinIO is the load-bearing fourth substrate. v0.5 §9.1
should be reconciled.)

## Bringing the stack up

### 1. Generate secrets and write `.env`

```bash
cd harnessit/docker/langfuse-selfhost
cp .env.example .env

# Then replace every CHANGE_ME_* value in .env. The .env.example file has
# one-liners at the top of each section to generate strong secrets with
# openssl. ENCRYPTION_KEY in particular MUST be exactly 64 hex chars.
```

### 2. Start the stack

```bash
docker compose up -d
```

First start pulls images (none if you already pulled), runs DB migrations,
and seeds ClickHouse. Wait ~60–90 seconds for everything to settle. Watch
status:

```bash
docker compose ps
docker compose logs -f langfuse-web   # quit with Ctrl-C; container keeps running
```

When `langfuse-web` is ready you'll see "Ready in …ms" in its logs.

### 3. Create a project and API keys

Open <http://localhost:3000> in your browser. Either:

- **Sign up via the web UI** — first user becomes the org admin. Create an
  organization, then a project, then under project settings → API keys, mint
  a public/secret key pair.
- **Headless init** — set the `LANGFUSE_INIT_*` block in `.env` *before* the
  first `docker compose up`, and the project + keys exist on boot. You still
  open the UI to view traces.

Either path gives you a `pk-lf-…` and `sk-lf-…` pair. Keep the secret key
somewhere durable; Langfuse will only show the full value once.

### 4. Point the harness at self-hosted

Edit `.langfuse-credentials` at the **workspace root** (one level above this
repo). Replace the three values:

```
LANGFUSE_PUBLIC_KEY="pk-lf-...your self-hosted public key..."
LANGFUSE_SECRET_KEY="sk-lf-...your self-hosted secret key..."
LANGFUSE_BASE_URL="http://localhost:3000"
```

(If you remapped the host port via `LANGFUSE_WEB_PORT` in `.env`, use that
port here.)

The harness reads this file at runtime via `harnessit.config.load_settings()`.
No code change.

### 5. Verify with an eval and the viewer

```bash
# From the harnessit repo root, with the venv active:
python -m harnessit microburst-symptom-only

# Take the trace ID it prints at the end and render:
python -m harnessit.viewer <trace_id> --output /tmp/selfhost_test.html
```

Open the HTML in a browser — the rendered trajectory should look identical
to a Cloud-rendered one. The `harnessit.viewer.client.fetch_trace_view` path
uses the same Langfuse SDK as `harnessit.tracing.init_langfuse`, so both
read/write paths exercise the new backend.

## Switching back to Cloud

Edit `.langfuse-credentials` back to your Cloud values:

```
LANGFUSE_PUBLIC_KEY="pk-lf-...your Cloud public key..."
LANGFUSE_SECRET_KEY="sk-lf-...your Cloud secret key..."
LANGFUSE_BASE_URL="https://us.cloud.langfuse.com"
```

That's it. To make the swap painless, keep two backup files:

```
.langfuse-credentials.cloud      # full creds for Cloud (gitignored at repo root)
.langfuse-credentials.selfhost   # full creds for self-hosted (gitignored)
```

And `cp` the one you want over `.langfuse-credentials`. The workspace-level
`.gitignore` already excludes `.langfuse-credentials*`.

**Stage-3-and-earlier traces stay in Cloud.** They were generated against
Cloud and Cloud retains them. The rendered HTML in `viewer/examples/` is
Cloud-independent (Mermaid.js loads from CDN at view time, no Langfuse
round-trip needed) so those publication artifacts survive any backend choice.

## Stopping and cleaning up

```bash
docker compose down              # stop containers, keep data volumes
docker compose down -v           # stop AND wipe data (deletes all traces)
docker compose stop              # pause without removing containers
```

On Windows + Docker Desktop, the volumes live inside the WSL2 VM under the
`harnessit-langfuse_*` names. `docker volume ls | grep harnessit-langfuse`
shows them.

## Troubleshooting

**`langfuse-web` keeps restarting with "missing ENCRYPTION_KEY" or similar.**
A required `.env` value is empty or wrong shape. ENCRYPTION_KEY must be
exactly 64 hex chars. Check `docker compose config` to see what the compose
file actually resolved to.

**ClickHouse migration hangs on first boot.** Normal — the first
`langfuse-worker` boot runs ClickHouse schema migrations and can take 60+
seconds. `docker compose logs langfuse-worker` shows progress.

**Port 3000 already in use.** Set `LANGFUSE_WEB_PORT=3001` (or any free
port) in `.env`, also update `NEXTAUTH_URL=http://localhost:3001`, and put
the same port in `LANGFUSE_BASE_URL` in `.langfuse-credentials`. Restart.

**Trace lands but viewer can't fetch it.** Check that `LANGFUSE_BASE_URL` in
`.langfuse-credentials` matches what the harness used at trace-write time.
The viewer calls `client.api.trace.get(trace_id)` against whichever URL the
SDK was initialized with.

**Want to start completely fresh.** `docker compose down -v` wipes data
volumes; next `up` recreates them empty.

## Upgrading the pin

When upstream Langfuse ships a new version you want to track:

1. Edit `docker-compose.yml`: bump `langfuse/langfuse:<old>` and
   `langfuse/langfuse-worker:<old>` to the new tag. Set the `@sha256:…`
   digests to placeholder/empty so they don't conflict.
2. `docker compose pull langfuse-web langfuse-worker` to fetch the new
   images.
3. `docker inspect langfuse/langfuse:<new> --format '{{index .RepoDigests 0}}'`
   to capture the real digest. Paste it into the compose file beside the
   tag.
4. `docker compose up -d` to restart with the new images.

Same procedure for `postgres`, `clickhouse`, `redis`, and (digest-only)
`minio`. Bump one substrate at a time so any breakage is bisectable.
