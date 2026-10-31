"""
app/config.py — backend settings, read from backend/.env.

Secrets (DATABASE_URL, BOT_TOKEN, JWT_SECRET) live ONLY here, loaded from
the environment. The frontend never sees them (rule: no secrets in client).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = ""
    # Direct (non-pooled) connection — used by Alembic for DDL, since PgBouncer
    # pooled URLs can break schema migrations. Falls back to DATABASE_URL.
    DATABASE_URL_UNPOOLED: str = ""
    BOT_TOKEN: str = ""
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 30
    CORS_ORIGINS: str = "*"
    # Comma-separated telegram user ids allowed as admins (Stage 8 uses this).
    ADMIN_TELEGRAM_IDS: str = ""
    # Public backend base for QR links printed on certificates (not a secret).
    PUBLIC_BASE_URL: str = "https://eduqurst.onrender.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def admin_id_set(self) -> set[int]:
        ids = set()
        for part in self.ADMIN_TELEGRAM_IDS.split(","):
            part = part.strip()
            if part.lstrip("-").isdigit():
                ids.add(int(part))
        return ids

    @property
    def migration_database_url(self) -> str:
        """Prefer the direct (non-pooled) URL for Alembic DDL; fall back otherwise."""
        return self.DATABASE_URL_UNPOOLED or self.DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
