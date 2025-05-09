"""Contains logic for synchronizing pull requests."""

import structlog
from githubkit.versions.latest.models import Issue, PullRequest

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.schemas.default_issue import IssueModel
from github_ops_manager.synchronize.models import SyncDecision
from github_ops_manager.utils.helpers import generate_branch_name

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def decide_github_pull_request_file_sync_action(
    desired_file_name: str,
    desired_file_content: str,
    github_pull_request: PullRequest,
    github_adapter: GitHubKitAdapter,
) -> SyncDecision:
    """Compare a YAML pull request's file and a GitHub pull request, and decide whether to create, update, or no-op."""
    files = await github_adapter.list_files_in_pull_request(github_pull_request.number)
    for file in files:
        if file.filename == desired_file_name:
            github_file_content = await github_adapter.get_file_content_from_pull_request(
                file_path=desired_file_name,
                branch=github_pull_request.head.ref,
            )
            if github_file_content == desired_file_content:
                return SyncDecision.NOOP
            else:
                return SyncDecision.UPDATE
    return SyncDecision.CREATE


async def decide_github_pull_request_label_sync_action(desired_label: str, github_pull_request: PullRequest) -> SyncDecision:
    """Compare a YAML label and a GitHub pull request, and decide whether to create, update, or no-op."""
    for github_label in github_pull_request.labels:
        if isinstance(github_label, str):
            if github_label == desired_label:
                return SyncDecision.NOOP
        else:
            if github_label.name == desired_label:
                return SyncDecision.NOOP
    return SyncDecision.UPDATE


async def decide_github_pull_request_sync_action(desired_issue: IssueModel, existing_issue: Issue, github_adapter: GitHubKitAdapter) -> SyncDecision:
    """Compare a YAML issue and a GitHub issue, and decide whether to create, update, or no-op the associated pull request."""
    # First, check if the existing issue has a pull request linked to it.
    if existing_issue.pull_request is None:
        logger.info("Existing issue has no pull request linked to it, creating a new one", issue_title=desired_issue.title)
        return SyncDecision.CREATE

    # Next, compare the titles of the existing and desired pull request
    if existing_issue.pull_request.title != desired_issue.title:
        logger.info("Existing pull request title does not match desired title, updating the pull request", issue_title=desired_issue.title)
        return SyncDecision.UPDATE

    # Next, check the body of the existing and desired pull request
    if existing_issue.pull_request.body != desired_issue.pull_request.body:
        logger.info("Existing pull request body does not match desired body, updating the pull request", issue_title=desired_issue.title)
        return SyncDecision.UPDATE

    # Next, check the labels of the existing and desired pull request
    label_decision = await decide_github_pull_request_label_sync_action(desired_issue.pull_request.labels, existing_issue.pull_request)
    if label_decision == SyncDecision.UPDATE:
        logger.info("Existing pull request labels do not match desired labels, updating the pull request", issue_title=desired_issue.title)
        return SyncDecision.UPDATE


async def sync_github_pull_requests(
    desired_issues: list[IssueModel],
    existing_issues: list[Issue],
    github_adapter: GitHubKitAdapter,
    default_branch: str,
) -> None:
    """Process pull requests for issues that specify a pull_request field."""
    desired_issues_with_prs = [issue for issue in desired_issues if issue.pull_request is not None]
    for desired_issue in desired_issues_with_prs:
        pr = desired_issue.pull_request
        existing_issue = next((issue for issue in existing_issues if issue.number == desired_issue.number), None)
        if existing_issue is None:
            logger.error("Issue not found in existing issues", issue_title=desired_issue.title)
            continue

        # Determine branch name
        desired_branch_name = pr.branch or generate_branch_name(existing_issue.number, desired_issue.title)

        # Check if branch exists, create if not
        if not await github_adapter.branch_exists(desired_branch_name):
            logger.info("Creating branch for PR", branch=desired_branch_name, base_branch=default_branch)
            await github_adapter.create_branch(desired_branch_name, default_branch)
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
            logger.error("Skipping PR creation due to missing files", files=missing_files, issue_title=desired_issue.title)
            continue
        # Commit files to branch
        commit_message = f"Attach files for PR: {pr.title} (issue: {desired_issue.title})"
        await github_adapter.commit_files_to_branch(desired_branch_name, files_to_commit, commit_message)
        # Check for existing PRs from this branch
        prs = await github_adapter.list_pull_requests(head=f"{github_adapter.owner}:{desired_branch_name}", base=default_branch, state="open")
        pr_body = pr.body or f"Closes #{getattr(desired_issue, 'number', desired_issue.title)}"
        pr_labels = pr.labels or []
        if prs:
            # Update the first matching PR
            existing_pr = prs[0]
            logger.info("Updating existing PR for issue", pr_number=existing_pr.number, branch=desired_branch_name)
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
            logger.info("Creating new PR for issue", branch=desired_branch_name, base_branch=default_branch)
            new_pr = await github_adapter.create_pull_request(
                title=pr.title,
                head=desired_branch_name,
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
