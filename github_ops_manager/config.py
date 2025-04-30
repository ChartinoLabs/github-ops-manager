"""Reconciles configuration between CLI arguments and environment variables."""

from dataclasses import dataclass
from enum import Enum


class GitHubAuthenticationType(str, Enum):
    """Enum for GitHub authentication types."""

    PAT = "pat"
    APP = "app"


@dataclass
class BaseConfig:
    """Configuration class for the GitHub Operations Manager CLI."""

    debug: bool
    github_api_url: str
    github_authentication_type: GitHubAuthenticationType
    github_pat_token: str | None
    github_app_id: str | None
    github_app_private_key_path: str | None
    github_app_installation_id: str | None
    repo: str | None


@dataclass
class ProcessIssuesConfig(BaseConfig):
    """Configuration class for the process-issues command."""

    yaml_path: str | None
    create_prs: bool


@dataclass
class ExportIssuesConfig(BaseConfig):
    """Configuration class for the export-issues command."""

    output_file: str | None
    state: str | None
    label: str | None
