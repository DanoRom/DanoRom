## For Python/FastAPI projects

- **Add GitHub Actions.** A `.github/workflows/ci.yml` running
  `pip install -r requirements.txt && pytest` on every push — the free tier
  comfortably covers a project this size.
- **Lint and format with `ruff`** (`ruff check .` and `ruff format .`) — one
  fast tool replaces flake8, isort, and black.
- **Containerize with a `Dockerfile`** built on an official
  `python:3.12-slim` base image, running as a non-root user.
- **Externalize all config through `pydantic-settings`**, never hardcode a
  `DATABASE_URL` or API key — extend this repo's `Settings` class rather than
  reading `os.environ` directly.
- **Keep `/api/health` meaningful** (already present here) and make sure CI
  fails loudly, not silently, on a broken build.
