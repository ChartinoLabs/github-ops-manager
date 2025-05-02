"""Unit tests for the process-issues configuration reconciliation process."""

from pathlib import Path
from unittest.mock import patch

import pytest

from github_ops_manager.configuration.exceptions import (
    GitHubAuthenticationConfigurationUndefinedError,
    RequiredConfigurationElementError,
)
from github_ops_manager.configuration.models import (
    GitHubAuthenticationType,
    ProcessIssuesConfig,
)
from github_ops_manager.configuration.reconcile import reconcile_process_issues_configuration


@pytest.mark.asyncio
async def test_reconcile_process_issues_with_cli_args() -> None:
    """Test reconciliation when all values are provided via CLI arguments."""
    # When
    with patch("github_ops_manager.configuration.reconcile.settings") as mock_settings:
        mock_settings.DEBUG = False
        mock_settings.GITHUB_API_URL = "https://api.github.com"
        mock_settings.GITHUB_PAT_TOKEN = "env-pat-token"
        mock_settings.GITHUB_APP_ID = None
        mock_settings.GITHUB_APP_PRIVATE_KEY_PATH = None
        mock_settings.GITHUB_APP_INSTALLATION_ID = None
        mock_settings.REPO = "other/repo"

        result = await reconcile_process_issues_configuration(
            cli_debug=True,
            cli_github_api_url="https://api.custom-github.com",
            cli_github_pat_token="cli-pat-token",
            cli_github_app_id=None,
            cli_github_app_private_key_path=None,
            cli_github_app_installation_id=None,
            cli_repo="owner/repo",
            cli_yaml_path=Path("/path/to/issues.yaml"),
            cli_create_prs=True,
        )

    # Then
    assert isinstance(result, ProcessIssuesConfig)
    assert result.debug is True  # CLI value
    assert result.github_api_url == "https://api.custom-github.com"  # CLI value
    assert result.github_pat_token == "cli-pat-token"  # CLI value
    assert result.github_authentication_type == GitHubAuthenticationType.PAT
    assert result.repo == "owner/repo"  # CLI value
    assert result.yaml_path == Path("/path/to/issues.yaml")  # CLI value
    assert result.create_prs is True  # CLI value


@pytest.mark.asyncio
async def test_reconcile_process_issues_with_env_vars() -> None:
    """Test reconciliation when values are provided via environment variables."""
    # When
    with patch("github_ops_manager.configuration.reconcile.settings") as mock_settings:
        mock_settings.DEBUG = True
        mock_settings.GITHUB_API_URL = "https://api.github.com"
        mock_settings.GITHUB_PAT_TOKEN = "env-pat-token"
        mock_settings.GITHUB_APP_ID = None
        mock_settings.GITHUB_APP_PRIVATE_KEY_PATH = None
        mock_settings.GITHUB_APP_INSTALLATION_ID = None
        mock_settings.REPO = "env/repo"

        result = await reconcile_process_issues_configuration(
            cli_debug=False,
            cli_github_api_url="",
            cli_github_pat_token=None,
            cli_github_app_id=None,
            cli_github_app_private_key_path=None,
            cli_github_app_installation_id=None,
            cli_repo=None,
            cli_yaml_path=None,
            cli_create_prs=False,
        )

    # Then
    assert isinstance(result, ProcessIssuesConfig)
    assert result.debug is True  # Environment value
    assert result.github_api_url == "https://api.github.com"  # Environment value
    assert result.github_pat_token == "env-pat-token"  # Environment value
    assert result.github_authentication_type == GitHubAuthenticationType.PAT
    assert result.repo == "env/repo"  # Environment value
    assert result.yaml_path is None  # Default value
    assert result.create_prs is False  # Default value


