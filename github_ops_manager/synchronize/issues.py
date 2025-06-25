"""Contains synchronization logic for GitHub issues."""

import time

import jinja2
import structlog
from githubkit.versions.latest.models import Issue

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.schemas.default_issue import IssueModel, IssuesYAMLModel
from github_ops_manager.synchronize.models import SyncDecision
from github_ops_manager.synchronize.results import AllIssueSynchronizationResults, IssueSynchronizationResult
from github_ops_manager.synchronize.utils import compare_github_field, compare_label_sets
from github_ops_manager.utils.templates import construct_jinja2_template

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


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
            decision = await compare_label_sets(desired_issue.labels, getattr(github_issue, "labels", []))
            if decision == SyncDecision.UPDATE:
                logger.info(
                    "Issue needs to be updated (labels differ)",
                    issue_title=desired_issue.title,
                    issue_field="labels",
                    current_value=getattr(github_issue, "labels", []),
                    new_value=desired_issue.labels,
                )
                return SyncDecision.UPDATE
        else:
            field_decision = await compare_github_field(getattr(desired_issue, field, None), getattr(github_issue, field, None))
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
    """For each YAML issue, decide whether to create, update, or no-op, and call the API accordingly."""
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
    number_of_created_github_issues = 0
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
            number_of_created_github_issues += 1
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
    return AllIssueSynchronizationResults(results, existing_issues, len(existing_issues) + number_of_created_github_issues)


async def render_issue_bodies(issues_yaml_model: IssuesYAMLModel) -> IssuesYAMLModel:
    """Render issue bodies using a provided Jinja2 template.

    This coroutine mutates the input object and returns it.
    """
    logger.info("Rendering issue bodies using template", template_path=issues_yaml_model.issue_template)
    try:
        template = construct_jinja2_template(issues_yaml_model.issue_template)
    except jinja2.TemplateSyntaxError as exc:
        logger.error("Encountered a syntax error with the provided issue template", issue_template=issues_yaml_model.issue_template, error=str(exc))
        raise

    for issue in issues_yaml_model.issues:
        if issue.data is not None:
            # Render with all issue fields available
            render_context = issue.model_dump()
            try:
                issue.body = template.render(**render_context)
            except jinja2.UndefinedError as exc:
                logger.error("Failed to render issue body with template", issue_title=issue.title, error=str(exc))
                raise

    return issues_yaml_model
