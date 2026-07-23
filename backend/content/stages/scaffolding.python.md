## For Python/FastAPI projects

- **Commit a real lockfile.** `pip freeze > requirements.txt` is the bare
  minimum; `pip-compile` (pip-tools) or `poetry`/`uv` give you a proper
  lockfile with hashes.
- **Structure as a package**: `app/main.py`, `app/routers/`,
  `app/services/`, `app/models.py` — this mirrors the layout used throughout
  this repo and keeps routes, business logic, and data access separable.
- **Use `pydantic-settings`** for a typed `Settings` class reading from
  `.env`, instead of scattering `os.getenv()` calls through the codebase.
- **Call `Base.metadata.create_all()` for local dev only** — it's fine for
  greenfield tables, but plan to introduce Alembic migrations before this
  becomes a multi-developer project with schema changes.
- **Add a one-command startup script** (a `dev.py` or `Makefile` target) that
  runs `uvicorn app.main:app --reload`.
