"""Configuration loaded from environment variables.

Fails fast on missing or malformed values rather than serving 500s
indefinitely. This matches the brief's preference for "clear startup
failure" over deferred runtime errors when the token is missing.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, HttpUrl, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="",
        case_sensitive=True,
        extra="ignore",
    )

    gitlab_url: HttpUrl = Field(alias="GITLAB_URL")
    gitlab_token: str = Field(alias="GITLAB_TOKEN", min_length=1)
    request_timeout_seconds: float = Field(default=30.0, alias="REQUEST_TIMEOUT_SECONDS")
    per_page: int = Field(default=100, ge=1, le=100, alias="GITLAB_PER_PAGE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("gitlab_token")
    @classmethod
    def _strip_token(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("GITLAB_TOKEN must not be blank")
        return stripped

    @property
    def gitlab_api_base(self) -> str:
        parsed = urlparse(str(self.gitlab_url))
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc
        return f"{scheme}://{netloc}/api/v4"


class ConfigError(RuntimeError):
    """Raised when environment configuration is invalid."""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        missing = [
            err["loc"][0] for err in exc.errors() if err.get("type") in {"missing", "value_error"}
        ]
        hint = ", ".join(str(m) for m in missing) if missing else "see details above"
        raise ConfigError(
            f"Invalid configuration ({hint}). "
            f"Required env vars: GITLAB_URL, GITLAB_TOKEN. Details: {exc}"
        ) from exc
