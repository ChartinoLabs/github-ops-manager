"""GitHub client adapter for the githubkit library."""

from typing import Any, Literal, Self

from githubkit import Response
from githubkit.versions.latest.models import (
    FullRepository,
    Issue,
    Label,
    PullRequest,
    PullRequestSimple,
)

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

    # Repository CRUD
    async def get_repository(self) -> FullRepository:
        """Get the repository for the current client."""
        response: Response[FullRepository] = await self.client.rest.repos.async_get(owner=self.owner, repo=self.repo_name)
        return response.parsed_data

    # Issue CRUD
    async def create_issue(
        self,
        title: str,
        body: str | None = None,
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
        milestone: str | int | None = None,
        **kwargs: Any,
    ) -> Issue:
        """Create an issue for a repository."""
        response: Response[Issue] = await self.client.rest.issues.async_create(
            owner=self.owner,
            repo=self.repo_name,
            title=title,
            body=body,
            assignees=assignees,
            labels=labels,  # type: ignore
            milestone=milestone,
            **kwargs,
        )
        return response.parsed_data

    async def update_issue(
        self,
        issue_number: int,
        title: str | None = None,
        body: str | None = None,
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
        milestone: str | int | None = None,
        state: Literal["open", "closed"] | None = None,
        **kwargs: Any,
    ) -> Issue:
        """Update an issue for a repository."""
        response: Response[Issue] = await self.client.rest.issues.async_update(
            owner=self.owner,
            repo=self.repo_name,
            issue_number=issue_number,
            title=title,
            body=body,
            assignees=assignees,
            labels=labels,  # type: ignore
            milestone=milestone,
            state=state,
            **kwargs,
        )
        return response.parsed_data

    async def list_issues(self, **kwargs: Any) -> list[Issue]:
        """List issues for a repository."""
        response: Response[list[Issue]] = await self.client.rest.issues.async_list_for_repo(owner=self.owner, repo=self.repo_name, **kwargs)
        return response.parsed_data

    async def close_issue(self, issue_number: int, **kwargs: Any) -> Issue:
        """Close an issue for a repository."""
        response: Response[Issue] = await self.client.rest.issues.async_update(
            owner=self.owner,
            repo=self.repo_name,
            issue_number=issue_number,
            state="closed",
            **kwargs,
        )
        return response.parsed_data

    # Label CRUD
    async def create_label(self, name: str, color: str, description: str | None = None, **kwargs: Any) -> Label:
        """Create a label for a repository."""
        response: Response[Label] = await self.client.rest.issues.async_create_label(
            owner=self.owner,
            repo=self.repo_name,
            name=name,
            color=color,
            description=description,
            **kwargs,
        )
        return response.parsed_data

    async def update_label(
        self,
        name: str,
        new_name: str | None = None,
        color: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> Label:
        """Update a label for a repository."""
        response: Response[Label] = await self.client.rest.issues.async_update_label(
            owner=self.owner,
            repo=self.repo_name,
            name=name,
            new_name=new_name,
            color=color,
            description=description,
            **kwargs,
        )
        return response.parsed_data

    async def delete_label(self, name: str) -> None:
        """Delete a label for a repository."""
        await self.client.rest.issues.async_delete_label(owner=self.owner, repo=self.repo_name, name=name)
        return None

    async def list_labels(self, **kwargs: Any) -> list[Label]:
        """List labels for a repository."""
        response: Response[list[Label]] = await self.client.rest.issues.async_list_labels_for_repo(owner=self.owner, repo=self.repo_name, **kwargs)
        return response.parsed_data

    # Pull Request CRUD
    async def create_pull_request(
        self,
        title: str,
        head: str,
        base: str,
        body: str | None = None,
        draft: bool | None = None,
        maintainer_can_modify: bool | None = None,
        **kwargs: Any,
    ) -> PullRequest:
        """Create a pull request for a repository."""
        response: Response[PullRequest] = await self.client.rest.pulls.async_create(
            owner=self.owner,
            repo=self.repo_name,
            title=title,
            head=head,
            base=base,
            body=body,
            draft=draft,
            maintainer_can_modify=maintainer_can_modify,
            **kwargs,
        )
        return response.parsed_data

    async def update_pull_request(
        self,
        pull_number: int,
        title: str | None = None,
        body: str | None = None,
        state: Literal["open", "closed"] | None = None,
        base: str | None = None,
        maintainer_can_modify: bool | None = None,
        **kwargs: Any,
    ) -> PullRequest:
        """Update a pull request for a repository."""
        response: Response[PullRequest] = await self.client.rest.pulls.async_update(
            owner=self.owner,
            repo=self.repo_name,
            pull_number=pull_number,
            title=title,
            body=body,
            state=state,
            base=base,
            maintainer_can_modify=maintainer_can_modify,
            **kwargs,
        )
        return response.parsed_data

    async def list_pull_requests(self, **kwargs: Any) -> list[PullRequestSimple]:
        """List pull requests for a repository."""
        response: Response[list[PullRequestSimple]] = await self.client.rest.pulls.async_list(owner=self.owner, repo=self.repo_name, **kwargs)
        return response.parsed_data

    async def merge_pull_request(self, pull_number: int, **kwargs: Any) -> Any:
        """Merge a pull request for a repository."""
        response = await self.client.rest.pulls.async_merge(owner=self.owner, repo=self.repo_name, pull_number=pull_number, **kwargs)
        return response.parsed_data

    async def close_pull_request(self, pull_number: int, **kwargs: Any) -> PullRequest:
        """Close a pull request for a repository."""
        response: Response[PullRequest] = await self.client.rest.pulls.async_update(
            owner=self.owner,
            repo=self.repo_name,
            pull_number=pull_number,
            state="closed",
            **kwargs,
        )
        return response.parsed_data
