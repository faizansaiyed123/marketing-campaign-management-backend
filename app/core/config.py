from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    app_name: str = "Campaign Management API"
    environment: str = "production"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/campaigns"
    jwt_secret_key: str = "change-me-in-development"
    jwt_expire_minutes: int = Field(default=480, gt=0, le=10080)
    frontend_origin: str = "http://localhost:5173"
    cookie_secure: bool = False
    cookie_name: str = "campaign_session"
    public_base_url: str = "http://localhost:8000"
    redis_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_runtime_security(self):
        env = self.environment.lower()
        if env not in {"development", "test"}:
            secret = self.jwt_secret_key.strip().lower()
            if secret.startswith(("replace-", "change-me-", "your-secret", "example-secret")):
                raise ValueError("JWT_SECRET_KEY must be replaced outside development/test")
            if len(self.jwt_secret_key) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters outside development/test")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true outside development/test")
            if not self.public_base_url.startswith("https://"):
                raise ValueError("PUBLIC_BASE_URL must use HTTPS outside development/test")
            if not self.cookie_name.startswith("__Host-"):
                raise ValueError("COOKIE_NAME must use the __Host- prefix outside development/test")
            if self.frontend_origin and not self.frontend_origin.startswith("https://"):
                raise ValueError("FRONTEND_ORIGIN must use HTTPS outside development/test")
            database_password = make_url(self.database_url).password
            normalized_password = (database_password or "").strip().lower()
            if (
                not normalized_password
                or normalized_password in {"postgres", "password", "changeme"}
                or normalized_password.startswith(("replace-", "change-me-", "your-secret", "example-secret"))
            ):
                raise ValueError("DATABASE_URL must use a unique database password outside development/test")

            try:
                redis_parts = urlsplit(self.redis_url or "")
                redis_password = redis_parts.password or ""
            except ValueError:
                redis_parts = None
                redis_password = ""
            normalized_redis_password = redis_password.strip().lower()
            if (
                redis_parts is None
                or redis_parts.scheme not in {"redis", "rediss"}
                or not redis_parts.hostname
                or len(redis_password) < 32
                or normalized_redis_password in {"password", "changeme"}
                or normalized_redis_password.startswith(
                    ("replace-", "change-me-", "your-secret", "example-secret", "development-only")
                )
            ):
                raise ValueError(
                    "REDIS_URL must point to shared Redis and include a unique password of at least 32 characters"
                )

            if not self.smtp_host or not self.smtp_from_email:
                raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL are required outside development/test")
            if bool(self.smtp_username) != bool(self.smtp_password):
                raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
            if not self.smtp_use_tls:
                raise ValueError("SMTP_USE_TLS must be true outside development/test")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
