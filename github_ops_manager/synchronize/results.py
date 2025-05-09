"""Contains results of application execution."""

from typing import Any

from githubkit.versions.latest.models import Issue

from github_ops_manager.schemas.default_issue import IssueModel
from github_ops_manager.synchronize.models import SyncDecision


class IssueSynchronizationResult:
    """Contains results of the issue synchronization workflow."""

    def __init__(self, desired_issue: IssueModel, github_issue: Issue, decision: SyncDecision) -> None:
        """Initialize the result with the desired issue, the actual issue, and the decision."""
        self.desired_issue = desired_issue
        self.github_issue = github_issue
        self.decision = decision


class AllIssueSynchronizationResults:
    """Contains results of the issue synchronization workflow for all issues."""

    def __init__(
        self,
        results: list[IssueSynchronizationResult],
        github_issues_before_sync: list[Issue],
        expected_number_of_github_issues_after_sync: int,
    ) -> None:
        """Initialize the result with a list of issue synchronization results."""
        self.results = results
        self.github_issues_before_sync = github_issues_before_sync
        self.expected_number_of_github_issues_after_sync = expected_number_of_github_issues_after_sync


class ProcessIssuesResult:
    """Contains results of the process-issues workflow."""

    def __init__(self, issue_synchronization_results: AllIssueSynchronizationResults, errors: list[dict[str, Any]] | None = None) -> None:
        """Initialize the result with issues and errors."""
        self.issue_synchronization_results = issue_synchronization_results
        self.errors = errors or []
