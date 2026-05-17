# Deploying the Iowa Legal Corpus to DigitalOcean App Platform

Complete, start-to-finish runbook. Source = a connected **GitHub repo**
(every `git push` to `main` rebuilds and deploys). Launch on the free
**`*.ondigitalocean.app`** subdomain (a custom domain can be added later
with no rebuild).

> Conventions: shell blocks are copy-pasteable. Replace anything in
> `<ANGLE_BRACKETS>`. `$APP_ID` / `$DB_ID` mean the IDs the commands print.

---

## 0. What gets deployed

```
                 ┌─────────────────────── App Platform ───────────────────────┐
  git push  ──►  │  build root Dockerfile (Vite SPA → Django)                  │
                 │                                                             │
  Internet ─TLS─►│  web service: gunicorn + WhiteNoise                         │
                 │    • / and /assets/*   → React SPA (same-origin)            │
                 │    • /api/*            → Django Ninja API                   │
                 │    • /admin/           → Django admin                       │
                 │  PRE_DEPLOY job: manage.py migrate (before traffic)         │
                 └───────────────┬───────────────────────┬─────────────────────┘
                                 │                        │
                   ${iowa-db}    │                        │  ${iowa-cache}
                                 ▼                        ▼
                 Managed Postgres 16 (pgvector)   Managed Valkey (Redis)
                 — standalone, preloaded —        — chat quota / rate limits —
```

The Postgres cluster is created and **loaded with the corpus first**, as a
standalone cluster, so the app comes up against real data (no empty-DB
race). Valkey is provisioned by the app itself (nothing to preload).

---

## 1. Accounts and tools (one time)

1. A DigitalOcean account with billing enabled
   (Settings → Billing → add a card).
2. **`doctl`** (the DO CLI):
   - macOS: `brew install doctl`
   - Linux: `sudo snap install doctl`
   - or download from <https://github.com/digitalocean/doctl/releases>
3. A Personal Access Token: <https://cloud.digitalocean.com/account/api/tokens>
   → "Generate New Token", **Read + Write**, copy it. Then:
   ```bash
   doctl auth init        # paste the token when prompted
   doctl account get      # sanity check — prints your account
   ```
4. `git` and (optional, easiest) the GitHub CLI `gh`
   (`brew install gh` / `sudo snap install gh`; then `gh auth login`).

---

## 2. Push the code to GitHub (private)

`backend/.env` is gitignored, so no secrets leave your machine. The image
builds the frontend from source, so `node_modules/` and `frontend/dist/`
(also gitignored) are not needed in the repo.

From `/workspaces/statutes`:

```bash
git add backend frontend Dockerfile .dockerignore deploy DEPLOY.md \
        TASKS.md README.md .gitignore
git commit -m "Production deploy: App Platform + Managed PG/Valkey"
```

> The untracked `iowa_code_probe.json`, `Iowa Court Rules/` PDFs, and the
> `.docx` brief are large and **not** needed to deploy (the corpus already
> lives in the database). Leave them out of the commit, or add them to
> `.gitignore`. `.dockerignore` already excludes them from the image.

Create the private repo and push:

```bash
# With gh (easiest):
gh repo create statutes --private --source=. --remote=origin --push

# Or manually: create an empty private repo at github.com, then:
#   git remote add origin git@github.com:<GH_USER>/statutes.git
#   git branch -M main
#   git push -u origin main
```

Note your repo slug — `<GH_USER>/statutes` — you need it in step 6.

---

## 3. Authorize App Platform on GitHub (one time, browser)

App Platform needs read access to the repo to build it. This can only be
done in the UI once:

1. Go to <https://cloud.digitalocean.com/apps> → **Create App**.
2. Choose **GitHub** as the source → **Manage Access** / **Authorize
   DigitalOcean** → install the DigitalOcean app on your GitHub account and
   grant it the `statutes` repo.
3. You can **cancel out of the create-app wizard** after authorizing — we
   create the app from the spec in step 8. The authorization persists.

---

## 4. Create the Managed Postgres cluster

Create it in the **same region as the app** (`nyc`) so the app reaches it
over DigitalOcean's private network. `db-s-1vcpu-2gb` comfortably holds the
~600 MB corpus plus the HNSW index with headroom.

```bash
doctl databases create iowa-corpus-db \
  --engine pg --version 16 \
  --region nyc1 \
  --size db-s-1vcpu-2gb --num-nodes 1

# Wait until status is "online" (a few minutes):
doctl databases list
```

Grab the cluster ID and its admin connection URI:

```bash
DB_ID=$(doctl databases list --format ID,Name --no-header \
        | awk '/iowa-corpus-db/{print $1}')
echo "DB_ID=$DB_ID"

doctl databases connection "$DB_ID" --format URI
# → postgresql://doadmin:<PW>@<host>:25060/defaultdb?sslmode=require
```

Keep that URI handy for the next step. (During the data load the cluster
accepts connections from any IP by default; in step 9 we lock it to the
app.)

---

## 5. Load the corpus into the managed cluster

This dumps your local Docker Postgres and restores it — **embeddings
travel in the dump, so there is no re-embedding cost.** From
`/workspaces/statutes`, with the local `backend-db-1` container running:

