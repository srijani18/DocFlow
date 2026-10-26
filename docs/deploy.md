# Deploying DocFlow

Everything runs on free tiers, with no credit card. Do the steps in order: later steps paste in values from earlier ones. Keep a scratch note (in a password manager, **not** in the repo) for the values marked 📋.

| # | Service | Purpose | Needed for |
|---|---|---|---|
| 1 | GitHub | Code, CI, branch protection | Phase 0 |
| 2 | Supabase | Postgres + pgvector, Auth, file storage (ADR-0007) | Phase 0 (database, auth), Phase 1 (storage) |
| 3 | Render | API + worker | Phase 0 |
| 4 | Vercel | Web app | Phase 0 |
| 5 | cron-job.org | Keep-alive pings | Phase 0 |
| 6 | BYOK master key; Google AI Studio, Groq, OpenRouter | Encrypting customers' AI keys; your own keys for evals | Phase 2 |
| 7 | Langfuse, Sentry | Traces, errors | Phase 5 (you can create them now) |

Region everywhere: **Singapore** (overview A5).

---

## 1. GitHub

1. Create an **empty public** repository, for example `docflow`, with no README, licence or `.gitignore` (the repo already has them).
   Public matters: branch protection on private repos needs a paid plan, and the portfolio is meant to be public anyway.
2. Push the local repository (I can run this step once the repo exists):
   ```bash
   git remote add origin git@github.com:<you>/docflow.git
   git push -u origin main
   git push -u origin p0/scaffold
   ```
3. Open a pull request from `p0/scaffold` to `main`. CI runs. Wait for **`ci-ok`** to go green.
4. **Settings → Branches → Add branch ruleset** (or classic branch protection) for `main`:
   - Require a pull request before merging.
   - Require status checks to pass, and add **`ci-ok`** (it appears in the list once CI has run at least once).
   - Block force pushes.
5. Merge the pull request (squash).
6. Optional: `brew install gh && gh auth login`, so I can open PRs and read CI results from the terminal.

## 2. Supabase (database, auth, storage)

One project holds everything (ADR-0007).

### 2a. Project

1. Sign up at <https://supabase.com>. Create an organization on the **Free** plan.
2. **New project:** name `docflow`, region **Southeast Asia (Singapore)**.
   - **Database password:** a long random password using **letters and digits only**, so it needs no URL-encoding in the connection string. 📋 (password manager)
3. **Project Settings → Infrastructure:** note the **Postgres major version**. If it isn't **17**, tell me, so I can match `docker-compose.yml` and CI (overview A7).

### 2b. Database connection

