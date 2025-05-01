"""Unit tests for validate_github_authentication_configuration function."""

from pathlib import Path

import pytest

from github_ops_manager.configuration.exceptions import (
    GitHubAuthenticationConfigurationUndefinedError,
)
from github_ops_manager.configuration.models import GitHubAuthenticationType
from github_ops_manager.configuration.reconcile import validate_github_authentication_configuration


@pytest.mark.asyncio
async def test_valid_pat_authentication() -> None:
    """Test that PAT authentication is validated correctly."""
    # When
    auth_type = await validate_github_authentication_configuration(
        github_pat_token="test-token",
        github_app_id=None,
        github_app_private_key_path=None,
        github_app_installation_id=None,
    )

    # Then
    assert auth_type == GitHubAuthenticationType.PAT


@pytest.mark.asyncio
async def test_valid_app_authentication() -> None:
    """Test that GitHub App authentication is validated correctly."""
    # When
    auth_type = await validate_github_authentication_configuration(
        github_pat_token=None,
        github_app_id="test-app-id",
        github_app_private_key_path=Path("/path/to/key.pem"),
        github_app_installation_id="test-installation-id",
    )

    # Then
    assert auth_type == GitHubAuthenticationType.APP


@pytest.mark.asyncio
async def test_both_auth_methods_error() -> None:
    """Test that error is raised when both PAT and App authentication are provided."""
    # When/Then
    with pytest.raises(GitHubAuthenticationConfigurationUndefinedError) as exc_info:
        await validate_github_authentication_configuration(
            github_pat_token="test-token",
            github_app_id="test-app-id",
            github_app_private_key_path=Path("/path/to/key.pem"),
            github_app_installation_id="test-installation-id",
        )

    assert "Both PAT and GitHub App configurations are defined" in str(exc_info.value)


@pytest.mark.asyncio
async def test_no_auth_error() -> None:
    """Test that error is raised when no authentication is provided."""
    # When/Then
    with pytest.raises(GitHubAuthenticationConfigurationUndefinedError) as exc_info:
        await validate_github_authentication_configuration(
            github_pat_token=None,
            github_app_id=None,
            github_app_private_key_path=None,
            github_app_installation_id=None,
        )

    assert "No GitHub authentication configuration provided" in str(exc_info.value)


@pytest.mark.asyncio
async def test_missing_app_id() -> None:
    """Test error when GitHub App ID is missing but other App credentials exist."""
    # When/Then
    with pytest.raises(GitHubAuthenticationConfigurationUndefinedError) as exc_info:
        await validate_github_authentication_configuration(
            github_pat_token=None,
            github_app_id=None,
            github_app_private_key_path=Path("/path/to/key.pem"),
            github_app_installation_id="test-installation-id",
        )

    assert "Incomplete GitHub App configuration" in str(exc_info.value)
    assert "GitHub App ID" in str(exc_info.value)


@pytest.mark.asyncio
async def test_missing_private_key_path() -> None:
    """Test error when GitHub App private key path is missing but other App credentials exist."""
    # When/Then
    with pytest.raises(GitHubAuthenticationConfigurationUndefinedError) as exc_info:
        await validate_github_authentication_configuration(
            github_pat_token=None,
            github_app_id="test-app-id",
            github_app_private_key_path=None,
            github_app_installation_id="test-installation-id",
        )

    assert "Incomplete GitHub App configuration" in str(exc_info.value)
    assert "GitHub App private key path" in str(exc_info.value)


@pytest.mark.asyncio
async def test_missing_installation_id() -> None:
    """Test error when GitHub App installation ID is missing but other App credentials exist."""
    # When/Then
    with pytest.raises(GitHubAuthenticationConfigurationUndefinedError) as exc_info:
        await validate_github_authentication_configuration(
            github_pat_token=None,
            github_app_id="test-app-id",
            github_app_private_key_path=Path("/path/to/key.pem"),
            github_app_installation_id=None,
        )

    assert "Incomplete GitHub App configuration" in str(exc_info.value)
    assert "GitHub App installation ID" in str(exc_info.value)


@pytest.mark.asyncio
async def test_missing_multiple_app_credentials() -> None:
    """Test error when multiple GitHub App credentials are missing."""
    # When/Then
    with pytest.raises(GitHubAuthenticationConfigurationUndefinedError) as exc_info:
        await validate_github_authentication_configuration(
            github_pat_token=None,
            github_app_id=None,
            github_app_private_key_path=None,
            github_app_installation_id="test-installation-id",
        )

    assert "Incomplete GitHub App configuration" in str(exc_info.value)
    assert "GitHub App ID" in str(exc_info.value)
    assert "GitHub App private key path" in str(exc_info.value)


@pytest.mark.asyncio
async def test_error_message_contains_cli_and_env_variable_names() -> None:
    """Test that error messages include CLI option and environment variable names."""
    # When/Then
    with pytest.raises(GitHubAuthenticationConfigurationUndefinedError) as exc_info:
        await validate_github_authentication_configuration(
            github_pat_token=None,
            github_app_id="test-app-id",
            github_app_private_key_path=None,
            github_app_installation_id=None,
        )

    error_message = str(exc_info.value)
    assert "command line option github_app_private_key_path" in error_message
    assert "environment variable GITHUB_APP_PRIVATE_KEY_PATH" in error_message
