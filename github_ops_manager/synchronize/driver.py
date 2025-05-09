"""Orchestrates the synchronization of GitHub objects."""

import time
from pathlib import Path

from github_ops_manager.configuration.models import GitHubAuthenticationType
from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.yaml_processor import YAMLProcessingError, YAMLProcessor
from github_ops_manager.synchronize.issues import render_issue_bodies, sync_github_issues
from github_ops_manager.synchronize.results import AllIssueSynchronizationResults, ProcessIssuesResult
from github_ops_manager.synchronize.workflow_runner import logger, process_pull_requests_for_issues


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

    # Render Jinja2 templates for issue bodies if provided.
    if issues_model.issue_template:
        issues_model = await render_issue_bodies(issues_model)

    # Set up GitHub adapter.
    github_adapter = await GitHubKitAdapter.create(
        repo=repo,
        github_auth_type=github_auth_type,
        github_pat_token=github_pat_token,
        github_app_id=github_app_id,
        github_app_private_key_path=github_app_private_key_path,
        github_app_installation_id=github_app_installation_id,
        github_api_url=github_api_url,
    )

    # Synchronize issues to GitHub.
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

    # Synchronize pull requests for issues that specify a pull_request field.
    repo_info = await github_adapter.get_repository()
    default_branch = repo_info.default_branch
    await process_pull_requests_for_issues(issues_model.issues, github_adapter, default_branch)
    return ProcessIssuesResult(issue_sync_results)