```bash
export TARGET_URL='postgresql://doadmin:<PW>@<host>:25060/defaultdb?sslmode=require'
deploy/migrate_db.sh
```

The script enables `pgvector` on the target, restores, and prints counts.
**Confirm: `nodes = 31002`, `versions = 29062`, `embedded = 29062`.** If
the counts are zero, `TARGET_URL` was wrong or the cluster wasn't online —
fix and re-run (the script is idempotent: `--clean --if-exists`).

---

## 6. The spec — already wired (no action)

The spec lives at **`.do/app.yaml`** (the path App Platform auto-detects
when you connect the repo, so the web UI ingests the whole config — you
only enter the 4 secrets). It is already filled in and pushed:

| Field | Value |
|---|---|
| `services[web].github.repo`, `jobs[migrate].github.repo` | `NikolasHudson/statutes` |
| `databases[0].cluster_name` | `iowa-db` |

If you ever rename the repo or DB cluster, edit `.do/app.yaml` and push.

---

## 7. Generate the secrets

You'll paste these in step 9. Generate a Django key now:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Have ready:

| Secret | Get it from |
|---|---|
| `SECRET_KEY` | the command above |
| `OPENAI_API_KEY` | platform.openai.com — the assistant spends this |
| `VOYAGE_API_KEY` | voyageai.com — **required**; vector search embeds each query at request time. Issue a **fresh** one (see checklist). |
| `ANTHROPIC_API_KEY` | optional; console.anthropic.com — query expansion, no-op if unset |

---

## 8. Create the app

