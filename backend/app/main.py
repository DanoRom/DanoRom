from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from .config import settings
from .database import Base, engine
from .routers import learning, projects

Base.metadata.create_all(bind=engine)


def _migrate() -> None:
    """Adds columns introduced after the initial release to existing databases."""
    columns = {c["name"] for c in inspect(engine).get_columns("evaluations")}
    additions = {
        "chosen_branch": "INTEGER DEFAULT -1",
        "completed_steps_json": "TEXT DEFAULT '[]'",
    }
    with engine.begin() as conn:
        for name, ddl in additions.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE evaluations ADD COLUMN {name} {ddl}"))


_migrate()

app = FastAPI(title="Developer Platform API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(learning.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
