import ipaddress
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from email_validator import EmailNotValidError, validate_email
from sqlalchemy.engine import make_url


def _validate_production_https_origin(value: str, setting_name: str) -> None:
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        parsed.port
    except ValueError as exc:
        raise ValueError(f"{setting_name} must be a valid HTTPS origin") from exc

    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{setting_name} must be an HTTPS origin without credentials, path, query, or fragment")

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError(f"{setting_name} must use a real public HTTPS domain, not an IP address")

    placeholder_suffixes = (".example", ".invalid", ".test", ".localhost")
    example_domains = {"example.com", "example.org", "example.net"}
    if (
        hostname == "localhost"
        or hostname in example_domains
        or any(hostname.endswith("." + domain) for domain in example_domains)
        or any(hostname.endswith(suffix) for suffix in placeholder_suffixes)
        or "." not in hostname
    ):
        raise ValueError(f"{setting_name} must use a real public HTTPS domain, not a reserved placeholder")


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
    smtp_use_ssl: bool = False
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
            _validate_production_https_origin(self.public_base_url, "PUBLIC_BASE_URL")
            _validate_production_https_origin(self.frontend_origin, "FRONTEND_ORIGIN")
            if not self.cookie_name.startswith("__Host-"):
                raise ValueError("COOKIE_NAME must use the __Host- prefix outside development/test")
            database_password = make_url(self.database_url).password
            normalized_password = (database_password or "").strip().lower()
            if (
                len(database_password or "") < 24
                or len(set(database_password or "")) < 8
                or normalized_password in {"postgres", "password", "changeme"}
                or normalized_password.startswith(("replace-", "change-me-", "your-secret", "example-secret"))
            ):
                raise ValueError("DATABASE_URL must use a unique database password of at least 24 characters outside development/test")

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

            smtp_host = self.smtp_host.strip().lower().rstrip(".")
            placeholder_suffixes = (".example", ".invalid", ".test", ".localhost")
            example_domains = {"example.com", "example.org", "example.net"}
            if (
                smtp_host == "localhost"
                or smtp_host.startswith("<")
                or smtp_host.endswith(">")
                or any(character.isspace() for character in smtp_host)
                or smtp_host in example_domains
                or any(smtp_host.endswith("." + domain) for domain in example_domains)
                or any(smtp_host.endswith(suffix) for suffix in placeholder_suffixes)
            ):
                raise ValueError("SMTP_HOST must use a real provider hostname, not an example placeholder")

            try:
                validated_sender = validate_email(
                    self.smtp_from_email.strip(),
                    check_deliverability=False,
                )
            except EmailNotValidError as exc:
                raise ValueError("SMTP_FROM_EMAIL must be a valid mailbox address") from exc

            sender_domain = validated_sender.domain.lower()
            if (
                sender_domain in {"example.com", "example.org", "example.net", "localhost"}
                or any(sender_domain.endswith("." + domain) for domain in {"example.com", "example.org", "example.net"})
                or any(sender_domain.endswith(suffix) for suffix in placeholder_suffixes)
            ):
                raise ValueError("SMTP_FROM_EMAIL must use a real, verified sender domain")

            for label, value in (
                ("SMTP_USERNAME", self.smtp_username),
                ("SMTP_PASSWORD", self.smtp_password),
            ):
                normalized = (value or "").strip().lower()
                if (
                    normalized.startswith(("<", "replace-", "change-me-", "your-", "example-"))
                    or normalized in {"username", "password", "changeme", "your username", "your password"}
                ):
                    raise ValueError(f"{label} must be replaced with the email provider credential")

            if bool(self.smtp_username) != bool(self.smtp_password):
                raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
            if self.smtp_use_tls == self.smtp_use_ssl:
                raise ValueError(
                    "Exactly one of SMTP_USE_TLS or SMTP_USE_SSL must be true outside development/test"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
