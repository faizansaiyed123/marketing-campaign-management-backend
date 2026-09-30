from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
            if self.jwt_secret_key == "change-me-in-development":
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
        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()
