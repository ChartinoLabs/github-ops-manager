"""Contains logic for synchronizing pull requests."""

import structlog
from githubkit.versions.latest.models import Issue, PullRequest

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.schemas.default_issue import IssueModel, PullRequestModel
from github_ops_manager.synchronize.models import SyncDecision
from github_ops_manager.synchronize.utils import compare_github_field, compare_label_sets
from github_ops_manager.utils.helpers import generate_branch_name

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def get_pull_request_associated_with_issue(issue: Issue, existing_pull_requests: list[PullRequest]) -> PullRequest | None:
    """Get the pull request associated with the issue.

    The only way to do this is to parse the body of the pull request and look
    for closing keywords that reference the issue number. This is extremely
    hacky; it's also the only reasonable way to do this, as GitHub does not
    have an API for directly getting the pull request associated with an issue.
    """
    closing_keywords = [
        "close",
        "closes",
        "closed",
        "fix",
        "fixes",
        "fixed",
        "resolve",
        "resolves",
        "resolved",
    ]
    for pr in existing_pull_requests:
        if pr.body is None:
            continue
        for keyword in closing_keywords:
            if f"{keyword} #{issue.number}" in pr.body.lower():
                return pr
    return None


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


async def decide_github_pull_request_sync_action(desired_issue: IssueModel, existing_pull_request: PullRequest | None = None) -> SyncDecision:
    """Compare a YAML issue and a GitHub issue, and decide whether to create, update, or no-op the associated pull request."""
    if existing_pull_request is None:
        logger.info("Existing issue has no pull request linked to it, creating a new one", issue_title=desired_issue.title)
        return SyncDecision.CREATE

    # Compare relevant pull request fields
    pr_fields_to_compare = ["title", "body"]
    for field in pr_fields_to_compare:
        desired_value = getattr(desired_issue.pull_request, field, None)
        github_value = getattr(existing_pull_request, field, None)
        field_decision = await compare_github_field(desired_value, github_value)
        if field_decision == SyncDecision.UPDATE:
            logger.info(
                "Pull request needs to be updated",
                issue_title=desired_issue.title,
                pr_field=field,
                current_value=github_value,
                new_value=desired_value,
            )
            return SyncDecision.UPDATE
        elif field_decision == SyncDecision.CREATE:
            logger.info(
                "Pull request needs to be created",
                issue_title=desired_issue.title,
                pr_field=field,
                new_value=desired_value,
            )
            return SyncDecision.CREATE

    # Next, check the labels of the existing and desired pull request
    decision = await compare_label_sets(desired_issue.pull_request.labels, getattr(existing_pull_request, "labels", []))
    if decision == SyncDecision.UPDATE:
        logger.info(
            "Existing pull request labels do not match desired labels, updating the pull request",
            issue_title=desired_issue.title,
        )
        return SyncDecision.UPDATE

    logger.info("Pull request is up to date", issue_title=desired_issue.title)
    return SyncDecision.NOOP


async def commit_files_to_branch(
    desired_issue: IssueModel, existing_issue: Issue, desired_branch_name: str, github_adapter: GitHubKitAdapter
) -> None:
    """Commit files to a branch."""
    if desired_issue.pull_request is None:
        raise ValueError("Desired issue has no pull request associated with it")

    files_to_commit: list[tuple[str, str]] = []
    missing_files: list[str] = []
    logger.info("Preparing files to commit for pull request", issue_title=desired_issue.title, branch=desired_branch_name)
    for file_path in desired_issue.pull_request.files:
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
            files_to_commit.append((file_path, content))
        except FileNotFoundError as exc:
            logger.error("File for PR not found or unreadable", file=file_path, error=str(exc))
            missing_files.append(file_path)
    if missing_files:
        logger.error("Skipping PR creation due to missing files", files=missing_files, issue_title=desired_issue.title)
        raise ValueError("Skipping PR creation due to missing files")

    # Commit files to branch
    logger.info("Committing files to branch", issue_title=desired_issue.title, branch=desired_branch_name)
    commit_message = (
        f"chore: attach files for PR '{desired_issue.pull_request.title}' associated with issue '{desired_issue.title}' ({existing_issue.number})"
    )
    await github_adapter.commit_files_to_branch(desired_branch_name, files_to_commit, commit_message)


