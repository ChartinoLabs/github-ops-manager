"""Unit tests for the GitHubKitAdapter class and related GitHub operations."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest import MonkeyPatch

from github_ops_manager.github.adapter import GitHubKitAdapter


class DummyResponse:
    """A dummy response object to mock GitHub API responses."""

    def __init__(self, status_code: int = 200, sha: str = "abc123") -> None:
        """Initialize the dummy response with a status code and SHA."""
        self.status_code: int = status_code
        self.parsed_data = MagicMock()
        self.parsed_data.object.sha = sha
        self.parsed_data.commit.sha = sha
        self.parsed_data.sha = sha


@pytest.mark.asyncio
async def test_branch_exists_true(monkeypatch: MonkeyPatch) -> None:
    """Test that branch_exists returns True when the branch exists."""
    adapter = GitHubKitAdapter(MagicMock(), "owner", "repo")
    adapter.client.rest.repos.async_get_branch = AsyncMock(return_value=DummyResponse())
    assert await adapter.branch_exists("main") is True


@pytest.mark.asyncio
async def test_branch_exists_not_found(monkeypatch: MonkeyPatch) -> None:
    """Test that branch_exists returns False when the branch does not exist."""
    adapter = GitHubKitAdapter(MagicMock(), "owner", "repo")
    error = Exception("Not found")
    adapter.client.rest.repos.async_get_branch = AsyncMock(side_effect=error)
    assert await adapter.branch_exists("does-not-exist") is False


@pytest.mark.asyncio
async def test_branch_exists_other_error(monkeypatch: MonkeyPatch) -> None:
    """Test that branch_exists raises an exception for non-404 errors."""
    adapter = GitHubKitAdapter(MagicMock(), "owner", "repo")
    error = Exception("Server error")
    adapter.client.rest.repos.async_get_branch = AsyncMock(side_effect=error)
    # If a more specific exception is expected, replace Exception below
    with pytest.raises(Exception):  # noqa: B017
        await adapter.branch_exists("main")


@pytest.mark.asyncio
async def test_create_branch_success(monkeypatch: MonkeyPatch) -> None:
    """Test successful branch creation."""
    adapter = GitHubKitAdapter(MagicMock(), "owner", "repo")
    adapter.client.rest.git.async_get_ref = AsyncMock(return_value=DummyResponse(sha="base-sha"))
    adapter.client.rest.git.async_create_ref = AsyncMock()
    await adapter.create_branch("feature/test", "main")
    adapter.client.rest.git.async_create_ref.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_branch_rest_error(monkeypatch: MonkeyPatch) -> None:
    """Test that create_branch raises an exception on REST error."""
    adapter = GitHubKitAdapter(MagicMock(), "owner", "repo")
    adapter.client.rest.git.async_get_ref = AsyncMock(return_value=DummyResponse(sha="base-sha"))
    adapter.client.rest.git.async_create_ref = AsyncMock(side_effect=Exception("Unprocessable"))
    # If a more specific exception is expected, replace Exception below
    with pytest.raises(Exception):  # noqa: B017
        await adapter.create_branch("feature/test", "main")


@pytest.mark.asyncio
async def test_commit_files_to_branch_success(monkeypatch: MonkeyPatch) -> None:
    """Test committing new files to a branch."""
    adapter = GitHubKitAdapter(MagicMock(), "owner", "repo")
    adapter.client.rest.repos.async_get_branch = AsyncMock(return_value=DummyResponse())
    adapter.client.rest.repos.async_get_content = AsyncMock(side_effect=Exception("Not found"))
    adapter.client.rest.repos.async_create_or_update_file_contents = AsyncMock()
    await adapter.commit_files_to_branch("feature/test", [("file.txt", "content")], "msg")
    adapter.client.rest.repos.async_create_or_update_file_contents.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_files_to_branch_file_exists(monkeypatch: MonkeyPatch) -> None:
    """Test committing files to a branch when the file already exists."""
    adapter = GitHubKitAdapter(MagicMock(), "owner", "repo")
    adapter.client.rest.repos.async_get_branch = AsyncMock(return_value=DummyResponse())
    adapter.client.rest.repos.async_get_content = AsyncMock(return_value=DummyResponse(sha="file-sha"))
    adapter.client.rest.repos.async_create_or_update_file_contents = AsyncMock()
    await adapter.commit_files_to_branch("feature/test", [("file.txt", "content")], "msg")
    adapter.client.rest.repos.async_create_or_update_file_contents.assert_awaited_once()