1. Click **Connect** (top bar) → **Session pooler**.
   - Use this mode, not "Direct connection" (IPv6-only on Free, and Render can't reach IPv6) and not "Transaction pooler" (meant for serverless). See ADR-0007.
2. Copy the URI. It looks like `postgresql://postgres.<ref>:[YOUR-PASSWORD]@aws-<n>-ap-southeast-1.pooler.supabase.com:5432/postgres`.
3. Put your database password in place of `[YOUR-PASSWORD]`, and append `?sslmode=require`. 📋 `DATABASE_URL` (**secret**: Render and local `.env` only)

### 2c. Turn off the Data API

DocFlow never uses Supabase's auto-generated REST API (PostgREST). With it on, tables in `public` are reachable by anyone holding the publishable key, which ships in the browser.

1. **Project Settings → Data API** (or **Integrations → Data API**): turn **Enable Data API** **off**.
2. Check: `curl -s https://<ref>.supabase.co/rest/v1/ -H "apikey: <publishable key>"` no longer returns an API description.

DocFlow's tables also live in their own `docflow` schema, and the baseline migration revokes the browser roles' access to it. These are extra layers behind the Data API switch.

### 2d. API keys

On **Project Settings → API Keys**:

- Copy the **publishable** key (`sb_publishable_…`). 📋 `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
- Create or copy a **secret** key (`sb_secret_…`). 📋 `SUPABASE_SECRET_KEY` (**secret**: Render and local `.env` only)
- Copy the project URL `https://<ref>.supabase.co`. 📋 `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL`
- Do **not** use the legacy `anon` / `service_role` keys.

### 2e. JWT signing keys

On **Project Settings → JWT Keys**:

- The **current key** must be **ECC (P-256)** or **RSA**. These are asymmetric, and DocFlow verifies them through JWKS.
- If the current key is **Legacy HS256 (shared secret)**: click **Migrate JWT secret**, then **Rotate keys**, so that an asymmetric key becomes current. The backend rejects HS256 tokens by design (F1 plan §4.1).
- Check: `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` lists at least one key.

### 2f. Auth settings

1. **Authentication → Sign In / Providers → Email:**
   - Enable the Email provider.
   - Turn **Confirm email OFF**. Supabase's built-in email sender only reaches your own team (F1 decision Q1).
   - Set **Minimum password length** to **10**.
2. **Authentication → URL Configuration:**
   - **Site URL:** your Vercel production URL (from step 4; come back to this).
   - **Redirect URLs:** `http://localhost:3000/**`, `https://<your-vercel-production-domain>/**` and `https://*-<your-vercel-scope>.vercel.app/**`.

### 2g. Storage buckets

For Phase 1, but quick to do now. Go to **Storage → New bucket** and create two: `documents` (production) and `documents-dev` (local). For each:

- **Public bucket:** OFF (private).
- **Restrict file upload size:** ON, **10 MB**.
- **Allowed MIME types:** `application/pdf, image/png, image/jpeg`.
- **Add no storage policies.** Only the backend (with the secret key) grants access (ADR-0004).

## 3. Render (API)

1. Sign up at <https://render.com> with **GitHub**, and allow access to the `docflow` repo.
2. **New → Blueprint** → choose the repo, branch `main`. Render reads `render.yaml` and proposes the `docflow-api` service (free, Singapore).
3. Fill in the prompted values:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | 📋 Supabase **session pooler** URI (step 2b) |
   | `SUPABASE_URL` | 📋 `https://<ref>.supabase.co` (step 2d) |
   | `CORS_ALLOWED_ORIGINS` | Your Vercel production URL, e.g. `https://docflow-web.vercel.app` (fill in after step 4, then redeploy) |
   | `CORS_ALLOWED_ORIGIN_REGEX` | `^https://docflow-web-[a-z0-9-]+-<your-vercel-scope>\.vercel\.app$` (preview deployments, overview A1) |

   Phase 1 adds `SUPABASE_SECRET_KEY` and `SUPABASE_STORAGE_BUCKET=documents`; Phase 2 adds `BYOK_MASTER_KEYS` (§6). Add each under **Environment** when its feature ships; `.env.example` always lists the current set.
4. **Apply.** The first deploy runs immediately. Later deploys wait for `ci-ok` on `main` (`autoDeployTrigger: checksPass`).
5. Check, using the service URL from the dashboard (📋 `https://docflow-api-xxxx.onrender.com`):
   - `GET /healthz` returns `{"status":"ok"}`.
   - `GET /readyz` returns `{"status":"ok","database":"ok"}`. This also proves the migrations ran against Supabase.
   - The logs show `Running upgrade -> 0001`, then `worker_started`.
   - In Supabase's **Table Editor**, switch the schema selector to `docflow`: it contains `alembic_version`, and nothing new is in `public`.
6. Don't create any other free Render services in this workspace. The keep-alive ping uses about 720 of the 750 free hours a month.

## 4. Vercel (web)

1. Sign up at <https://vercel.com> with **GitHub** (Hobby plan).
2. **Add New → Project** → import the `docflow` repo.
   - **Root Directory:** `apps/web`. The framework (Next.js) and pnpm are detected automatically; `vercel.json` sets the install command.
3. **Environment Variables** (all environments):

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | 📋 Render service URL (no trailing slash) |
   | `NEXT_PUBLIC_SUPABASE_URL` | 📋 Supabase project URL (used from F1) |
   | `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | 📋 Supabase publishable key (used from F1) |

   **Never** put the Supabase secret key, the database URL or LLM keys on Vercel.
4. **Deploy.** Note the production domain 📋 and your Vercel scope (the team or user slug in preview URLs).
5. Go back and finish **Supabase step 2f** (Site URL, redirect URLs) and **Render step 3** (`CORS_ALLOWED_ORIGINS`, `CORS_ALLOWED_ORIGIN_REGEX`). Then **Manual Deploy → Deploy latest commit** on Render.
6. Check: the production URL shows "DocFlow" and **"API: ok"**. If it says "unavailable", see Troubleshooting.

## 5. cron-job.org (keep-alive)

1. Sign up at <https://cron-job.org> (free).
2. **Job 1 – keep-alive for the API and the database:**
   - URL `https://<render-service>.onrender.com/readyz`, **every 10 minutes**, method GET.
   - `/readyz` runs a real query, so this one job keeps the Render service awake and the Supabase project active (a paused project would take the database, auth and storage down together). It also alerts you when the database is unreachable.
3. **Job 2 – Supabase backup ping:**
   - URL `https://<ref>.supabase.co/storage/v1/bucket`, **weekly**, method GET, header `apikey: <publishable key>`.
   - It keeps the project active even if Render is down for a week. An empty list `[]` as the response is expected (there are no policies).
4. Enable failure notifications by email on both jobs.

## 6. AI keys: bring your own (F15, ADR-0008)

DocFlow has **no platform AI key**. Each workspace's admin connects their own Gemini, Groq or OpenRouter key in **DocFlow → Settings**. Those keys are encrypted with a master key that only the server has.

1. **Generate the master key:** run `make byok-key` and copy the output (`v1:…`).
2. Put it in **Render → Environment** as `BYOK_MASTER_KEYS` (**secret**), and in your password manager. If you lose it, every workspace has to re-enter its keys.
3. **Rotation:** append a new key, `BYOK_MASTER_KEYS=v1:…,v2:…`. New saves use v2 and old keys still decrypt. Remove v1 only once every key has been re-saved.
4. **Your own keys, for evals only (F11):** they never go on Render or Vercel.

| Provider | Where | Used by |
|---|---|---|
| Google Gemini | <https://aistudio.google.com/apikey> (no billing) | Settings in the app; `GEMINI_API_KEY` for evals |
| Groq | <https://console.groq.com/keys> | Settings in the app; `GROQ_API_KEY` for evals |
| OpenRouter | <https://openrouter.ai/keys> (50 free requests a day) | Settings in the app |

For CI evals, add `GEMINI_API_KEY` and `GROQ_API_KEY` as **GitHub Actions secrets**. Free tiers may train on what they receive: evals use only public or synthetic documents.

## 7. Langfuse and Sentry (Phase 5, optional now)

- **Langfuse Cloud** (<https://cloud.langfuse.com>, free Hobby plan): create project `docflow`. Keys: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`.
- **Sentry** (<https://sentry.io>, free Developer plan): create a Python (FastAPI) project. Key: `SENTRY_DSN`.

---

## Local `.env`

`make setup` copies `.env.example` to `.env`. The defaults already work for local development against Docker Postgres; your local database is never the Supabase one. Add your own values as features need them: Supabase URL and keys (F1), and `documents-dev` as the bucket (Phase 1). `BYOK_MASTER_KEYS` is generated with `make byok-key`. Your AI keys go into the app's Settings page, not `.env`.

## Rolling back

- **API:** Render → `docflow-api` → **Events** → pick the last good deploy → **Rollback**.
  - This is safe because migrations follow expand/contract (constitution §7.2): the previous release still works with the newer schema.
  - Never run `alembic downgrade` against production unless that migration's PR says it's safe.
  - Supabase Free has **no automatic backups** (ADR-0007). All data is synthetic, and that risk is accepted.
- **Web:** Vercel → Deployments → previous production deployment → **Instant Rollback**.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| The first request takes about a minute | Render is waking up from idle (free tier). This is expected, and the keep-alive job prevents it. |
| `/readyz` returns 503 `database-unavailable` | A wrong `DATABASE_URL`: the password wasn't put in place of `[YOUR-PASSWORD]`, the direct connection was used instead of the session pooler, or the project is paused (restore it in the Supabase dashboard). |
| Migrations fail with `permission denied` or `extension "vector" is not available` | The URL user must be `postgres.<ref>` (session pooler), not a custom role. |
| The web app shows "API: unavailable", and the browser console shows a CORS error | `CORS_ALLOWED_ORIGINS` doesn't exactly match the Vercel URL (scheme, no trailing slash). Redeploy Render after changing it. |
| The Render deploy never starts after a merge | `ci-ok` didn't pass on `main`, or the change was outside `apps/api/**` and `schemas/**` (build filter). |
| The Vercel build is skipped | Nothing changed under `apps/web` (the `ignoreCommand` in `vercel.json`). Use **Redeploy** to force a build. |
