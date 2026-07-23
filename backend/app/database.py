import ssl
from urllib.parse import urlsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif settings.database_url.startswith("postgresql"):
    host = urlsplit(settings.database_url).hostname
    if host and host not in ("localhost", "127.0.0.1"):
        # pg8000 doesn't read `sslmode` from the URL like psycopg does, so
        # managed Postgres providers (Neon, Supabase, Render, ...) need an
        # explicit ssl_context or the connection is rejected. Local/docker
        # Postgres stays plaintext since it never leaves the machine.
        connect_args = {"ssl_context": ssl.create_default_context()}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
