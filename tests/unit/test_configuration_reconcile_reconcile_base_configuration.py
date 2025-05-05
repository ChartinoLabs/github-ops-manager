"""Unit tests for the base configuration reconciliation process."""

from pathlib import Path
from unittest.mock import patch

import pytest

from github_ops_manager.configuration.exceptions import (
    GitHubAuthenticationConfigurationUndefinedError,
    RequiredConfigurationElementError,
)
from github_ops_manager.configuration.models import (
    BaseConfig,
    GitHubAuthenticationType,
)
from github_ops_manager.configuration.reconcile import (
    reconcile_base_configuration,
)


@pytest.mark.asyncio
async def test_reconcile_with_cli_args() -> None:
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

        result = await reconcile_base_configuration(
            cli_debug=True,
            cli_github_api_url="https://api.custom-github.com",
            cli_github_pat_token="cli-pat-token",
            cli_github_app_id=None,
            cli_github_app_private_key_path=None,
            cli_github_app_installation_id=None,
            cli_repo="owner/repo",
        )

    # Then
    assert isinstance(result, BaseConfig)
    assert result.debug is True  # CLI value
    assert result.github_api_url == "https://api.custom-github.com"  # CLI value
    assert result.github_pat_token == "cli-pat-token"  # CLI value
    assert result.github_authentication_type == GitHubAuthenticationType.PAT
    assert result.repo == "owner/repo"  # CLI value


@pytest.mark.asyncio
async def test_reconcile_with_env_vars() -> None:
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

        result = await reconcile_base_configuration(
            cli_debug=False,
            cli_github_api_url="",
            cli_github_pat_token=None,
            cli_github_app_id=None,
            cli_github_app_private_key_path=None,
            cli_github_app_installation_id=None,
            cli_repo=None,
        )

    # Then
    assert isinstance(result, BaseConfig)
    assert result.debug is True  # Environment value
    assert result.github_api_url == "https://api.github.com"  # Environment value
    assert result.github_pat_token == "env-pat-token"  # Environment value
    assert result.github_authentication_type == GitHubAuthenticationType.PAT
    assert result.repo == "env/repo"  # Environment value


@pytest.mark.asyncio
async def test_reconcile_with_github_app_auth() -> None:
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

        result = await reconcile_base_configuration(
            cli_debug=False,
            cli_github_api_url="",
            cli_github_pat_token=None,
            cli_github_app_id=1234567890,
            cli_github_app_private_key_path=Path("/path/to/key.pem"),
            cli_github_app_installation_id="install-id",
            cli_repo="owner/repo",
        )

    # Then
    assert isinstance(result, BaseConfig)
    assert result.github_authentication_type == GitHubAuthenticationType.APP
    assert result.github_app_id == 1234567890
    assert result.github_app_private_key_path == Path("/path/to/key.pem")
    assert result.github_app_installation_id == "install-id"


@pytest.mark.asyncio
async def test_missing_required_repo() -> None:
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
            await reconcile_base_configuration(
                cli_debug=False,
                cli_github_api_url="",
                cli_github_pat_token="pat-token",
                cli_github_app_id=None,
                cli_github_app_private_key_path=None,
                cli_github_app_installation_id=None,
                cli_repo=None,
            )

    assert "Repository" in str(exc_info.value)
    assert "repo" in str(exc_info.value)
    assert "REPO" in str(exc_info.value)


@pytest.mark.asyncio
async def test_no_auth_config() -> None:
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
            await reconcile_base_configuration(
                cli_debug=False,
                cli_github_api_url="",
                cli_github_pat_token=None,
                cli_github_app_id=None,
                cli_github_app_private_key_path=None,
                cli_github_app_installation_id=None,
                cli_repo="owner/repo",
            )

    assert "No GitHub authentication configuration provided" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mixed_auth_methods() -> None:
    """Test that an error is raised when both PAT and GitHub App auth are provided."""
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
            await reconcile_base_configuration(
                cli_debug=False,
                cli_github_api_url="",
                cli_github_pat_token="pat-token",
                cli_github_app_id=1234567890,
                cli_github_app_private_key_path=Path("/path/to/key.pem"),
                cli_github_app_installation_id="install-id",
                cli_repo="owner/repo",
            )

    assert "Both PAT and GitHub App configurations are defined" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cli_env_mixed_configuration() -> None:
    """Test reconciliation when values come from both CLI and environment."""
    # When
    with patch("github_ops_manager.configuration.reconcile.settings") as mock_settings:
        mock_settings.DEBUG = False
        mock_settings.GITHUB_API_URL = "https://api.github.com"
        mock_settings.GITHUB_PAT_TOKEN = "env-pat-token"
        mock_settings.GITHUB_APP_ID = None
        mock_settings.GITHUB_APP_PRIVATE_KEY_PATH = None
        mock_settings.GITHUB_APP_INSTALLATION_ID = None
        mock_settings.REPO = "env/repo"

        result = await reconcile_base_configuration(
            cli_debug=True,
            cli_github_api_url="",
            cli_github_pat_token=None,
            cli_github_app_id=None,
            cli_github_app_private_key_path=None,
            cli_github_app_installation_id=None,
            cli_repo="cli/repo",
        )

    # Then
    assert isinstance(result, BaseConfig)
    assert result.debug is True  # CLI takes precedence
    assert result.github_api_url == "https://api.github.com"  # From env
    assert result.github_pat_token == "env-pat-token"  # From env
    assert result.repo == "cli/repo"  # CLI takes precedence