async def sync_github_pull_request(
    desired_issue: IssueModel,
    existing_issue: Issue,
    existing_pull_requests: list[PullRequest],
    github_adapter: GitHubKitAdapter,
    default_branch: str,
    existing_pull_request: PullRequest | None = None,
) -> None:
    """Synchronize a specific pull request for an issue."""
    # Ignoring type below because we know that the pull_request field is
    # not None at this point.
    pr: PullRequestModel = desired_issue.pull_request  # type: ignore
    pr_body = pr.body or f"Closes #{getattr(desired_issue, 'number', desired_issue.title)}"
    pr_labels = pr.labels or []

    # Make overall PR sync decision
    pr_sync_decision = await decide_github_pull_request_sync_action(desired_issue, existing_pull_request=existing_pull_request)
    if pr_sync_decision == SyncDecision.CREATE:
        # Determine branch name
        desired_branch_name = pr.branch or generate_branch_name(existing_issue.number, desired_issue.title)

        # Check if branch exists, create if not
        if not await github_adapter.branch_exists(desired_branch_name):
            logger.info("Creating branch for PR", branch=desired_branch_name, base_branch=default_branch)
            await github_adapter.create_branch(desired_branch_name, default_branch)
        else:
            logger.info("Branch already exists, skipping creation", branch=desired_branch_name)

        # Commit files to branch
        await commit_files_to_branch(desired_issue, existing_issue, desired_branch_name, github_adapter)

        logger.info("Creating new PR for issue", branch=desired_branch_name, base_branch=default_branch)
        new_pr = await github_adapter.create_pull_request(
            title=pr.title,
            head=desired_branch_name,
            base=default_branch,
            body=pr_body,
        )
        logger.info("Created new PR", pr_number=new_pr.number, branch=desired_branch_name)
        await github_adapter.set_labels_on_issue(new_pr.number, pr_labels)
        logger.info("Set labels on new PR", pr_number=new_pr.number, labels=pr_labels)
    elif pr_sync_decision == SyncDecision.UPDATE:
        logger.info("Updating existing PR for issue", pr_number=existing_pull_request.number, branch=desired_branch_name)
        await github_adapter.update_pull_request(
            pull_number=existing_pull_request.number,
            title=pr.title,
            body=pr_body,
        )
        await github_adapter.set_labels_on_issue(existing_pull_request.number, pr_labels)
        pr_file_sync_decision = await decide_github_pull_request_file_sync_action(pr.files, existing_pull_request, github_adapter)
        if pr_file_sync_decision == SyncDecision.CREATE:
            # The branch will already exist, so we don't need to create it.
            # However, we do need to commit the files to the branch.
            await commit_files_to_branch(desired_issue, existing_issue, desired_branch_name, github_adapter)


async def sync_github_pull_requests(
    desired_issues: list[IssueModel],
    existing_issues: list[Issue],
    existing_pull_requests: list[PullRequest],
    github_adapter: GitHubKitAdapter,
    default_branch: str,
) -> None:
    """Process pull requests for issues that specify a pull_request field."""
    desired_issues_with_prs = [issue for issue in desired_issues if issue.pull_request is not None]
    for desired_issue in desired_issues_with_prs:
        existing_issue = next((issue for issue in existing_issues if issue.title == desired_issue.title), None)
        if existing_issue is None:
            logger.error("Issue not found in existing issues", issue_title=desired_issue.title)
            continue

        # Find existing PR associated with existing issue, if any.
        existing_pr = await get_pull_request_associated_with_issue(existing_issue, existing_pull_requests)

        await sync_github_pull_request(desired_issue, existing_issue, github_adapter, default_branch, existing_pull_request=existing_pr)
