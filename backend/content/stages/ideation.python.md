## For Python/FastAPI projects

- **Scaffold a single `app/main.py` with one `FastAPI()` instance and a
  `/health` route early** — proving the framework boots is cheap and catches
  environment problems before you've invested in structure.
- **Pin your Python version** with a `.python-version` file (pyenv) or a note
  in the README; FastAPI and Pydantic behavior can shift across minor
  versions.
- **Sketch the data model as Pydantic `BaseModel` classes**, not just prose —
  a `schemas.py` with your 3-5 entities doubles as documentation and a
  contract for the API.
- **Decide sync vs. async up front.** FastAPI supports both, but blocking I/O
  inside an `async def` route silently stalls the whole event loop.
- **Use `httpx` for any outbound API calls** — it's the modern, free,
  async-friendly successor to `requests` and what this repo already uses to
  call Gemini.
