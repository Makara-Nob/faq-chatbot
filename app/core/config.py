"""
Configuration.

JAVA: @ConfigurationProperties(prefix="app") + application-{profile}.yml
PYTHON: one Settings class. pydantic-settings reads .env and the real
        environment, validates types, and fails at STARTUP if something is
        wrong - not at 3am when the first request hits that code path.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- environment -------------------------------------------------------
    env: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = False

    # --- security ----------------------------------------------------------
    # NEVER hardcode this. Generate with:
    #   python -c "import secrets; print(secrets.token_urlsafe(64))"
    secret_key: str = Field(default="dev-only-insecure-key-change-me", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15        # short. it cannot be revoked.
    refresh_token_days: int = 7           # long. it CAN be revoked (see models).

    # --- database ----------------------------------------------------------
    # dev  : sqlite:///./app.db
    # prod : postgresql+psycopg://user:pass@host:5432/dbname
    database_url: str = "sqlite:///./app.db"

    # --- http --------------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:3000"]
    rate_limit_per_minute: int = 60

    # --- first admin -------------------------------------------------------
    # If both are set, the app creates/promotes this admin at startup.
    # Handy in dev and in docker-compose; in production prefer a secrets
    # manager and run scripts/create_admin.py as a one-off deploy step, so a
    # long-lived password is not sitting in a file on disk.
    admin_username: str | None = None
    admin_password: str | None = None
    seed_admin: bool = True          # set false to disable the startup seed

    # --- document ingestion ------------------------------------------------
    storage_dir: str = "./storage"
    max_upload_bytes: int = 1_048_576        # 1 MB
    max_documents_per_user: int = 20
    chunk_size: int = 500                    # characters per chunk
    chunk_overlap: int = 50                  # carried between chunks for context
    allowed_extensions: list[str] = [".txt", ".md", ".faq"]

    # --- chatbot -----------------------------------------------------------
    use_rag: bool = False
    anthropic_api_key: str | None = None

    @field_validator("secret_key")
    @classmethod
    def _reject_default_secret_in_prod(cls, v: str, info) -> str:
        # info.data holds the fields validated so far
        if info.data.get("env") == "prod" and v.startswith("dev-only"):
            raise ValueError("SECRET_KEY must be set in production")
        return v

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    """
    JAVA: a singleton @Bean.
    @lru_cache means this runs once; every later call returns the same object.
    Using it as a FastAPI dependency lets tests override it.
    """
    return Settings()
