"""Base ABC for GitHub clients."""

from abc import ABC, abstractmethod
from typing import Any


class GitHubClientBase(ABC):
    """Base ABC for GitHub clients."""

    # Repository CRUD
    @abstractmethod
    async def get_repository(self) -> Any:
        """Get a repository."""
        pass

    # Issue CRUD
    @abstractmethod
    async def create_issue(self, title: str, body: str | None = None, **kwargs: Any) -> Any:
        """Create an issue for a repository."""
        pass

    @abstractmethod
    async def update_issue(self, issue_number: int, **kwargs: Any) -> Any:
        """Update an issue for a repository."""
        pass

    @abstractmethod
    async def list_issues(self, **kwargs: Any) -> list[Any]:
        """List issues for a repository."""
        pass

    @abstractmethod
    async def close_issue(self, issue_number: int, **kwargs: Any) -> Any:
        """Close an issue for a repository."""
        pass

    # Label CRUD
    @abstractmethod
    async def create_label(self, name: str, color: str, **kwargs: Any) -> Any:
        """Create a label for a repository."""
        pass

    @abstractmethod
    async def update_label(self, name: str, **kwargs: Any) -> Any:
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
    async def create_pull_request(self, title: str, head: str, base: str, **kwargs: Any) -> Any:
        """Create a pull request for a repository."""
        pass

    @abstractmethod
    async def update_pull_request(self, pull_number: int, **kwargs: Any) -> Any:
        """Update a pull request for a repository."""
        pass

    @abstractmethod
    async def list_pull_requests(self, **kwargs: Any) -> list[Any]:
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
