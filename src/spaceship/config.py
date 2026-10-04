"""Client configuration (explicit args, env vars, or env file)."""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Config(BaseModel):
    """Spaceship client configuration with validation."""

    api_key: str = Field(description="Spaceship API key")
    api_secret: str = Field(description="Spaceship API secret")
    base_url: str = Field(
        default="https://spaceship.dev/api/v1",
        description="Spaceship API base URL",
    )
    timeout: float = Field(default=30.0, description="Request timeout in seconds")
    log_level: str = Field(default="INFO", description="Logging level")

    model_config = ConfigDict(str_strip_whitespace=True, validate_default=True)

    @field_validator("api_key", "api_secret")
    @classmethod
    def validate_required(cls, v: str) -> str:
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid}")
        return v.upper()

    @classmethod
    def from_env(
        cls,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        log_level: str | None = None,
    ) -> Config:
        """Build config from explicit args with ``SPACESHIP_*`` env fallback."""
        return cls(
            api_key=api_key or os.environ.get("SPACESHIP_API_KEY", ""),
            api_secret=api_secret or os.environ.get("SPACESHIP_API_SECRET", ""),
            base_url=base_url or os.environ.get("SPACESHIP_BASE_URL", "") or "https://spaceship.dev/api/v1",
            timeout=timeout if timeout is not None else float(os.environ.get("SPACESHIP_TIMEOUT", "30.0")),
            log_level=log_level or os.environ.get("SPACESHIP_LOG_LEVEL", "INFO"),
        )
