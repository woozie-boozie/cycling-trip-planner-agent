"""Runtime settings, loaded from environment.

Centralized so swapping models, raising token caps, or pointing at a different
provider doesn't require touching the orchestrator.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings sourced from environment variables and .env."""

    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-6"
    max_tokens: int = 8192
    max_loop_iterations: int = 25
    """Cap on agent loop iterations per turn — safety net against runaway loops."""

    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


_cached: Settings | None = None


def get_settings() -> Settings:
    """Lazy singleton. Tests can clear via `_clear_settings_cache()`."""
    global _cached
    if _cached is None:
        _cached = Settings()  # type: ignore[call-arg]
    return _cached


def _clear_settings_cache() -> None:
    """Test-only helper."""
    global _cached
    _cached = None