@pytest.mark.asyncio
async def test_reconcile_process_issues_with_github_app_auth() -> None:
    """Test reconciliation with GitHub App authentication."""
    # When
    with patch("github_ops_manager.configuration.reconcile.settings") as mock_settings:
        mock_settings.DEBUG = False
        mock_settings.GITHUB_API_URL = "https://api.github.com"
        mock_settings.GITHUB_PAT_TOKEN = None
        mock_settings.GITHUB_APP_ID = None
        mock_settings.GITHUB_APP_PRIVATE_KEY_PATH = None
        mock_settings.GITHUB_APP_INSTALLATION_ID = None
        mock_settings.REPO = None

        result = await reconcile_process_issues_configuration(
            cli_debug=False,
            cli_github_api_url="",
            cli_github_pat_token=None,
            cli_github_app_id="app-id",
            cli_github_app_private_key_path=Path("/path/to/key.pem"),
            cli_github_app_installation_id="install-id",
            cli_repo="owner/repo",
            cli_yaml_path=Path("/path/to/issues.yaml"),
            cli_create_prs=True,
        )

    # Then
    assert isinstance(result, ProcessIssuesConfig)
    assert result.github_authentication_type == GitHubAuthenticationType.APP
    assert result.github_app_id == "app-id"  # CLI value
    assert result.github_app_private_key_path == Path("/path/to/key.pem")  # CLI value
    assert result.github_app_installation_id == "install-id"  # CLI value
    assert result.yaml_path == Path("/path/to/issues.yaml")  # CLI value
    assert result.create_prs is True  # CLI value


@pytest.mark.asyncio
async def test_reconcile_process_issues_missing_required_repo() -> None:
    """Test that an error is raised when repository is not provided."""
    # When/Then
    with patch("github_ops_manager.configuration.reconcile.settings") as mock_settings:
        mock_settings.DEBUG = False
        mock_settings.GITHUB_API_URL = "https://api.github.com"
        mock_settings.GITHUB_PAT_TOKEN = None
        mock_settings.GITHUB_APP_ID = None
        mock_settings.GITHUB_APP_PRIVATE_KEY_PATH = None
        mock_settings.GITHUB_APP_INSTALLATION_ID = None
        mock_settings.REPO = None

        with pytest.raises(RequiredConfigurationElementError) as exc_info:
            await reconcile_process_issues_configuration(
                cli_debug=False,
                cli_github_api_url="",
                cli_github_pat_token="pat-token",
                cli_github_app_id=None,
                cli_github_app_private_key_path=None,
                cli_github_app_installation_id=None,
                cli_repo=None,
                cli_yaml_path=Path("/path/to/issues.yaml"),
                cli_create_prs=False,
            )

    assert "Repository" in str(exc_info.value)
    assert "repo" in str(exc_info.value)
    assert "REPO" in str(exc_info.value)


@pytest.mark.asyncio
async def test_reconcile_process_issues_no_auth_config() -> None:
    """Test that an error is raised when no authentication configuration is provided."""
    # When/Then
    with patch("github_ops_manager.configuration.reconcile.settings") as mock_settings:
        mock_settings.DEBUG = False
        mock_settings.GITHUB_API_URL = "https://api.github.com"
        mock_settings.GITHUB_PAT_TOKEN = None
        mock_settings.GITHUB_APP_ID = None
        mock_settings.GITHUB_APP_PRIVATE_KEY_PATH = None
        mock_settings.GITHUB_APP_INSTALLATION_ID = None
        mock_settings.REPO = None

        with pytest.raises(GitHubAuthenticationConfigurationUndefinedError) as exc_info:
            await reconcile_process_issues_configuration(
                cli_debug=False,
                cli_github_api_url="",
                cli_github_pat_token=None,
                cli_github_app_id=None,
                cli_github_app_private_key_path=None,
                cli_github_app_installation_id=None,
                cli_repo="owner/repo",
                cli_yaml_path=Path("/path/to/issues.yaml"),
                cli_create_prs=False,
            )

    assert "No GitHub authentication configuration provided" in str(exc_info.value)
