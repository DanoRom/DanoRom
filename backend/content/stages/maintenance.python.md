## For Python/FastAPI projects

- **Pin dependencies and update on a schedule.** `pip list --outdated`, or
  let Dependabot open PRs automatically against `requirements.txt`.
- **Monitor free-tier logs and uptime** (your host's built-in logs, or a
  free service like UptimeRobot) instead of waiting for user reports.
- **Watch the Gemini free-tier quota.** This app already falls back to the
  heuristic evaluator on any API failure — verify that fallback still fires
  correctly after touching `services/gemini.py`.
- **Introduce Alembic migrations** once schema changes need to survive
  without dropping data — `Base.metadata.create_all()` only adds new tables,
  it never alters existing ones.
- **Profile before optimizing.** Time slow endpoints (FastAPI middleware or
  simple `httpx` timing) before assuming which part is actually slow.