**Web UI (what you're using):** <https://cloud.digitalocean.com/apps> →
**Create App** → **GitHub** → pick `NikolasHudson/statutes`, branch
`main`. Because `.do/app.yaml` exists in the repo, App Platform reads it
and pre-fills the web service, the `migrate` job, the Valkey cache, the
`iowa-db` attachment, routes, health check, and all non-secret env vars.
Click through to **Create** — you set the secret values in step 9.

**CLI alternative:**

```bash
doctl apps create --spec .do/app.yaml
doctl apps list --format ID,Spec.Name,DefaultIngress
```

Either way, note the **ID** and **DefaultIngress** (your live URL,
`https://iowa-legal-corpus-XXXXX.ondigitalocean.app`):

```bash
APP_ID=<the-id>     # UI: app → Settings → App-level → the ID in the URL
```

This first build will run but the app will be **unhealthy until you set
the secrets** (no `SECRET_KEY` → the container can't start). That's
expected — continue to step 9. The Valkey cache is provisioned during this
first create.

---

## 9. Set the secret values, then redeploy

Secret-typed vars are intentionally empty in the spec. Set their values in
the UI (simplest and they're encrypted at rest):

1. <https://cloud.digitalocean.com/apps> → your app → **Settings**.
2. Component **web** → **Environment Variables** → **Edit** →
   fill `SECRET_KEY`, `OPENAI_API_KEY`, `VOYAGE_API_KEY`, and
   `ANTHROPIC_API_KEY` (optional) → **Save**.
3. Component **migrate** (the job) → set `SECRET_KEY` there too → **Save**.

Saving triggers a redeploy. (CLI alternative: `doctl apps update $APP_ID
--spec <spec-with-values>` — but that means putting secrets in a file, so
prefer the UI.)

**Lock the database to the app** (was open during the load):

```bash
doctl databases firewalls append "$DB_ID" --rule app:"$APP_ID"
# remove the temporary open access if one was added; verify:
doctl databases firewalls list "$DB_ID"
```

Watch the deploy:

```bash
doctl apps logs "$APP_ID" --type build  --follow   # image build
doctl apps logs "$APP_ID" --type deploy --follow   # PRE_DEPLOY migrate
doctl apps logs "$APP_ID" --type run    --follow   # gunicorn
```

The `migrate` job should print **"No migrations to apply."** (the dump
already included the schema + HNSW index). If it instead creates tables,
`DATABASE_URL` didn't resolve to the loaded cluster — recheck step 6.

---

## 10. Create the first admin user

```bash
doctl apps console "$APP_ID" web
# inside the container:
python manage.py createsuperuser
exit
```

Court Rules are already approved and searchable. Anything you ingest later
is `review_status=pending` until you approve it at `/admin/`.

---

## 11. Smoke test the live site

```bash
BASE=https://iowa-legal-corpus-XXXXX.ondigitalocean.app

curl -s $BASE/api/health                       # {"status": "ok"}
curl -s "$BASE/api/lookup/714.16" | head -c 300 # 401 (needs X-API-Key) = stack OK
open $BASE                                      # SPA loads over HTTPS
```

Then in the browser:

1. Register an account, log in.
2. Send a chat message — it should answer with source cards (this spends
   your server OpenAI key).
3. `/admin/` loads **with CSS** (confirms WhiteNoise static).

Optional cap check: in the UI set `CHAT_DAILY_USER_LIMIT=1`, send two
messages → second returns a 429 quota message, then restore the value.

---

## 12. Day-2 operations

**Deploy a change** — just push:

```bash
git push                       # main → App Platform auto-builds & deploys
# or force a redeploy without a code change:
doctl apps create-deployment "$APP_ID"
```

**Logs:** `doctl apps logs "$APP_ID" --type run --follow`

**Rollback:** UI → app → **Deployments** tab → pick a previous successful
deployment → **Rollback**. (Migrations are not auto-reverted; this app's
deploys are schema-stable, but keep it in mind.)

**Scale:** keep `instance_count: 1` until you've confirmed the chat quota
holds (it's Valkey-backed, so it *will* hold across instances — but verify
once before scaling). Change `instance_count` / `instance_size_slug` in
`.do/app.yaml`, push, redeploy.

**DB backups:** Managed Postgres takes daily backups automatically;
confirm/point-in-time settings in the DO panel under the cluster →
**Settings → Backups**.

---

## 13. Rough monthly cost

| Item | Plan | ~USD/mo |
|---|---|---|
| App Platform web (`basic-xs`, 1 instance) | basic | ~$5 |
| Managed Postgres (`db-s-1vcpu-2gb`) | | ~$30 |
| Managed Valkey (smallest) | | ~$15 |
| **Subtotal infra** | | **~$50** |
| OpenAI usage (chat) | metered | usage-based, capped by the quota envs |

The `CHAT_DAILY_USER_LIMIT` / `CHAT_MONTHLY_GLOBAL_LIMIT` envs are your
hard ceiling on OpenAI spend — tune them before launch.

---

## 14. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Build fails fetching repo | DO GitHub app not authorized for `statutes` (step 3), or `github.repo` slug wrong in `.do/app.yaml`. |
| Container won't start, `SECRET_KEY` error in run logs | Secret values not set yet (step 9), incl. on the **migrate** job. |
| Deploy fails health check; `DisallowedHost` in logs | App Platform health probe Host not in `ALLOWED_HOSTS`. Quick unblock: set `ALLOWED_HOSTS=*` (acceptable here — TLS terminates at the managed edge and CSRF is pinned via `CSRF_TRUSTED_ORIGINS`), then narrow later. |
| Infinite HTTPS redirect / "too many redirects" | Edge isn't forwarding `X-Forwarded-Proto`. App Platform does by default; if you fronted it with something else, ensure that header is set (settings honors `SECURE_PROXY_SSL_HEADER`). |
| migrate job creates tables instead of "No migrations" | `DATABASE_URL` not pointing at the loaded cluster — `databases[].cluster_name` wrong, or you loaded a different cluster (step 5/6). |
| Search returns nothing / 500 on vector path | `VOYAGE_API_KEY` unset or invalid — vector retrieval embeds the query live. |
| Chat: 401 for logged-in users | Cookie not first-party. We serve the SPA same-origin to avoid this; only happens if you split the frontend onto another domain. |
| Chat quota resets every deploy / not enforced | `REDIS_URL` unset or Valkey unreachable; counters fell back to per-process memory. Check the `iowa-cache` binding. |
| admin has no CSS | `collectstatic` didn't run — it's baked into the image build; check the build logs. |

---

## 15. Pre-launch checklist

- [ ] `migrate_db.sh` counts matched (31002 / 29062 / 29062).
- [ ] All four env secrets set on **web**, `SECRET_KEY` also on **migrate**.
- [ ] `migrate` job logged "No migrations to apply."
- [ ] `https://…/` loads the SPA; `/admin/` has CSS; HTTPS forced (http
      → 301). `doctl apps logs … --type run` shows no `DisallowedHost`.
- [ ] Logged-in chat works; anonymous `/api/chat` → 401; cap → 429;
      global ceiling → 503 (also covered by
      `apps/api/tests/test_chat_auth.py`).
- [ ] Database firewall locked to the app (`doctl databases firewalls
      list $DB_ID` shows only the app, no open `0.0.0.0/0`).
- [ ] **Rotate `VOYAGE_API_KEY`.** A real key is in `backend/.env`
      (gitignored — confirm it never entered history:
      `git log --all -p -- backend/.env` returns nothing). Issue a new key
      at voyageai.com, set it as the DO secret, revoke the old one.
- [ ] Managed Postgres daily backups confirmed in the DO panel.
- [ ] Disclaimer banner visible in the UI before real attorneys use it.
- [ ] `CHAT_DAILY_USER_LIMIT` / `CHAT_MONTHLY_GLOBAL_LIMIT` tuned to an
      OpenAI spend you're comfortable with.

---

## 16. Deferred (not blocking launch)

- **Custom domain:** DO panel → app → **Settings → Domains** → add domain,
  create the CNAME it shows. `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` use
  `${APP_DOMAIN}`, which follows the primary domain — no rebuild needed.
- **MCP server:** add as a second App Platform service on its own route
  once the API-key auth path is verified end to end (TASKS.md Phase 3).
- **`backend/data/raw/` → Spaces (S3):** the container filesystem is
  ephemeral, so prod ingestion won't keep its immutable audit trail until
  raw storage moves to object storage. Run ingestion locally against the
  managed DB until then.
- **Celery/Valkey worker** for scheduled diffs + embedding jobs.
