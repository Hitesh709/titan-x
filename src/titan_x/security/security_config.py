"""Central security configuration for Titan-X.

Security-sensitive defaults live here so API modules can share one policy.
Never store credentials or signing keys in source control; use environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SecurityConfig:
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    refresh_token_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    rate_limit_per_minute: int = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "120"))
    max_request_bytes: int = int(os.getenv("MAX_REQUEST_BYTES", str(2 * 1024 * 1024)))
    allowed_origins: tuple[str, ...] = tuple(
        x.strip() for x in os.getenv("ALLOWED_ORIGINS", "").split(",") if x.strip()
    )
    production: bool = os.getenv("ENVIRONMENT", "development").lower() == "production"

    def validate(self) -> None:
        if self.production and not os.getenv("JWT_SECRET"):
            raise RuntimeError("JWT_SECRET must be configured in production")
        if self.production and not self.allowed_origins:
            raise RuntimeError("ALLOWED_ORIGINS must be configured in production")
        if self.access_token_minutes > 60:
            raise RuntimeError("Access tokens must expire within 60 minutes")


security_config = SecurityConfig()
