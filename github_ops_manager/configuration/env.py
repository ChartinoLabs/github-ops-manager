"""Pydantic Settings model for application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment variable settings for the application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Generic application-wide settings
    DEBUG: bool = False

    # GitHub API settings
    GITHUB_API_URL: str = "https://api.github.com"
    REPO: str | None = None

    # GitHub PAT settings
    GITHUB_PAT_TOKEN: str | None = None

    # GitHub App settings
    GITHUB_APP_ID: str | None = None
    GITHUB_APP_PRIVATE_KEY_PATH: Path | None = None
    GITHUB_APP_INSTALLATION_ID: str | None = None


settings = Settings()
