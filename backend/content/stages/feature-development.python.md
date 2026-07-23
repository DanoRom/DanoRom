## For Python/FastAPI projects

- **Adopt `pytest` with `TestClient`** (or `httpx.AsyncClient` for async
  routes) to test endpoints without a running server — it's built into
  FastAPI's own documentation as the recommended pattern.
- **Cover the money paths first**: the routers driving your core
  create/evaluate/update flows, not incidental utility functions.
- **Use dependency overrides** (`app.dependency_overrides[get_db] = ...`) to
  swap in a test database instead of hitting real data during tests.
- **Keep routers thin.** Business logic belongs in `services/`; routers
  should mostly validate input and call a service function — this makes both
  layers easier to test in isolation.
- **Run `ruff`** to catch unused imports and obvious bugs continuously,
  rather than saving all cleanup for the testing stage.
