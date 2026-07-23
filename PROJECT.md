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

## Deploying

Free-tier deployment (Render for the backend, Neon for Postgres, Vercel for
the frontend) is fully documented step by step in
[DEPLOYMENT.md](DEPLOYMENT.md). The repo also includes `render.yaml`, a
[Render Blueprint](https://render.com/docs/blueprint-spec) that provisions
the backend as a free web service in one click.

## Core features

- **Project Management** — start a new project from a template or upload an existing
  repo as a `.zip`.
- **Stage Evaluation** — the backend scans the project tree for artifacts and
  dependencies and passes the report to Gemini, which classifies the stage
  (ideation → scaffolding → feature-development → testing → deployment → maintenance).
- **Branching Pathways** — a visual, step-by-step branch of the next logical
  development actions.
- **Learning Center** — contextual markdown documentation loaded for the detected stage.
