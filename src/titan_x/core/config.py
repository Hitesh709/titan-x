from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


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
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)

    # DATABASE_URL remains supported for local/dev deployments. Production can
    # instead provide the individual MySQL_* variables supplied by Render.
    database_url: AnyUrl | None = None
    mysql_host: str | None = None
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_database: str | None = None
    mysql_user: str | None = None
    mysql_password: SecretStr | None = None

    redis_url: AnyUrl
    api_key: SecretStr
    cors_origins: str = ""
    docs_enabled: bool = False
    sql_echo: bool = False
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=100)

    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=365)
    password_reset_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    email_verification_token_expire_hours: int = Field(default=48, ge=1, le=168)

    trusted_hosts: str = ""
    enable_https_redirect: bool = False
    seed_demo_on_startup: bool = False
    paper_demo_prices: bool = False
    frontend_url: str = "http://localhost:3000"

    market_data_provider: str = "yahoo"
    market_data_ingest_on_startup: bool = True
    market_data_ingest_max_symbols: int = Field(default=20, ge=1, le=2000)

    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=60, ge=1, le=10000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    brute_force_max_attempts: int = Field(default=5, ge=1, le=100)
    brute_force_window_minutes: int = Field(default=15, ge=1, le=1440)
    brute_force_block_minutes: int = Field(default=30, ge=1, le=1440)

    cache_default_ttl: int = Field(default=300, ge=1, le=86400)
    session_ttl: int = Field(default=3600, ge=60, le=604800)
    task_queue_enabled: bool = True
    task_queue_poll_interval: int = Field(default=1, ge=1, le=60)
    task_queue_max_retries: int = Field(default=3, ge=0, le=10)
    run_worker_in_process: bool = True

    scheduler_enabled: bool = True
    scheduler_poll_interval: int = Field(default=15, ge=5, le=300)
    job_default_max_retries: int = Field(default=3, ge=0, le=10)
    job_default_retry_delay: int = Field(default=60, ge=1, le=3600)

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "noreply@titanx.com"
    smtp_from_name: str = "Titan X"

    push_enabled: bool = False
    push_config_json: str = "{}"
    sms_enabled: bool = False
    sms_provider: str = "log"
    sms_config_json: str = "{}"
    sms_twilio_account_sid: str | None = None
    sms_twilio_auth_token: str | None = None
    sms_twilio_from_number: str | None = None
    sms_aws_access_key: str | None = None
    sms_aws_secret_key: str | None = None
    sms_aws_region: str = "us-east-1"

    qr_sms_number: str | None = None
    qr_sms_webhook_secret: SecretStr | None = None

    alert_evaluation_interval_seconds: int = Field(default=300, ge=30, le=86400)
    notification_log_only: bool = Field(default=True, description="Log notifications instead of sending when True")
    firebase_credentials_json: str | None = None
    firebase_enabled: bool = False
    retry_queue_enabled: bool = True
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_delay_seconds: int = Field(default=60, ge=10, le=3600)
    retry_max_delay_seconds: int = Field(default=86400, ge=60, le=604800)
    retry_batch_size: int = Field(default=50, ge=1, le=500)
    retry_poll_interval_seconds: int = Field(default=30, ge=5, le=300)
    notification_history_retention_days: int = Field(default=90, ge=1, le=730)
    backup_enabled: bool = False
    backup_s3_endpoint: str | None = None
    backup_s3_bucket: str | None = None
    backup_s3_region: str | None = None
    backup_s3_access_key: str | None = None
    backup_s3_secret_key: str | None = None
    backup_s3_prefix: str = "titan-x-backups"
    backup_interval_hours: int = Field(default=24, ge=1, le=720)

    @field_validator("api_key", "jwt_secret_key")
    @classmethod
    def validate_min_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError(f"{value} must contain at least 32 characters")
        return value

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_cors(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError("CORS_ORIGINS must not include a wildcard")
        return ",".join(origins)

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [origin for origin in self.cors_origins.split(",") if origin]

    @property
    def parsed_trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def resolved_database_url(self) -> str:
        if self.database_url is not None:
            return str(self.database_url)
        if not all((self.mysql_host, self.mysql_database, self.mysql_user, self.mysql_password)):
            raise ValueError("Database configuration is incomplete: provide DATABASE_URL or all MYSQL_* variables")
        return str(
            URL.create(
                "mysql+aiomysql",
                username=self.mysql_user,
                password=self.mysql_password.get_secret_value(),
                host=self.mysql_host,
                port=self.mysql_port,
                database=self.mysql_database,
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
