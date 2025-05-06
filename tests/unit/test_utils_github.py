"""Contains unit tests for the utils.github module."""

import pytest

from github_ops_manager.utils.github import split_repository_in_configuration


@pytest.mark.asyncio
async def test_split_repository_valid() -> None:
    """Test splitting a valid owner/repo string."""
    owner, repo = await split_repository_in_configuration("octocat/Hello-World")
    assert owner == "octocat"
    assert repo == "Hello-World"


@pytest.mark.asyncio
async def test_split_repository_missing() -> None:
    """Test that ValueError is raised if repo is None."""
    with pytest.raises(ValueError, match="GitHub App authentication requires repo in config."):
        await split_repository_in_configuration(None)


@pytest.mark.asyncio
async def test_split_repository_malformed_no_slash() -> None:
    """Test that ValueError is raised if repo is malformed (no slash)."""
    with pytest.raises(ValueError):
        await split_repository_in_configuration("octocat-HelloWorld")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_repo",
    [
        pytest.param("", id="empty string"),
        pytest.param("/", id="only a slash"),
        pytest.param("owner/repo/extra", id="too many parts"),
    ],
)
async def test_split_repository_various_malformed(malformed_repo: str) -> None:
    """Test that ValueError is raised if repo is malformed (various cases)."""
    with pytest.raises(ValueError):
        await split_repository_in_configuration(malformed_repo)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repo_input,expected_owner,expected_repo",
    [
        pytest.param("octocat/Hello-World", "octocat", "Hello-World", id="no slashes"),
        pytest.param("/octocat/Hello-World", "octocat", "Hello-World", id="leading slash"),
        pytest.param("octocat/Hello-World/", "octocat", "Hello-World", id="trailing slash"),
        pytest.param("/octocat/Hello-World/", "octocat", "Hello-World", id="both slashes"),
    ],
)
async def test_split_repository_strips_slashes(repo_input: str, expected_owner: str, expected_repo: str) -> None:
    """Test that leading/trailing slashes are stripped and owner/repo are parsed correctly."""
    owner, repo = await split_repository_in_configuration(repo_input)
    assert owner == expected_owner
    assert repo == expected_repo
