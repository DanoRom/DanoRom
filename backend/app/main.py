from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from .config import settings
from .database import Base, engine
from .ratelimit import SlidingWindowRateLimiter
from .routers import auth, coach, learning, projects, stats

Base.metadata.create_all(bind=engine)


def _migrate() -> None:
    """Adds columns introduced after the initial release to existing databases."""
    table_additions = {
        "evaluations": {
            "chosen_branch": "INTEGER DEFAULT -1",
            "completed_steps_json": "TEXT DEFAULT '[]'",
            "signals_json": "TEXT DEFAULT '{}'",
            "changes_json": "TEXT DEFAULT '[]'",
        },
        "projects": {
            "owner_id": "INTEGER NULL",
        },
    }
    with engine.begin() as conn:
        for table, additions in table_additions.items():
            columns = {c["name"] for c in inspect(engine).get_columns(table)}
            for name, ddl in additions.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


_migrate()

app = FastAPI(title="Developer Platform API", version=settings.app_version)

_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_minute)
_RATE_LIMIT_EXEMPT = {"/api/health", "/api/version"}


def _client_key(request: Request) -> str:
    """Best-effort real client identity. Behind a Cloudflare tunnel the
    origin socket is always localhost, so prefer the forwarded headers."""
    forwarded = request.headers.get("x-forwarded-for", "")
    return (
        request.headers.get("cf-connecting-ip")
        or (forwarded.split(",")[0].strip() if forwarded else "")
        or (request.client.host if request.client else "unknown")
    )


# Registered before CORSMiddleware so that CORS ends up the *outer* layer:
# Starlette runs the most recently added middleware first, and a 429 returned
# from here still has to pass back out through CORS to keep its headers.
# Without them the browser hides the status and reports only "Failed to fetch".
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path = request.url.path
    if (
        settings.rate_limit_per_minute > 0
        and request.method != "OPTIONS"  # never throttle CORS preflights
        and path.startswith("/api/")
        and path not in _RATE_LIMIT_EXEMPT
        and not _limiter.allow(_client_key(request))
    ):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded — slow down a moment and try again."},
        )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(learning.router)
app.include_router(coach.router)
app.include_router(stats.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/version")
def version():
    return {
        "version": settings.app_version,
        "engine": "gemini" if settings.gemini_api_key else "heuristic",
    }
