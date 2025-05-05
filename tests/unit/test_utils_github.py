"""Contains unit tests for the utils.github module."""

from unittest.mock import patch

import pytest

from github_ops_manager.utils.github import split_repository_in_configuration


@pytest.mark.asyncio
async def test_split_repository_valid() -> None:
    """Test splitting a valid owner/repo string."""
    with patch("github_ops_manager.utils.github.config") as mock_config:
        mock_config.repo = "octocat/Hello-World"
        owner, repo = await split_repository_in_configuration()
        assert owner == "octocat"
        assert repo == "Hello-World"


@pytest.mark.asyncio
async def test_split_repository_missing() -> None:
    """Test that ValueError is raised if repo is None."""
    with patch("github_ops_manager.utils.github.config") as mock_config:
        mock_config.repo = None
        with pytest.raises(ValueError, match="GitHub App authentication requires repo in config."):
            await split_repository_in_configuration()


@pytest.mark.asyncio
async def test_split_repository_malformed() -> None:
    """Test that ValueError is raised if repo is malformed (no slash)."""
    with patch("github_ops_manager.utils.github.config") as mock_config:
        mock_config.repo = "octocat-HelloWorld"
        with pytest.raises(ValueError):
            await split_repository_in_configuration()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_repo",
    [
        "",  # empty string
        "/",  # only a slash
        "/owner/repo",  # leading slash
        "owner/repo/",  # trailing slash
        "owner/repo/extra",  # too many parts
    ],
)
async def test_split_repository_various_malformed(malformed_repo: str) -> None:
    """Test that ValueError is raised if repo is malformed (various cases)."""
    with patch("github_ops_manager.utils.github.config") as mock_config:
        mock_config.repo = malformed_repo
        with pytest.raises(ValueError):
            await split_repository_in_configuration()
