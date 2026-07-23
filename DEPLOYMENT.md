# Deploying the Developer Platform for $0

This guide gets the app running in production using only free tiers:
**Render** (backend), **Neon** (Postgres), and **Vercel** (frontend). No step
in this guide requires a credit card or paid plan.

Total time: ~15-20 minutes.

---

## 1. Backend on Render (free web service)

### Option A — one-click via the Blueprint (recommended)

This repo includes `render.yaml` at the root, a
[Render Blueprint](https://render.com/docs/blueprint-spec) that describes the
API service for you.

1. Push this repo to GitHub (if you haven't already).
2. In the [Render dashboard](https://dashboard.render.com/), click
   **New > Blueprint**.
3. Connect your GitHub account and select this repository. Render detects
   `render.yaml` automatically.
4. Render will show one service to create: `developer-platform-api`
   (plan: **Free**, root directory `backend/`). Click **Apply**.
5. The blueprint declares `GEMINI_API_KEY`, `DATABASE_URL`, and
   `CORS_ORIGINS` as env vars but leaves their values for you to fill in
   (`sync: false` means "don't store this in the blueprint file"). You'll set
   real values in step 2 and step 4 below — for now you can leave them blank
   and the app will fall back to SQLite and the free heuristic evaluator.
6. Click **Create Web Service**. The first build takes a few minutes; note
   the resulting URL, e.g. `https://developer-platform-api.onrender.com`.

### Option B — manual free web service (no blueprint)

1. **New > Web Service** in the Render dashboard, connect the repo.
2. **Root Directory:** `backend`
3. **Runtime:** Python 3
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. **Instance Type:** Free
7. Create the service, then add the environment variables from step 2 below.

> Render's free web services spin down after ~15 minutes of inactivity and
> take a few seconds to wake back up on the next request. That's fine for a
> side project or portfolio piece; just don't rely on it for anything
> latency-sensitive.

---

## 2. PostgreSQL on Neon (free tier)

SQLite (the default) is fine for a solo demo, but a real deployment should
use Postgres so data survives redeploys.

1. Create a free account at [neon.tech](https://neon.tech) and create a new
   project (pick any region close to your Render service).
2. On the project dashboard, copy the **connection string**. Neon gives you
   something like:

   ```
   postgresql://alice:AbC123@ep-cool-lake-12345.us-east-2.aws.neon.tech/devplatform?sslmode=require
   ```

3. **This app uses the `pg8000` driver, not `psycopg2`**, so the URL needs
   the `+pg8000` suffix after `postgresql`, and the `?sslmode=require` query
   param has to be dropped (pg8000 doesn't understand it — see the note
   below). Rewrite the copied URL to:

   ```
   postgresql+pg8000://alice:AbC123@ep-cool-lake-12345.us-east-2.aws.neon.tech/devplatform
   ```

4. In Render, open your service's **Environment** tab and set:

   | Key            | Value                                                        |
   |----------------|---------------------------------------------------------------|
   | `DATABASE_URL` | the rewritten `postgresql+pg8000://...` URL from step 3       |

5. **About TLS:** Neon requires TLS on every connection, but `pg8000` (unlike
   `psycopg2`) does not read `sslmode` from the URL — it needs an explicit
   `ssl_context` passed as a connection argument, or the connection is
   refused. **This is already handled for you:** `backend/app/database.py`
   automatically attaches a default TLS `ssl_context` to the connection
   whenever `DATABASE_URL` is a `postgresql://` URL whose host isn't
   `localhost`/`127.0.0.1`. You don't need to change any code — just set
   `DATABASE_URL` and redeploy (Render redeploys automatically when you save
   an environment variable).
6. Redeploy the backend (Render does this automatically after an env var
   change) and confirm it started cleanly by checking
   `https://<your-render-url>/api/health` returns `{"status":"ok"}`.

---

## 3. Frontend on Vercel (free Hobby tier)

1. Create a free account at [vercel.com](https://vercel.com) and click
   **Add New > Project**.
2. Import the same GitHub repository.
3. When configuring the project:
   - **Root Directory:** `frontend`
   - **Framework Preset:** Next.js (auto-detected)
4. Add an environment variable:

   | Key                     | Value                                                |
   |--------------------------|-------------------------------------------------------|
   | `NEXT_PUBLIC_API_URL`   | your Render backend URL, e.g. `https://developer-platform-api.onrender.com` |

5. Click **Deploy**. Vercel builds and gives you a URL like
   `https://your-project.vercel.app`. Every future push to `main` redeploys
   automatically, and every pull request gets its own free preview URL.

---

## 4. Point CORS at the deployed frontend

The backend only accepts browser requests from origins listed in
`CORS_ORIGINS` (see `backend/app/config.py` and the `CORSMiddleware` setup in
`backend/app/main.py`).

1. Back in the Render dashboard, open the backend service's **Environment**
   tab.
2. Set `CORS_ORIGINS` to your Vercel URL, e.g.:

   ```
   CORS_ORIGINS=https://your-project.vercel.app
   ```

   Use a comma-separated list if you need more than one origin (e.g. a
   preview URL and the production URL).
3. Save — Render redeploys the service automatically.

---

## Final checklist

- [ ] Backend deployed on Render (free plan) and `/api/health` returns `{"status":"ok"}`
- [ ] Neon Postgres project created and `DATABASE_URL` set to the `postgresql+pg8000://...` form (no `sslmode` query param)
- [ ] Backend redeployed after setting `DATABASE_URL` and it started without errors
- [ ] Frontend deployed on Vercel (free Hobby tier) with `NEXT_PUBLIC_API_URL` pointing at the Render URL
- [ ] `CORS_ORIGINS` on Render updated to the Vercel URL
- [ ] Opening the Vercel URL loads the dashboard and can create/evaluate a project without CORS or network errors

## Cost note

Every service used here — Render's free web service plan, Neon's free
Postgres tier, and Vercel's free Hobby tier — has a genuine $0 tier with no
credit card required to start. The app itself also runs at $0 without a
`GEMINI_API_KEY` (it falls back to the built-in heuristic evaluator). Total
cost for this deployment: **$0/month**.

Keep in mind free tiers have limits (Render free services spin down when
idle; Neon free projects have storage and compute caps; Vercel Hobby is for
non-commercial use) — fine for personal projects and portfolios, worth
reviewing before scaling up.
