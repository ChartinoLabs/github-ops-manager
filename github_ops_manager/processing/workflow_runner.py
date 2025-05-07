# This file is intended to orchestrate the main actions (e.g., sync-to-github, export-issues).

"""Orchestrates the main workflows (e.g., sync-to-github, export-issues)."""

import time
from pathlib import Path
from typing import Any

import jinja2
import structlog
from githubkit.versions.latest.models import Issue, IssuePropLabelsItemsOneof1, Label
from structlog.stdlib import BoundLogger

from github_ops_manager.configuration.models import GitHubAuthenticationType
from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.models import SyncDecision
from github_ops_manager.processing.results import AllIssueSynchronizationResults, IssueSynchronizationResult, ProcessIssuesResult
from github_ops_manager.processing.yaml_processor import (
    YAMLProcessingError,
    YAMLProcessor,
)
from github_ops_manager.schemas.default_issue import IssueModel, LabelModel

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
        issues_model = processor.load_issues_model([str(yaml_path)])
    except YAMLProcessingError as e:
        return ProcessIssuesResult(AllIssueSynchronizationResults([]), errors=e.errors)

    # Template rendering logic
    if issues_model.issue_template:
        logger.info("Rendering issue bodies using template", template_path=issues_model.issue_template)
        try:
            with open(issues_model.issue_template, encoding="utf-8") as f:
                template_content = f.read()
            jinja_env = jinja2.Environment(undefined=jinja2.StrictUndefined)
            template = jinja_env.from_string(template_content)
        except Exception as e:
            logger.error("Failed to load or parse issue template", template_path=issues_model.issue_template, error=str(e))
            return ProcessIssuesResult(AllIssueSynchronizationResults([]), errors=[{"error": str(e)}])
        for issue in issues_model.issues:
            if issue.data is not None:
                try:
                    # Render with all issue fields available
                    render_context = issue.model_dump()
                    issue.body = template.render(**render_context)
                except Exception as e:
                    logger.error("Failed to render issue body with template", issue_title=issue.title, error=str(e))
                    # Optionally, continue or set body to empty string
                    issue.body = ""
            # If data is None, leave body as-is
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
    issue_sync_results = await sync_github_issues(issues_model.issues, github_adapter)
    end_time = time.time()
    total_time = end_time - start_time
    logger.info(
        "Processed issues",
        start_time=start_time,
        end_time=end_time,
        duration=total_time,
        desired_issue_count=len(issues_model.issues),
        issue_sync_result_count=len(issue_sync_results.results),
    )
    return ProcessIssuesResult(issue_sync_results)


async def decide_github_label_sync_action(desired_label: LabelModel, github_label: Label | None = None) -> SyncDecision:
    """Compare a YAML label and a GitHub label, and decide whether to create, update, or no-op.

    Key is label name.
    """
    # For now, we'll only make decisions based on the label name
    if github_label is None:
        logger.info("Label not found in GitHub", label_name=desired_label.name)
        return SyncDecision.CREATE

    if github_label.name != desired_label.name:
        logger.info("Label needs to be updated", current_label_name=github_label.name, new_label_name=desired_label.name)
        return SyncDecision.UPDATE

    logger.info("Label is up to date", label_name=desired_label.name)
    return SyncDecision.NOOP


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


async def value_is_noney(value: Any) -> bool:
    """Check if a value is None, an empty list, an empty string, or an empty dict."""
    if value is None:
        return True
    elif isinstance(value, list) and value == []:
        return True
    elif isinstance(value, str) and value == "":
        return True
    elif isinstance(value, dict) and not value:
        return True
    return False


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
