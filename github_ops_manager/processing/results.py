"""Contains results of application execution."""

from typing import Any


class ProcessIssuesResult:
    """Contains results of the process-issues workflow."""

    def __init__(
        self, issues: list[Any], errors: list[dict[str, Any]] | None = None
    ) -> None:
        """Initialize the result with issues and errors."""
        self.issues = issues
        self.errors = errors or []
