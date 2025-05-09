# This file is intended to orchestrate the main actions (e.g., sync-to-github, export-issues).

"""Orchestrates the main workflows (e.g., sync-to-github, export-issues)."""

import time
from pathlib import Path

import jinja2
import structlog
from structlog.stdlib import BoundLogger

from github_ops_manager.configuration.models import GitHubAuthenticationType
from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.yaml_processor import (
    YAMLProcessingError,
    YAMLProcessor,
)
from github_ops_manager.schemas.default_issue import IssueModel
from github_ops_manager.synchronize.issues import sync_github_issues
from github_ops_manager.synchronize.results import AllIssueSynchronizationResults, ProcessIssuesResult
from github_ops_manager.utils.helpers import generate_branch_name

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
    # --- PR/branch orchestration integration ---
    repo_info = await github_adapter.get_repository()
    default_branch = repo_info.default_branch
    await process_pull_requests_for_issues(issues_model.issues, github_adapter, default_branch)
    return ProcessIssuesResult(issue_sync_results)


async def process_pull_requests_for_issues(
    issues: list[IssueModel],
    github_adapter: GitHubKitAdapter,
    default_branch: str,
) -> None:
    """Process pull requests for issues that specify a pull_request field."""
    for issue in issues:
        pr = issue.pull_request
        if pr is None:
            continue
        # Determine branch name
        branch_name = pr.branch or generate_branch_name(getattr(issue, "number", issue.title), issue.title)
        # Check if branch exists, create if not
        if not await github_adapter.branch_exists(branch_name):
            logger.info("Creating branch for PR", branch=branch_name, base_branch=default_branch)
            await github_adapter.create_branch(branch_name, default_branch)
        # Prepare files to commit
        files_to_commit: list[tuple[str, str]] = []
        missing_files: list[str] = []
        for file_path in pr.files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
                files_to_commit.append((file_path, content))
            except Exception as e:
                logger.error("File for PR not found or unreadable", file=file_path, error=str(e))
                missing_files.append(file_path)
        if missing_files:
            logger.error("Skipping PR creation due to missing files", files=missing_files, issue_title=issue.title)
            continue
        # Commit files to branch
        commit_message = f"Attach files for PR: {pr.title} (issue: {issue.title})"
        await github_adapter.commit_files_to_branch(branch_name, files_to_commit, commit_message)
        # Check for existing PRs from this branch
        prs = await github_adapter.list_pull_requests(head=f"{github_adapter.owner}:{branch_name}", base=default_branch, state="open")
        pr_body = pr.body or f"Closes #{getattr(issue, 'number', issue.title)}"
        pr_labels = pr.labels or []
        if prs:
            # Update the first matching PR
            existing_pr = prs[0]
            logger.info("Updating existing PR for issue", pr_number=existing_pr.number, branch=branch_name)
            await github_adapter.update_pull_request(
                pull_number=existing_pr.number,
                title=pr.title,
                body=pr_body,
            )
            # Update PR labels to match pr.labels
            if pr_labels:
                try:
                    await github_adapter.client.rest.issues.async_set_labels(
                        owner=github_adapter.owner,
                        repo=github_adapter.repo_name,
                        issue_number=existing_pr.number,
                        labels=pr_labels,
                    )
                    logger.info("Updated PR labels", pr_number=existing_pr.number, labels=pr_labels)
                except Exception as e:
                    logger.error("Failed to update PR labels", pr_number=existing_pr.number, error=str(e))
        else:
            # Create a new PR
            logger.info("Creating new PR for issue", branch=branch_name, base_branch=default_branch)
            new_pr = await github_adapter.create_pull_request(
                title=pr.title,
                head=branch_name,
                base=default_branch,
                body=pr_body,
            )
            # Add PR labels if specified
            if pr_labels:
                try:
                    await github_adapter.client.rest.issues.async_set_labels(
                        owner=github_adapter.owner,
                        repo=github_adapter.repo_name,
                        issue_number=new_pr.number,
                        labels=pr_labels,
                    )
                    logger.info("Added PR labels", pr_number=new_pr.number, labels=pr_labels)
                except Exception as e:
                    logger.error("Failed to add PR labels", pr_number=new_pr.number, error=str(e))
