"""Models for configuration between CLI arguments and environment variables."""

from enum import Enum


class GitHubAuthenticationType(str, Enum):
    """Enum for GitHub authentication types."""

    PAT = "pat"
    APP = "app"
