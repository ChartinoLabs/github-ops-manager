# This file is intended to orchestrate the main actions (e.g., sync-to-github, export-issues).

"""Orchestrates the main workflows (e.g., sync-to-github, export-issues)."""

import time
from pathlib import Path

import structlog
from githubkit.versions.latest.models import Issue
from structlog.stdlib import BoundLogger

from github_ops_manager.configuration.models import GitHubAuthenticationType
from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.models import IssueSyncDecision
from github_ops_manager.processing.results import AllIssueSynchronizationResults, IssueSynchronizationResult, ProcessIssuesResult
from github_ops_manager.processing.yaml_processor import (
    YAMLProcessingError,
    YAMLProcessor,
)
from github_ops_manager.schemas.default_issue import IssueModel

logger: BoundLogger = structlog.get_logger(__name__)  # type: ignore


async def run_process_issues_workflow(
    repo: str,
    github_pat_token: str | None,
    github_app_id: int | None,
    github_app_private_key_path: Path | None,
    github_app_installation_id: int | None,
    github_auth_type: GitHubAuthenticationType,
    github_api_url: str,
    yaml_path: Path,
    raise_on_yaml_error: bool = False,
) -> ProcessIssuesResult:
    """Run the process-issues workflow: load issues from YAML and return them/errors."""
    processor = YAMLProcessor(raise_on_error=raise_on_yaml_error)
    try:
        issues = processor.load_issues([str(yaml_path)])
    except YAMLProcessingError as e:
        return ProcessIssuesResult(AllIssueSynchronizationResults([]), errors=e.errors)

    # Set up GitHub adapter
    github_adapter = await GitHubKitAdapter.create(
        repo=repo,
        github_auth_type=github_auth_type,
        github_pat_token=github_pat_token,
        github_app_id=github_app_id,
        github_app_private_key_path=github_app_private_key_path,
        github_app_installation_id=github_app_installation_id,
        github_api_url=github_api_url,
    )
    start_time = time.time()
    logger.info("Processing issues", start_time=start_time)
    issue_sync_results = await sync_github_issues(issues, github_adapter)
    end_time = time.time()
    total_time = end_time - start_time
    logger.info(
        "Processed issues",
        start_time=start_time,
        end_time=end_time,
        duration=total_time,
        desired_issue_count=len(issues),
        issue_sync_result_count=len(issue_sync_results.results),
    )
    return ProcessIssuesResult(issue_sync_results)


async def decide_github_issue_sync_action(desired_issue: IssueModel, github_issue: Issue | None = None) -> IssueSyncDecision:
    """Compare a YAML issue and a GitHub issue, and decide whether to create, update, or no-op.

    Key is issue title.
    """
    if github_issue is None:
        logger.info("Issue not found in GitHub", issue_title=desired_issue.title)
        return IssueSyncDecision.CREATE

    # Compare relevant fields
    fields_to_compare = ["body", "labels", "assignees", "milestone"]
    for field in fields_to_compare:
        if getattr(desired_issue, field, None) != getattr(github_issue, field, None):
            logger.info(
                "Issue needs to be updated",
                issue_title=desired_issue.title,
                issue_field=field,
                current_value=getattr(github_issue, field, "None"),
                new_value=getattr(desired_issue, field, "None"),
            )
            return IssueSyncDecision.UPDATE

    logger.info("Issue is up to date", issue_title=desired_issue.title)
    return IssueSyncDecision.NOOP


async def sync_github_issues(desired_issues: list[IssueModel], github_adapter: GitHubKitAdapter) -> AllIssueSynchronizationResults:
    """For each YAML issue, decide whether to create, update, or no-op, and call the API accordingly.

    Returns a list of (yaml_issue, decision, github_issue) tuples.
    """
    # Fetch all existing issues from GitHub
    start_time = time.time()
    logger.info("Fetching existing issues from GitHub", start_time=start_time)
    existing_issues = await github_adapter.list_issues(state="all")
    end_time = time.time()
    total_time = end_time - start_time
    logger.info(
        "Fetched existing issues from GitHub", start_time=start_time, end_time=end_time, duration=total_time, issue_count=len(existing_issues)
    )
    github_issue_by_title: dict[str, Issue] = {issue.title: issue for issue in existing_issues}

    results: list[IssueSynchronizationResult] = []
    for desired_issue in desired_issues:
        github_issue = github_issue_by_title.get(desired_issue.title)
        decision = await decide_github_issue_sync_action(desired_issue, github_issue)
        if decision == IssueSyncDecision.CREATE:
            github_issue = await github_adapter.create_issue(
                title=desired_issue.title,
                body=desired_issue.body,
                labels=desired_issue.labels,
                assignees=desired_issue.assignees,
                milestone=desired_issue.milestone,
            )
            results.append(IssueSynchronizationResult(desired_issue, github_issue, decision))
        elif decision == IssueSyncDecision.UPDATE:
            if github_issue is not None:
                await github_adapter.update_issue(
                    issue_number=github_issue.number,
                    title=desired_issue.title,
                    body=desired_issue.body,
                    labels=desired_issue.labels,
                    assignees=desired_issue.assignees,
                    milestone=desired_issue.milestone,
                )
                results.append(IssueSynchronizationResult(desired_issue, github_issue, decision))
            else:
                raise ValueError("GitHub issue not found")
        else:
            if github_issue is not None:
                results.append(IssueSynchronizationResult(desired_issue, github_issue, decision))
            else:
                raise ValueError("GitHub issue not found")
    return AllIssueSynchronizationResults(results)
