from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Defaults to SQLite so local development costs nothing and needs no services.
    # Point at PostgreSQL in production, e.g.:
    #   DATABASE_URL=postgresql+pg8000://devplatform:devplatform@localhost:5432/devplatform
    database_url: str = f"sqlite:///{BASE_DIR / 'devplatform.db'}"

    # Google Gemini free tier. When empty, the engine falls back to the
    # built-in heuristic evaluator so the platform never incurs charges.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Where uploaded / templated project trees are stored.
    storage_dir: Path = BASE_DIR / "storage"

    content_dir: Path = BASE_DIR / "content"

    cors_origins: str = "http://localhost:3000"

    app_version: str = "1.1.0"

    # Per-client sliding-window API rate limit. Set to 0 to disable.
    # Protects the API when it is exposed publicly (e.g. via a share tunnel).
    rate_limit_per_minute: int = 120

    class Config:
        env_file = ".env"


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