@pytest.mark.asyncio
async def test_mixed_github_app_auth_sources() -> None:
    """Test GitHub App authentication with credentials from mixed sources."""
    # When
    with patch("github_ops_manager.configuration.reconcile.settings") as mock_settings:
        mock_settings.DEBUG = False
        mock_settings.GITHUB_API_URL = "https://api.github.com"
        mock_settings.GITHUB_PAT_TOKEN = None
        mock_settings.GITHUB_APP_ID = None
        mock_settings.GITHUB_APP_PRIVATE_KEY_PATH = Path("/env/path/to/key.pem")
        mock_settings.GITHUB_APP_INSTALLATION_ID = "env-install-id"
        mock_settings.REPO = None

        result = await reconcile_base_configuration(
            cli_debug=False,
            cli_github_api_url="",
            cli_github_pat_token=None,
            cli_github_app_id=1234567890,
            cli_github_app_private_key_path=None,
            cli_github_app_installation_id=None,
            cli_repo="owner/repo",
        )

    # Then
    assert isinstance(result, BaseConfig)
    assert result.github_authentication_type == GitHubAuthenticationType.APP
    assert result.github_app_id == 1234567890  # From CLI
    assert result.github_app_private_key_path == Path("/env/path/to/key.pem")  # From env
    assert result.github_app_installation_id == "env-install-id"  # From env


@pytest.mark.asyncio
async def test_empty_github_api_url() -> None:
    """Test that empty GitHub API URL from CLI falls back to env var."""
    # When
    with patch("github_ops_manager.configuration.reconcile.settings") as mock_settings:
        mock_settings.DEBUG = False
        mock_settings.GITHUB_API_URL = "https://api.github.com"
        mock_settings.GITHUB_PAT_TOKEN = None
        mock_settings.GITHUB_APP_ID = None
        mock_settings.GITHUB_APP_PRIVATE_KEY_PATH = None
        mock_settings.GITHUB_APP_INSTALLATION_ID = None
        mock_settings.REPO = None

        result = await reconcile_base_configuration(
            cli_debug=False,
            cli_github_api_url="",
            cli_github_pat_token="pat-token",
            cli_github_app_id=None,
            cli_github_app_private_key_path=None,
            cli_github_app_installation_id=None,
            cli_repo="owner/repo",
        )

    # Then
    assert isinstance(result, BaseConfig)
    assert result.github_api_url == "https://api.github.com"  # Falls back to env var


@pytest.mark.asyncio
async def test_debug_flag_combinations() -> None:
    """Test various combinations of debug flag from CLI and environment."""
    test_cases = [
        (True, True, True),  # CLI True, Env True -> True
        (True, False, True),  # CLI True, Env False -> True
        (False, True, True),  # CLI False, Env True -> True
        (False, False, False),  # CLI False, Env False -> False
    ]

    for cli_debug, env_debug, expected in test_cases:
        # When
        with patch("github_ops_manager.configuration.reconcile.settings") as mock_settings:
            mock_settings.DEBUG = env_debug
            mock_settings.GITHUB_API_URL = "https://api.github.com"
            mock_settings.GITHUB_PAT_TOKEN = None
            mock_settings.GITHUB_APP_ID = None
            mock_settings.GITHUB_APP_PRIVATE_KEY_PATH = None
            mock_settings.GITHUB_APP_INSTALLATION_ID = None
            mock_settings.REPO = None

            result = await reconcile_base_configuration(
                cli_debug=cli_debug,
                cli_github_api_url="",
                cli_github_pat_token="pat-token",
                cli_github_app_id=None,
                cli_github_app_private_key_path=None,
                cli_github_app_installation_id=None,
                cli_repo="owner/repo",
            )

        # Then
        assert isinstance(result, BaseConfig)
        assert result.debug is expected, f"Failed with CLI debug={cli_debug}, env debug={env_debug}"
