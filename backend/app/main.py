from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import learning, projects

Base.metadata.create_all(bind=engine)

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
