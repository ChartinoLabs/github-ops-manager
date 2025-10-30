"""Synchronization logic for GitHub pull requests using embedded metadata from test_cases.yaml."""

import time
from pathlib import Path

import structlog
from githubkit.versions.latest.models import Issue, PullRequest

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.test_cases_processor import find_test_cases_files, load_test_cases_yaml, save_test_cases_yaml
from github_ops_manager.synchronize.models import SyncDecision
from github_ops_manager.utils.helpers import generate_branch_name

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def build_pr_url(github_api_url: str, repo: str, pr_number: int) -> str:
    """Build full URL to GitHub pull request.

    Args:
        github_api_url: GitHub API URL
        repo: Repository name (owner/repo)
        pr_number: PR number

    Returns:
        Full URL to PR
    """
    if "api.github.com" in github_api_url:
        base_url = "https://github.com"
    else:
        base_url = github_api_url.replace("/api/v3", "").replace("/api", "").rstrip("/")
    return f"{base_url}/{repo}/pull/{pr_number}"


async def sync_test_case_pull_request(
    test_case: dict,
    test_case_file: Path,
    test_case_data: dict,
    github_issue: Issue,
    github_adapter: GitHubKitAdapter,
    default_branch: str,
    base_directory: Path,
    github_api_url: str,
    repo: str,
) -> tuple[PullRequest | None, SyncDecision]:
    """Synchronize a single test case's pull request using embedded metadata.

    Args:
        test_case: Test case dictionary
        test_case_file: Path to test case file
        test_case_data: Full test case file data (for saving)
        github_issue: GitHub Issue for this test case
        github_adapter: GitHub adapter
        default_branch: Default branch name
        base_directory: Base directory for file resolution
        github_api_url: GitHub API URL for constructing URLs
        repo: Repository name (owner/repo)

    Returns:
        Tuple of (GitHub PullRequest or None, SyncDecision)
    """
    title = test_case.get("title", "Untitled Test Case")
    generated_script_path = test_case.get("generated_script_path")

    # Check if test case has a generated script
    if not generated_script_path:
        logger.info("Test case has no generated script, skipping PR", title=title)
        return (None, SyncDecision.NOOP)

    # Check if test case has existing PR metadata
    existing_pr_number = test_case.get("project_pr_number")

    if existing_pr_number:
        # Fetch PR directly by number
        logger.info("Fetching existing PR by number", title=title, pr_number=existing_pr_number)
        try:
            github_pr = await github_adapter.get_pull_request(existing_pr_number)
            logger.info("PR is up to date", title=title, pr_number=existing_pr_number)
            return (github_pr, SyncDecision.NOOP)

        except Exception as e:
            logger.warning(
                "Failed to fetch existing PR, will create new one",
                title=title,
                pr_number=existing_pr_number,
                error=str(e),
            )
            # Fall through to create new PR

    # Create new PR
    logger.info("Creating new PR for test case", title=title)

    # Generate branch name
    branch_name = test_case.get("project_pr_branch")
    if not branch_name:
        branch_name = generate_branch_name(github_issue.number, title)

    # Check if branch exists
    if not await github_adapter.branch_exists(branch_name):
        logger.info("Creating branch for PR", branch=branch_name, base_branch=default_branch)
        await github_adapter.create_branch(branch_name, default_branch)
    else:
        logger.info("Branch already exists", branch=branch_name)

    # Commit files to branch
    script_file_path = base_directory / generated_script_path
    if not script_file_path.exists():
        logger.error("Generated script not found", file=str(script_file_path), title=title)
        return (None, SyncDecision.NOOP)

    file_content = script_file_path.read_text(encoding="utf-8")
    commit_message = f"feat: add test script for issue #{github_issue.number}"
    files_to_commit = [(generated_script_path, file_content)]

    logger.info("Committing files to branch", branch=branch_name, file=generated_script_path)
    await github_adapter.commit_files_to_branch(branch_name, files_to_commit, commit_message)

    # Create PR
    pr_title = f"feat: {title}"
    pr_body = f"Automated test script for issue #{github_issue.number}.\\n\\nCloses #{github_issue.number}"

    logger.info("Creating PR", branch=branch_name, base_branch=default_branch, title=pr_title)
    github_pr = await github_adapter.create_pull_request(
        title=pr_title,
        head=branch_name,
        base=default_branch,
        body=pr_body,
    )

    # Write metadata back to test case
    test_case["project_pr_number"] = github_pr.number
    test_case["project_pr_url"] = build_pr_url(github_api_url, repo, github_pr.number)
    test_case["project_pr_branch"] = branch_name

    logger.info(
        "Created PR and wrote metadata back",
        title=title,
        pr_number=github_pr.number,
        pr_branch=branch_name,
        file=str(test_case_file),
    )

    # Save test case file
    if not save_test_cases_yaml(test_case_file, test_case_data):
        logger.error("Failed to save test case file after creating PR", file=str(test_case_file))

    return (github_pr, SyncDecision.CREATE)


