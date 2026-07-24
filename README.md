# Developer Platform

A platform that evaluates the build stage of a developer's application and provides
branched pathways to completion. See [CLAUDE.md](CLAUDE.md) for the project charter.

## Architecture

```
frontend/   Next.js (React, TypeScript) — dashboard, pathways, learning center
backend/    FastAPI — project management, directory scanner, Gemini evaluation engine
```

- **Database:** PostgreSQL (via `docker-compose up db`); defaults to SQLite locally so
  development is zero-cost with no services required.
- **AI Engine:** Google Gemini API (free tier). With no `GEMINI_API_KEY` set, a built-in
  heuristic evaluator runs instead — the platform never requires a paid service.
- **Design system:** Midnight Blue `#191970` backgrounds, Royal Purple `#7851A9` /
  Blue `#0000FF` navigation & cards, Ferrari Red `#FF2800` CTAs, Oak Brown `#806517` borders.

## Running locally

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optionally add GEMINI_API_KEY / DATABASE_URL
python dev.py
```

`dev.py` runs uvicorn with auto-reload but excludes the `storage/` directory, so
project uploads don't restart the server. (Equivalent to
`uvicorn app.main:app --reload --reload-exclude "storage/*"`.)

API at http://localhost:8000 (docs at `/docs`).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at http://localhost:3000.

### PostgreSQL (optional)

```bash
docker compose up -d db
# then in backend/.env:
# DATABASE_URL=postgresql+pg8000://devplatform:devplatform@localhost:5432/devplatform
```

## Quick share (temporary link, no deployment)

To hand a friend a link without deploying anywhere, on Windows run
`scripts\share.ps1` from the repo root (PowerShell). One window, no manual
URL copy-pasting: it starts both Cloudflare quick tunnels, wires the URLs
into the frontend and backend automatically, and prints the link to send.
Requires `cloudflared` (`winget install Cloudflare.cloudflared`) and the
usual one-time `venv`/`npm install` setup. See the script's header comment
for exact prerequisites and how to stop everything.

## Deploying

Free-tier deployment (Render for the backend, Neon for Postgres, Vercel for
the frontend) is fully documented step by step in
[DEPLOYMENT.md](DEPLOYMENT.md). The repo also includes `render.yaml`, a
[Render Blueprint](https://render.com/docs/blueprint-spec) that provisions
the backend as a free web service in one click.

## Core features

- **Project Management** — start a new project from a template, upload an existing
  repo as a `.zip`, or import a public GitHub repo by URL. Owned projects can be
  deleted from the project page.
- **Stage Evaluation** — the backend scans the project tree for artifacts and
  dependencies and passes the report to Gemini, which classifies the stage
  (ideation → scaffolding → feature-development → testing → deployment → maintenance).
  Runs on the free Gemini tier, with a zero-cost heuristic fallback when no
  `GEMINI_API_KEY` is set.
- **Branching Pathways** — a visual, step-by-step branch of the next logical
  development actions. Choose a path to turn it into a persistent checklist with a
  progress bar; completing every step unlocks the next evaluation. Pathways can be
  exported as a markdown checklist.
- **AI Step Coach** — a "🎓 Coach me" button on every step of the chosen path asks
  Gemini for guidance grounded in the project's actual file tree: concrete actions,
  real paths and commands, and a definition of done.
- **Re-upload & Diff-Aware Re-evaluation** — upload an updated `.zip` at any time;
  the next evaluation reports exactly what changed (`+ tests detected`, `+12 files`,
  …) and how it moved the stage.
- **Progress Timeline** — the full evaluation history per project, with stages,
  confidence, engines, and change chips.
- **File-Tree Explorer** — see the tree the scanner saw, with tests/CI/Docker
  highlighted and missing artifacts flagged.
- **Dashboard Stats** — project totals, evaluations, completed steps, and a stage
  distribution bar.
- **Learning Center** — contextual markdown documentation loaded for the detected
  stage, with Python/TypeScript-specific addenda and a per-stage quiz ("Stage
  mastered" badge on passing).
- **Accounts** — optional username/password accounts (stdlib PBKDF2, bearer-token
  sessions). Owned projects are private to their owner; everything also works
  logged-out for ownerless projects.
