"""Base ABC for GitHub clients."""

from abc import ABC, abstractmethod
from typing import Any


class GitHubClientBase(ABC):
    """Base ABC for GitHub clients."""

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
