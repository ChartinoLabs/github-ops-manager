"""Base ABC for GitHub clients."""

from abc import ABC, abstractmethod
from typing import Any, Literal


class GitHubClientBase(ABC):
    """Base ABC for GitHub clients."""

    # Repository CRUD
    @abstractmethod
    async def get_repository(self) -> Any:
        """Get a repository."""
        pass

    # Issue CRUD
    @abstractmethod
    async def create_issue(
        self,
        title: str,
        body: str | None = None,
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
        milestone: str | int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Create an issue for a repository."""
        pass

    @abstractmethod
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
    ) -> Any:
        """Update an issue for a repository."""
        pass

    @abstractmethod
    async def list_issues(self, state: Literal["open", "closed", "all"] | None = "all", **kwargs: Any) -> list[Any]:
        """List issues for a repository."""
        pass

    @abstractmethod
    async def close_issue(self, issue_number: int, **kwargs: Any) -> Any:
        """Close an issue for a repository."""
        pass

    # Label CRUD
    @abstractmethod
    async def create_label(self, name: str, color: str, description: str | None = None, **kwargs: Any) -> Any:
        """Create a label for a repository."""
        pass

    @abstractmethod
    async def update_label(
        self,
        name: str,
        new_name: str | None = None,
        color: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Update a label for a repository."""
        pass

    @abstractmethod
    async def delete_label(self, name: str) -> Any:
        """Delete a label for a repository."""
        pass

    @abstractmethod
    async def list_labels(self, **kwargs: Any) -> list[Any]:
        """List labels for a repository."""
        pass

    # Pull Request CRUD
    @abstractmethod
    async def get_pull_request(self, pull_request_number: int) -> Any:
        """Get a pull request for a repository."""
        pass

    @abstractmethod
    async def create_pull_request(
        self,
        title: str,
        head: str,
        base: str,
        body: str | None = None,
        draft: bool | None = None,
        maintainer_can_modify: bool | None = None,
        **kwargs: Any,
    ) -> Any:
        """Create a pull request for a repository."""
        pass

    @abstractmethod
    async def update_pull_request(
        self,
        pull_number: int,
        title: str | None = None,
        body: str | None = None,
        state: Literal["open", "closed"] | None = None,
        base: str | None = None,
        maintainer_can_modify: bool | None = None,
        **kwargs: Any,
    ) -> Any:
        """Update a pull request for a repository."""
        pass

    @abstractmethod
    async def list_pull_requests(self, state: Literal["open", "closed", "all"] | None = "all", **kwargs: Any) -> list[Any]:
        """List pull requests for a repository."""
        pass

    @abstractmethod
    async def merge_pull_request(self, pull_number: int, **kwargs: Any) -> Any:
        """Merge a pull request for a repository."""
        pass

    @abstractmethod
    async def close_pull_request(self, pull_number: int, **kwargs: Any) -> Any:
        """Close a pull request for a repository."""
        pass

    @abstractmethod
    async def list_files_in_pull_request(self, pull_number: int) -> list[Any]:
        """List files changed in a pull request."""
        pass

    @abstractmethod
    async def get_file_content_from_pull_request(self, file_path: str, branch: str) -> str:
        """Get the content of a file from a specific branch (typically the PR's head branch)."""
        pass

    @abstractmethod
    async def set_labels_on_issue(self, issue_number: int, labels: list[str]) -> None:
        """Set labels on a specific issue (or pull request)."""
        pass

    # Team Management Operations
    @abstractmethod
    async def get_user_by_username(self, username: str) -> Any:
        """Get a GitHub user by username."""
        pass

    @abstractmethod
    async def search_users_by_email(self, email: str) -> list[Any]:
        """Search for GitHub users by email address."""
        pass

    @abstractmethod
    async def get_team(self, org: str, team_slug: str) -> Any:
        """Get team information by organization and team slug."""
        pass

    @abstractmethod
    async def add_user_to_team(self, org: str, team_slug: str, username: str) -> bool:
        """Add a user to a GitHub team."""
        pass

    @abstractmethod
    async def check_team_membership(self, org: str, team_slug: str, username: str) -> bool:
        """Check if a user is already a member of a team."""
        pass

    # Release/Tag Operations
    @abstractmethod
    async def list_releases(self, per_page: int = 100, **kwargs: Any) -> list[Any]:
        """List all releases for a repository."""
        pass

    @abstractmethod
    async def get_release(self, tag_name: str) -> Any:
        """Get a specific release by tag name."""
        pass

    @abstractmethod
    async def get_latest_release(self) -> Any:
        """Get the latest release for the repository."""
        pass

    # Commit Operations
    @abstractmethod
    async def get_commit(self, commit_sha: str) -> dict[str, Any]:
        """Get detailed information about a specific commit, including full message body."""
        pass
