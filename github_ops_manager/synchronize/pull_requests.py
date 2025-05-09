"""Contains logic for synchronizing pull requests."""

import structlog

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.schemas.default_issue import IssueModel
from github_ops_manager.utils.helpers import generate_branch_name

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def sync_github_pull_requests(
    desired_issues: list[IssueModel],
    github_adapter: GitHubKitAdapter,
    default_branch: str,
) -> None:
    """Process pull requests for issues that specify a pull_request field."""
    desired_issues_with_prs = [issue for issue in desired_issues if issue.pull_request is not None]
    for desired_issue in desired_issues_with_prs:
        pr = desired_issue.pull_request
        # Determine branch name
        branch_name = pr.branch or generate_branch_name(getattr(desired_issue, "number", desired_issue.title), desired_issue.title)
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
            logger.error("Skipping PR creation due to missing files", files=missing_files, issue_title=desired_issue.title)
            continue
        # Commit files to branch
        commit_message = f"Attach files for PR: {pr.title} (issue: {desired_issue.title})"
        await github_adapter.commit_files_to_branch(branch_name, files_to_commit, commit_message)
        # Check for existing PRs from this branch
        prs = await github_adapter.list_pull_requests(head=f"{github_adapter.owner}:{branch_name}", base=default_branch, state="open")
        pr_body = pr.body or f"Closes #{getattr(desired_issue, 'number', desired_issue.title)}"
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
