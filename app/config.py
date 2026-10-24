"""Central application configuration.

All configuration is sourced from environment variables (or a .env file in
development). Nothing environment-specific is hard-coded so the same image
can run in dev, staging, and production by changing env vars only.
"""
from functools import lru_cache
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "FlowDesk API"
    ENVIRONMENT: Literal["development", "test", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --- Security ---
    SECRET_KEY: str = Field(..., description="Used to sign JWTs. Must be set in production.")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ALGORITHM: str = "HS256"
    PASSWORD_MIN_LENGTH: int = 8

    # --- Database ---
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/flowdesk"
    )
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10

    # --- CORS ---
    # Stored as a raw comma-separated string to avoid pydantic-settings'
    # default JSON decoding of list-typed env vars; use `cors_origins`
    # (the property below) to get the parsed list.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # --- Rate limiting ---
    RATE_LIMIT_PER_MINUTE: int = 120

    # --- File uploads ---
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 15
    ALLOWED_UPLOAD_EXTENSIONS: List[str] = [
        ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".docx", ".xlsx", ".csv", ".txt", ".zip",
    ]

    # --- Email (transactional) ---
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str = "noreply@flowdesk.app"
    SMTP_USE_TLS: bool = True
    # When no SMTP host is configured, emails are logged instead of sent —
    # this keeps local/dev/test environments fully functional without
    # requiring real credentials, while production simply sets SMTP_HOST.
    EMAIL_ENABLED: bool = False

    # --- Frontend ---
    FRONTEND_URL: str = "http://localhost:5173"

    # --- Redis (background jobs / rate limit / webhook queue) ---
    REDIS_URL: str | None = None

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
