"""Synchronization logic for GitHub issues using embedded metadata from test_cases.yaml."""

import time
from pathlib import Path

import structlog
from githubkit.versions.latest.models import Issue

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.test_cases_processor import find_test_cases_files, load_test_cases_yaml, save_test_cases_yaml
from github_ops_manager.synchronize.models import SyncDecision

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def build_issue_url(github_api_url: str, repo: str, issue_number: int) -> str:
    """Build full URL to GitHub issue.

    Args:
        github_api_url: GitHub API URL
        repo: Repository name (owner/repo)
        issue_number: Issue number

    Returns:
        Full URL to issue
    """
    if "api.github.com" in github_api_url:
        base_url = "https://github.com"
    else:
        base_url = github_api_url.replace("/api/v3", "").replace("/api", "").rstrip("/")
    return f"{base_url}/{repo}/issues/{issue_number}"


async def sync_test_case_issue(
    test_case: dict,
    test_case_file: Path,
    test_case_data: dict,
    github_adapter: GitHubKitAdapter,
    github_api_url: str,
    repo: str,
) -> tuple[Issue, SyncDecision]:
    """Synchronize a single test case's issue using embedded metadata.

    Args:
        test_case: Test case dictionary
        test_case_file: Path to test case file
        test_case_data: Full test case file data (for saving)
        github_adapter: GitHub adapter
        github_api_url: GitHub API URL for constructing URLs
        repo: Repository name (owner/repo)

    Returns:
        Tuple of (GitHub Issue, SyncDecision)
    """
    title = test_case.get("title", "Untitled Test Case")
    purpose = test_case.get("purpose", "")
    labels = test_case.get("labels", [])

    # Check if test case has existing issue metadata
    existing_issue_number = test_case.get("project_issue_number")

    if existing_issue_number:
        # Fetch issue directly by number (fast!)
        logger.info("Fetching existing issue by number", title=title, issue_number=existing_issue_number)
        try:
            github_issue = await github_adapter.get_issue(existing_issue_number)

            # Check if update is needed
            needs_update = False
            if github_issue.body != purpose:
                logger.info("Issue body needs update", title=title, issue_number=existing_issue_number)
                needs_update = True

            # Check labels
            existing_label_names = {label.name if hasattr(label, "name") else str(label) for label in (github_issue.labels or [])}
            desired_label_names = set(labels or [])
            if existing_label_names != desired_label_names:
                logger.info("Issue labels need update", title=title, issue_number=existing_issue_number)
                needs_update = True

            if needs_update:
                logger.info("Updating existing issue", title=title, issue_number=existing_issue_number)
                await github_adapter.update_issue(
                    issue_number=existing_issue_number,
                    body=purpose,
                    labels=labels,
                )
                # Fetch updated issue
                github_issue = await github_adapter.get_issue(existing_issue_number)
                return (github_issue, SyncDecision.UPDATE)
            else:
                logger.info("Issue is up to date", title=title, issue_number=existing_issue_number)
                return (github_issue, SyncDecision.NOOP)

        except Exception as e:
            logger.warning(
                "Failed to fetch existing issue, will create new one",
                title=title,
                issue_number=existing_issue_number,
                error=str(e),
            )
            # Fall through to create new issue

    # Create new issue
    logger.info("Creating new issue", title=title)
    github_issue = await github_adapter.create_issue(
        title=title,
        body=purpose,
        labels=labels,
    )

    # Write metadata back to test case
    test_case["project_issue_number"] = github_issue.number
    test_case["project_issue_url"] = build_issue_url(github_api_url, repo, github_issue.number)

    logger.info(
        "Created issue and wrote metadata back",
        title=title,
        issue_number=github_issue.number,
        file=str(test_case_file),
    )

    # Save test case file
    if not save_test_cases_yaml(test_case_file, test_case_data):
        logger.error("Failed to save test case file after creating issue", file=str(test_case_file))

    return (github_issue, SyncDecision.CREATE)


async def sync_test_cases_issues(
    test_cases_dir: Path,
    github_adapter: GitHubKitAdapter,
    github_api_url: str,
    repo: str,
) -> dict:
    """Synchronize issues for all test cases using embedded metadata.

    Args:
        test_cases_dir: Directory containing test_cases.yaml files
        github_adapter: GitHub adapter
        github_api_url: GitHub API URL
        repo: Repository name (owner/repo)

    Returns:
        Dictionary with synchronization statistics
    """
    logger.info("Synchronizing issues from test_cases.yaml files", test_cases_dir=str(test_cases_dir))

    start_time = time.time()

    stats = {
        "test_cases_processed": 0,
        "issues_created": 0,
        "issues_updated": 0,
        "issues_unchanged": 0,
        "errors": [],
    }

    test_case_files = find_test_cases_files(test_cases_dir)
    logger.info("Found test case files", count=len(test_case_files))

    for test_case_file in test_case_files:
        data = load_test_cases_yaml(test_case_file)
        if not data or "test_cases" not in data:
            logger.warning("Skipping file without test_cases", file=str(test_case_file))
            continue

        test_cases = data.get("test_cases", [])
        if not isinstance(test_cases, list):
            logger.warning("test_cases is not a list", file=str(test_case_file))
            continue

        for test_case in test_cases:
            title = test_case.get("title", "Untitled")
            logger.info("Processing test case", title=title, file=str(test_case_file))
            stats["test_cases_processed"] += 1

            try:
                github_issue, decision = await sync_test_case_issue(
                    test_case=test_case,
                    test_case_file=test_case_file,
                    test_case_data=data,
                    github_adapter=github_adapter,
                    github_api_url=github_api_url,
                    repo=repo,
                )

                if decision == SyncDecision.CREATE:
                    stats["issues_created"] += 1
                elif decision == SyncDecision.UPDATE:
                    stats["issues_updated"] += 1
                elif decision == SyncDecision.NOOP:
                    stats["issues_unchanged"] += 1

            except Exception as e:
                logger.error("Failed to sync test case issue", title=title, error=str(e))
                stats["errors"].append({"title": title, "error": str(e)})

    end_time = time.time()
    duration = end_time - start_time

    logger.info(
        "Completed issue synchronization",
        duration=round(duration, 2),
        test_cases_processed=stats["test_cases_processed"],
        issues_created=stats["issues_created"],
        issues_updated=stats["issues_updated"],
        issues_unchanged=stats["issues_unchanged"],
        errors=len(stats["errors"]),
    )

    return stats