async def sync_test_cases_pull_requests(
    test_cases_dir: Path,
    github_adapter: GitHubKitAdapter,
    default_branch: str,
    base_directory: Path,
    github_api_url: str,
    repo: str,
) -> dict:
    """Synchronize pull requests for all test cases using embedded metadata.

    Args:
        test_cases_dir: Directory containing test_cases.yaml files
        github_adapter: GitHub adapter
        default_branch: Default branch name
        base_directory: Base directory for file resolution
        github_api_url: GitHub API URL
        repo: Repository name (owner/repo)

    Returns:
        Dictionary with synchronization statistics
    """
    logger.info("Synchronizing PRs from test_cases.yaml files", test_cases_dir=str(test_cases_dir))

    start_time = time.time()

    stats = {
        "test_cases_processed": 0,
        "prs_created": 0,
        "prs_updated": 0,
        "prs_unchanged": 0,
        "prs_skipped": 0,
        "errors": [],
    }

    test_case_files = find_test_cases_files(test_cases_dir)

    for test_case_file in test_case_files:
        data = load_test_cases_yaml(test_case_file)
        if not data or "test_cases" not in data:
            continue

        test_cases = data.get("test_cases", [])
        if not isinstance(test_cases, list):
            continue

        for test_case in test_cases:
            title = test_case.get("title", "Untitled")
            stats["test_cases_processed"] += 1

            # Skip catalog-destined test cases (handled separately)
            if test_case.get("catalog_destined"):
                logger.info("Skipping catalog-destined test case", title=title)
                stats["prs_skipped"] += 1
                continue

            # Check if test case has issue
            issue_number = test_case.get("project_issue_number")
            if not issue_number:
                logger.info("Test case has no project issue, skipping PR", title=title)
                stats["prs_skipped"] += 1
                continue

            try:
                # Fetch issue
                github_issue = await github_adapter.get_issue(issue_number)

                # Sync PR
                github_pr, decision = await sync_test_case_pull_request(
                    test_case=test_case,
                    test_case_file=test_case_file,
                    test_case_data=data,
                    github_issue=github_issue,
                    github_adapter=github_adapter,
                    default_branch=default_branch,
                    base_directory=base_directory,
                    github_api_url=github_api_url,
                    repo=repo,
                )

                if decision == SyncDecision.CREATE:
                    stats["prs_created"] += 1
                elif decision == SyncDecision.UPDATE:
                    stats["prs_updated"] += 1
                elif decision == SyncDecision.NOOP:
                    if github_pr:
                        stats["prs_unchanged"] += 1
                    else:
                        stats["prs_skipped"] += 1

            except Exception as e:
                logger.error("Failed to sync test case PR", title=title, error=str(e))
                stats["errors"].append({"title": title, "error": str(e)})

    end_time = time.time()
    duration = end_time - start_time

    logger.info(
        "Completed PR synchronization",
        duration=round(duration, 2),
        test_cases_processed=stats["test_cases_processed"],
        prs_created=stats["prs_created"],
        prs_updated=stats["prs_updated"],
        prs_unchanged=stats["prs_unchanged"],
        prs_skipped=stats["prs_skipped"],
        errors=len(stats["errors"]),
    )

    return stats
