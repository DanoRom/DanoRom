from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from .config import settings
from .database import Base, engine
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

app = FastAPI(title="Developer Platform API", version="0.1.0")

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
