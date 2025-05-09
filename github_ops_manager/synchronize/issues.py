"""Contains synchronization logic for GitHub issues."""

import time
from typing import Any

from githubkit.versions.latest.models import Issue, IssuePropLabelsItemsOneof1, Label

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.schemas.default_issue import IssueModel
from github_ops_manager.synchronize.models import SyncDecision
from github_ops_manager.synchronize.results import AllIssueSynchronizationResults, IssueSynchronizationResult
from github_ops_manager.synchronize.utils import value_is_noney
from github_ops_manager.synchronize.workflow_runner import logger


async def decide_github_issue_label_sync_action(desired_label: str, github_issue: Issue) -> SyncDecision:
    """Compare a YAML label and a GitHub issue, and decide whether to create, update, or no-op.

    Key is label name.
    """
    for github_label in github_issue.labels:
        if isinstance(github_label, str):
            if github_label == desired_label:
                return SyncDecision.NOOP
        else:
            if github_label.name == desired_label:
                return SyncDecision.NOOP
    return SyncDecision.UPDATE


async def compare_github_issue_field(desired_value: Any, github_value: Any) -> SyncDecision:
    """Compare a YAML field and a GitHub field, and decide whether to create, update, or no-op.

    Key is field name.
    """
    desired_value_is_noney = await value_is_noney(desired_value)
    github_value_is_noney = await value_is_noney(github_value)
    if desired_value_is_noney and github_value_is_noney:
        return SyncDecision.NOOP
    elif desired_value_is_noney:
        return SyncDecision.CREATE
    elif github_value_is_noney:
        return SyncDecision.UPDATE
    elif desired_value == github_value:
        return SyncDecision.NOOP
    else:
        return SyncDecision.UPDATE


async def decide_github_issue_sync_action(desired_issue: IssueModel, github_issue: Issue | None = None) -> SyncDecision:
    """Compare a YAML issue and a GitHub issue, and decide whether to create, update, or no-op.

    Key is issue title.
    """
    if github_issue is None:
        logger.info("Issue not found in GitHub", issue_title=desired_issue.title)
        return SyncDecision.CREATE

    # Compare relevant fields
    fields_to_compare = ["body", "labels", "assignees", "milestone"]
    for field in fields_to_compare:
        # Special analysis for labels
        if field == "labels":
            if desired_issue.labels is None:
                logger.info("Issue has no labels", issue_title=desired_issue.title)
                return SyncDecision.NOOP
            for desired_label in desired_issue.labels:
                label_decision = await decide_github_issue_label_sync_action(desired_label, github_issue)
                if label_decision == SyncDecision.UPDATE:
                    logger.info(
                        "Issue needs to be updated (labels differ)",
                        issue_title=desired_issue.title,
                        issue_field="labels",
                        current_value=github_issue.labels,
                        new_value=desired_issue.labels,
                    )
                    return SyncDecision.UPDATE
            # Now check for labels that need to be removed
            desired_labels_set = set(desired_issue.labels)
            github_labels_set = set(
                label.name if isinstance(label, Label | IssuePropLabelsItemsOneof1) else label for label in getattr(github_issue, "labels", [])
            )
            extra_labels = github_labels_set - desired_labels_set
            if extra_labels:
                logger.info(
                    "Issue needs to be updated (labels to remove)",
                    issue_title=desired_issue.title,
                    issue_field="labels",
                    current_value=github_issue.labels,
                    new_value=desired_issue.labels,
                    labels_to_remove=list(extra_labels),
                )
                return SyncDecision.UPDATE
        else:
            field_decision = await compare_github_issue_field(getattr(desired_issue, field, None), getattr(github_issue, field, None))
            if field_decision == SyncDecision.UPDATE:
                logger.info(
                    "Issue needs to be updated",
                    issue_title=desired_issue.title,
                    issue_field=field,
                    current_value=getattr(github_issue, field, "None"),
                    new_value=getattr(desired_issue, field, "None"),
                )
                return SyncDecision.UPDATE
            elif field_decision == SyncDecision.CREATE:
                logger.info(
                    "Issue needs to be created",
                    issue_title=desired_issue.title,
                    issue_field=field,
                    new_value=getattr(desired_issue, field, "None"),
                )
                return SyncDecision.CREATE

    logger.info("Issue is up to date", issue_title=desired_issue.title)
    return SyncDecision.NOOP


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
        if decision == SyncDecision.CREATE:
            github_issue = await github_adapter.create_issue(
                title=desired_issue.title,
                body=desired_issue.body,
                labels=desired_issue.labels,
                assignees=desired_issue.assignees,
                milestone=desired_issue.milestone,
            )
            results.append(IssueSynchronizationResult(desired_issue, github_issue, decision))
        elif decision == SyncDecision.UPDATE:
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
