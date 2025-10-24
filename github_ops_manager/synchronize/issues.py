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
from github_ops_manager.utils.templates import construct_jinja2_template_from_file

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


async def process_tac_attachments(issue: IssueModel, issue_number: int, github_adapter: GitHubKitAdapter) -> None:
    """Process and upload large TAC outputs as attachments.

    This function handles uploading command_output and parsed_output content that exceeds
    TAC_MAX_INLINE_OUTPUT_SIZE as GitHub issue attachments. Content is retrieved from the
    original issue data (before it was removed during template rendering).

    Args:
        issue: The issue model with original TAC data preserved in _original_commands_data
        issue_number: GitHub issue number to attach files to
        github_adapter: GitHub adapter for uploads
    """
    from github_ops_manager.utils.attachments import process_large_content_for_attachment

    # Check if this is a TAC issue with preserved original commands data
    if not hasattr(issue, "_original_commands_data"):
        return

    logger.info("Processing TAC attachments for issue", issue_number=issue_number, issue_title=issue.title)

    # Access the ORIGINAL data (before template rendering removed large content)
    for command_data in issue._original_commands_data:  # type: ignore
        command = command_data.get("command", "unknown")

        # Process command_output if it exists
        if command_data.get("command_output"):
            await process_large_content_for_attachment(
                content=command_data["command_output"],
                filename=f"{command}_output.txt",
                github_adapter=github_adapter,
                issue_number=issue_number,
            )

        # Process parsed_output if it exists
        if command_data.get("parsed_output"):
            # Determine file extension based on parser type
            parser_used = command_data.get("parser_used", "")
            if parser_used in ["Genie", "NXOSJSON"]:
                extension = "json"
            elif parser_used == "YamlPathParse":
                extension = "yaml"
            else:
                extension = "json"  # Default for Regex and others

            await process_large_content_for_attachment(
                content=command_data["parsed_output"],
                filename=f"{command}_parsed.{extension}",
                github_adapter=github_adapter,
                issue_number=issue_number,
            )


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

    logger.info("Issue is up to date", issue_title=desired_issue.title, issue_number=github_issue.number)
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

            # Process attachments for TAC issues after issue creation
            await process_tac_attachments(desired_issue, github_issue.number, github_adapter)

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

    For Testing as Code issues, large command outputs and parsed data that exceed
    TAC_MAX_INLINE_OUTPUT_SIZE will be removed before rendering. The original content
    is preserved in a separate attribute for later attachment upload.
    """
    from copy import deepcopy

    from github_ops_manager.utils.constants import TAC_MAX_INLINE_OUTPUT_SIZE

    logger.info("Rendering issue bodies using template", template_path=issues_yaml_model.issue_template)
    try:
        template = construct_jinja2_template_from_file(issues_yaml_model.issue_template)
    except jinja2.TemplateSyntaxError as exc:
        logger.error("Encountered a syntax error with the provided issue template", issue_template=issues_yaml_model.issue_template, error=str(exc))
        raise

    for issue in issues_yaml_model.issues:
        if issue.data is not None:
            # Preserve original data for attachment processing
            if "commands" in issue.data:
                # Store original commands data before modification
                if not hasattr(issue, "_original_commands_data"):
                    issue._original_commands_data = deepcopy(issue.data["commands"])  # type: ignore

                # Remove large content from TAC issues before template rendering
                for command_data in issue.data["commands"]:
                    # Remove command_output if too large
                    if command_data.get("command_output") and len(command_data["command_output"]) > TAC_MAX_INLINE_OUTPUT_SIZE:
                        logger.info(
                            "Removing large command_output from template context",
                            issue_title=issue.title,
                            command=command_data.get("command"),
                            content_size=len(command_data["command_output"]),
                            threshold=TAC_MAX_INLINE_OUTPUT_SIZE,
                        )
                        command_data["command_output"] = None

                    # Remove parsed_output if too large
                    if command_data.get("parsed_output") and len(command_data["parsed_output"]) > TAC_MAX_INLINE_OUTPUT_SIZE:
                        logger.info(
                            "Removing large parsed_output from template context",
                            issue_title=issue.title,
                            command=command_data.get("command"),
                            content_size=len(command_data["parsed_output"]),
                            threshold=TAC_MAX_INLINE_OUTPUT_SIZE,
                        )
                        command_data["parsed_output"] = None

            # Render with modified data (large content removed)
            render_context = issue.model_dump()
            try:
                issue.body = template.render(**render_context)
            except jinja2.UndefinedError as exc:
                logger.error("Failed to render issue body with template", issue_title=issue.title, error=str(exc))
                raise

    return issues_yaml_model
