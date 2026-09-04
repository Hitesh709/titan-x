from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TITAN X"
    app_version: str = "0.1.0"
    app_build_date: str = ""
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    log_format: str = "json"
    log_slow_request_ms: int = Field(default=1000, ge=0, le=60000)
    host: str = "0.0.0.0"  # nosec B104 - required for Render/container web binding
    port: int = Field(default=8000, ge=1, le=65535)

    # Titan X uses SQLite. DATABASE_URL may override the default for local/test
    # environments, but production Render is explicitly configured below.
    database_url: AnyUrl = "sqlite+aiosqlite:///./titan_x.db"

    redis_url: AnyUrl
    api_key: SecretStr
    cors_origins: str = ""