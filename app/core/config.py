"""VYRO — Application settings (pydantic-settings)."""
from __future__ import annotations

from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # ---------- App ----------
    APP_NAME: str = "VYRO"
    ENV: str = "dev"  # dev | staging | prod
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    VERSION: str = "1.0.0"

    # ---------- Database ----------
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://vyro:vyro_secret@127.0.0.1:5432/vyro",
        validation_alias=AliasChoices("VYRO_DATABASE_URL", "DATABASE_URL"),
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False
    DB_STATEMENT_TIMEOUT_MS: int = 15000

    # ---------- Redis (optional) ----------
    REDIS_URL: Optional[str] = None

    # ---------- Security / JWT ----------
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    EMAIL_TOKEN_EXPIRE_HOURS: int = 24
    RESET_TOKEN_EXPIRE_HOURS: int = 1

    # ---------- Email ----------
    EMAIL_VERIFICATION_REQUIRED: bool = True
    DEV_EXPOSE_EMAIL_TOKENS: bool = True
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "VYRO <no-reply@vyro.app>"

    # ---------- Media ----------
    MEDIA_ROOT: str = "./media"
    MAX_UPLOAD_SIZE_MB: int = 10
    MAX_IMAGES_PER_POST: int = 4

    # ---------- Rate limit ----------
    RATE_LIMIT_GLOBAL: str = "300/60"  # requests/seconds per IP
    RATE_LIMIT_AUTH: str = "10/60"

    # ---------- Economy (ZYRA coin) ----------
    SIGNUP_BONUS_ZYRA: int = 100
    DAILY_BONUS_ZYRA: int = 25
    BUFF_MIN: int = 1
    BUFF_MAX: int = 10000
    DAILY_BONUS_COOLDOWN_HOURS: int = 24

    # ---------- Profile ----------
    USERNAME_CHANGE_COOLDOWN_DAYS: int = 7

    # ---------- CORS ----------
    CORS_ORIGINS: str = "*"

    # ---------- Seed admin ----------
    ADMIN_EMAIL: str = "admin@vyro.app"
    ADMIN_PASSWORD: str = "Admin@1234"
    ADMIN_USERNAME: str = "vyro_admin"

    # ---------- helpers ----------
    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.ENV == "prod"

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


settings = Settings()
