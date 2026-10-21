# Deploying CraftProof on Render

CraftProof deploys as **two services**: a Python backend and a static frontend. Both are described
in [`render.yaml`](../render.yaml) at the repo root.

Live today:

| Service | URL |
|---|---|
| `craftproof-backend` | https://craftproof-backend.onrender.com |
| `craftproof-frontend` | https://craftproof-frontend.onrender.com |

---

## Before you start

Have these two values ready. Neither belongs in Git, which is why `render.yaml` marks them
`sync: false` — Render prompts for them instead of reading them from the repo.

| Secret | Where it comes from |
|---|---|
| `REMARKET_SALE_API_KEY` | The ReMarket team. Must be byte-identical to the key set on their server |
| `CRAFTPROOF_REMARKET_SYNC_KEY` | You generate it. Nobody else needs to know it |

Generate the sync key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

If `JWT_SECRET_KEY` has never been set on this service, generate one of those too. The backend
**refuses to start** without a secret of at least 32 characters, by design:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## Step 1 — Point Render at the right branch

This is the step that most often goes wrong, so read which case you are in.

Render reads `render.yaml` from whichever branch the **Blueprint** tracks. A `branch:` line
*inside* `render.yaml` controls which branch each **service** builds from. Those are two different
settings and they have to agree.

### If your services were created from the Blueprint

1. Open your Blueprint in the Render dashboard.
2. Settings → set the tracked branch to the branch you want to deploy.
3. Save. Render re-reads `render.yaml` from that branch and applies it.

The `branch:` lines already in `render.yaml` will then match, because they live on the same branch.

> **Why this order matters.** If the Blueprint still tracks `main`, Render reads `main`'s
> `render.yaml` and never sees a `branch:` line added on another branch. Nothing happens, and
> there is no error to tell you why.

### If your services were created manually

Set the branch on each service directly. Do this for **both** `craftproof-backend` and
`craftproof-frontend` — a backend on one branch and a frontend on another is a confusing bug to
chase.

1. Open the service → Settings → Build & Deploy.
2. Set **Branch** to the branch you want.
3. Save.

> A later Blueprint sync can overwrite a branch you set by hand, if `render.yaml` disagrees.
> Keep the two consistent.

---

## Step 2 — Set the secrets

On **`craftproof-backend`** → Environment → Add Environment Variable:

| Key | Value |
|---|---|
| `REMARKET_SALE_API_KEY` | the ReMarket key |
| `CRAFTPROOF_REMARKET_SYNC_KEY` | the one you generated |
| `JWT_SECRET_KEY` | only if it is not already set |

Everything else comes from `render.yaml` and needs no action.

Nothing goes on the frontend service. It gets the backend URL automatically through the
`fromService` block, and the ReMarket key is used only server-side — it must never reach a browser.

---

## Step 3 — Deploy

Render deploys on push to the tracked branch. To deploy immediately: open the service →
**Manual Deploy** → *Deploy latest commit*. Do the backend first, then the frontend.

First builds take a few minutes. The frontend build runs `npm install && npm run build`.

---

## Step 4 — Check it actually worked

Free instances sleep after inactivity, so the first request after a quiet period can take up to a
minute. That is a cold start, not a failure.

```bash
# 1. Backend is awake and serving its schema
curl -s -o /dev/null -w '%{http_code}\n' https://craftproof-backend.onrender.com/openapi.json

# 2. Both halves of the ReMarket credential arrived
curl -s https://craftproof-backend.onrender.com/integrations/remarket/status

# 3. A certificate verifies end to end
curl -s https://craftproof-backend.onrender.com/api/verify/KOODE0LL
```

Step 2 should report `"configured": true`. If it says `false`, one of the two ReMarket variables is
missing or empty.

Then open the frontend and check:

- `/marketplace` shows **Connected** rather than *Not configured*
- `/ledger` → **Publish a checkpoint** succeeds instead of erroring
- a certificate page loads and shows a green badge

---

## Step 5 — Import the first sales

The background poller only runs while the service is awake, and a free instance sleeps. So do not
rely on it. Trigger a sync by hand:

```bash
curl -X POST https://craftproof-backend.onrender.com/integrations/remarket/sync \
  -H "X-Integration-Key: <CRAFTPROOF_REMARKET_SYNC_KEY>"
```

Or sign in to the app, open **ReMarket** and press *Check for new sales*. That button uses your own
session, so the browser never holds the shared key.

For regular imports, point any external scheduler (cron-job.org, GitHub Actions, a Render cron job)
at that endpoint. Once every few hours is plenty.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Deploy succeeds but your changes are missing | The Blueprint tracks a different branch than you edited | Step 1 |
| Auth routes return `503 Auth unavailable` | `JWT_SECRET_KEY` missing or under 32 characters | Set a longer secret |
| `status` shows `configured: false` | A ReMarket variable is missing or empty | Step 2 |
| Sync returns `502 ReMarket rejected the sale API key` | The two sides hold different keys | Compare with the ReMarket team |
| Sync returns `502 ReMarket has no sale API key configured` | ReMarket's own server has no key set | Their side, not yours |
| Sync returns `401 Valid integration key required` | Wrong `X-Integration-Key` header | Check the value |
| Sync returns `503 ReMarket sync key is not configured` | `CRAFTPROOF_REMARKET_SYNC_KEY` unset on the backend | Step 2 |
| First request hangs for ~50s | Free instance cold start | Wait, then retry |
| Sales import but show as skipped | Listing title does not match the certificate title | Working as intended, see below |

A skipped sale is not a bug. The importer refuses to touch a certificate when the ReMarket listing
title disagrees with the piece title, so a wrong or guessed code cannot rewrite someone else's
record. Skipped sales are retried on every later sync.

---

## Known limits of this deployment

Stated plainly, because they matter for anything beyond a demo.

**Storage is ephemeral.** No disk is declared in `render.yaml`, so the filesystem resets on every
redeploy. The SQLite database, the anchor journal and the ReMarket signing key are all lost
together, and the app reseeds itself with demo data on next boot. Accounts and certificates created
between deploys do not survive.

To fix it properly you need a paid instance type with a disk. `render.yaml` carries the `disk:`
block and the five paths to restore, commented out, next to an explanation.

**Losing the signing key is handled, not ignored.** When the key file disappears but the database
survives, a new key is generated. The importer registers it as a *new signer identity* rather than
overwriting the old one, so records signed by the previous key keep verifying. Overwriting would
have made every earlier import report `ALTERED RECORD` to the public.

**The poller only runs while the service is awake.** Covered in step 5.

**ReMarket's storage is ephemeral too.** Their orders live in SQLite on a free instance. Both teams
should sort persistence before treating either history as durable.

---

## When you merge the branch

If `render.yaml` carries `branch:` lines pinning a feature branch, change them to `main` or delete
them at merge time. Otherwise `main` keeps redeploying from a branch that has stopped moving, and
the deployed site silently falls behind the code you are writing.

Both lines carry a comment saying so.
