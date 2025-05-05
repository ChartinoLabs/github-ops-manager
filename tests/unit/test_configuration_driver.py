"""Unit tests for the configuration driver module."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from github_ops_manager.configuration import driver
from github_ops_manager.configuration.models import (
    ExportIssuesConfig,
    GitHubAuthenticationType,
    ProcessIssuesConfig,
)


@pytest.mark.asyncio
async def test_get_process_issues_config_sets_and_returns_config() -> None:
    """Test that get_process_issues_config sets and returns the config."""
    fake_config = ProcessIssuesConfig(
        debug=True,
        github_api_url="https://api.github.com",
        github_authentication_type=GitHubAuthenticationType.PAT,
        github_pat_token="token",
        github_app_id=None,
        github_app_private_key_path=None,
        github_app_installation_id=None,
        repo="owner/repo",
        yaml_path=Path("issues.yaml"),
        create_prs=True,
    )
    with (
        patch(
            "github_ops_manager.configuration.reconcile.reconcile_process_issues_configuration",
            new=AsyncMock(return_value=fake_config),
        ) as mock_reconcile,
        patch("github_ops_manager.configuration.driver.set_configuration", new=AsyncMock()) as mock_set_config,
    ):
        result = await driver.get_process_issues_config(
            debug=True,
            github_api_url="https://api.github.com",
            github_pat_token="token",
            github_app_id=None,
            github_app_private_key_path=None,
            github_app_installation_id=None,
            repo="owner/repo",
            yaml_path=Path("issues.yaml"),
            create_prs=True,
        )
        mock_reconcile.assert_awaited_once()
        mock_set_config.assert_awaited_once_with(fake_config)
        assert result == fake_config


@pytest.mark.asyncio
async def test_get_export_issues_config_sets_and_returns_config() -> None:
    """Test that get_export_issues_config sets and returns the config."""
    fake_config = ExportIssuesConfig(
        debug=False,
        github_api_url="https://api.github.com",
        github_authentication_type=GitHubAuthenticationType.APP,
        github_pat_token=None,
        github_app_id=1234567890,
        github_app_private_key_path=Path("/path/to/key.pem"),
        github_app_installation_id=1234567890,
        repo="owner/repo",
        output_file=Path("out.yaml"),
        state="open",
        label="bug",
    )
    with (
        patch(
            "github_ops_manager.configuration.reconcile.reconcile_export_issues_configuration",
            new=AsyncMock(return_value=fake_config),
        ) as mock_reconcile,
        patch("github_ops_manager.configuration.driver.set_configuration", new=AsyncMock()) as mock_set_config,
    ):
        result = await driver.get_export_issues_config(
            debug=False,
            github_api_url="https://api.github.com",
            github_pat_token=None,
            github_app_id=1234567890,
            github_app_private_key_path=Path("/path/to/key.pem"),
            github_app_installation_id=1234567890,
            repo="owner/repo",
            output_file=Path("out.yaml"),
            state="open",
            label="bug",
        )
        mock_reconcile.assert_awaited_once()
        mock_set_config.assert_awaited_once_with(fake_config)
        assert result == fake_config
