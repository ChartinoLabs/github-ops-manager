"""GitHub client adapter for the githubkit library."""

from typing import Any, Self

from githubkit import Response
from githubkit.versions.latest.models import FullRepository, Issue

from github_ops_manager.utils.github import split_repository_in_configuration

from .abc import GitHubClientBase
from .client import GitHubClient, get_github_client


class GitHubKitAdapter(GitHubClientBase):
    """GitHub client adapter for the githubkit library."""

    def __init__(self, client: GitHubClient, owner: str, repo_name: str) -> None:
        """Initialize the GitHub client adapter with an already-initialized client."""
        self.client = client
        self.owner = owner
        self.repo_name = repo_name

    @classmethod
    async def create(cls) -> Self:
        """Create a new GitHub client adapter."""
        client = await get_github_client()
        owner, repo_name = await split_repository_in_configuration()
        return cls(client, owner, repo_name)

    async def get_repository(self) -> FullRepository:
        """Get the repository for the current client."""
        response: Response[FullRepository] = await self.client.rest.repos.async_get(owner=self.owner, repo=self.repo_name)
        return response.parsed_data

    async def create_issue(self, title: str, body: str | None = None, **kwargs: Any) -> Any:
        """Create an issue for a repository."""
        response: Response[Issue] = await self.client.rest.issues.async_create(
            owner=self.owner, repo=self.repo_name, title=title, body=body, **kwargs
        )
        return response.parsed_data

    async def update_issue(self, issue_number: int, **kwargs: Any) -> Any:
        """Update an issue for a repository."""
        response: Response[Issue] = await self.client.rest.issues.async_update(
            owner=self.owner, repo=self.repo_name, issue_number=issue_number, **kwargs
        )
        return response.parsed_data

    async def list_issues(self, **kwargs: Any) -> list[Any]:
        """List issues for a repository."""
        response: Response[list[Issue]] = await self.client.rest.issues.async_list_for_repo(owner=self.owner, repo=self.repo_name, **kwargs)
        return response.parsed_data
