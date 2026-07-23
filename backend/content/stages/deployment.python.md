## For Python/FastAPI projects

- **Deploy on a free-tier web service** (e.g. Render) with the root
  directory set to `backend/`, build command
  `pip install -r requirements.txt`, and start command
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. See this repo's
  `render.yaml` and `DEPLOYMENT.md` for a ready-made blueprint.
- **Use a free managed Postgres** (Neon, Supabase) instead of SQLite once
  more than one person touches the data — SQLite is great for local dev,
  risky once the filesystem isn't durable.
- **Set `CORS_ORIGINS` to your deployed frontend's exact URL.** The
  `CORSMiddleware` setup here reads it straight from `Settings`, so no code
  change is required.
- **Never commit `.env`.** Set `GEMINI_API_KEY` and `DATABASE_URL` as
  environment variables in the host's dashboard instead.
- **Expect cold starts on free tiers.** Services often spin down on idle —
  fine for a side project, worth knowing about before a live demo.
