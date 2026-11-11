from functools import lru_cache
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Urban Liquor OS"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production-please-use-a-long-random-string"
    currency: str = "KES"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/urban_liquor"
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    algorithm: str = "HS256"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env.lower() == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if (
                self.secret_key == "change-me-in-production-please-use-a-long-random-string"
                or len(self.secret_key) < 32
            ):
                raise ValueError("Set a unique SECRET_KEY of at least 32 characters in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
