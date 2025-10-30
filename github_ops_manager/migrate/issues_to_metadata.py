"""Migration logic to embed issue/PR metadata from issues.yaml into test_cases.yaml files."""

from pathlib import Path

import structlog
from githubkit.versions.latest.models import Issue, PullRequest

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.test_cases_processor import find_test_cases_files, load_test_cases_yaml, save_test_cases_yaml
from github_ops_manager.processing.yaml_processor import YAMLProcessor
from github_ops_manager.schemas.default_issue import IssuesYAMLModel
from github_ops_manager.synchronize.pull_requests import get_pull_request_associated_with_issue

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def find_github_issue_by_title(title: str, github_adapter: GitHubKitAdapter) -> Issue | None:
    """Find a GitHub issue by matching title.

    Args:
        title: Issue title to search for
        github_adapter: GitHub adapter for API calls

    Returns:
        GitHub Issue object if found, None otherwise
    """
    logger.info("Searching for GitHub issue by title", title=title)
    all_issues = await github_adapter.list_issues()

    for issue in all_issues:
        if issue.title == title:
            logger.info("Found matching GitHub issue", title=title, issue_number=issue.number)
            return issue

    logger.warning("No matching GitHub issue found", title=title)
    return None


def find_test_case_by_title(title: str, test_cases_dir: Path) -> tuple[Path, dict, dict] | None:
    """Find a test case in test_cases.yaml files by matching title.

    Args:
        title: Test case title to search for
        test_cases_dir: Directory containing test_cases.yaml files

    Returns:
        Tuple of (file_path, test_case_dict, parent_data_dict) if found, None otherwise
    """
    logger.info("Searching for test case by title", title=title, test_cases_dir=str(test_cases_dir))
    test_case_files = find_test_cases_files(test_cases_dir)

    for test_case_file in test_case_files:
        data = load_test_cases_yaml(test_case_file)
        if not data or "test_cases" not in data:
            continue

        test_cases = data["test_cases"]
        if not isinstance(test_cases, list):
            logger.warning("test_cases field is not a list", filepath=str(test_case_file))
            continue

        for test_case in test_cases:
            if test_case.get("title") == title:
                logger.info("Found matching test case", title=title, file=str(test_case_file))
                return (test_case_file, test_case, data)

    logger.warning("No matching test case found", title=title)
    return None


def update_test_case_with_project_metadata(test_case: dict, github_issue: Issue, github_pr: PullRequest | None, base_url: str) -> dict:
    """Add project issue/PR metadata fields to test case.

    Args:
        test_case: Test case dictionary to update
        github_issue: GitHub Issue object
        github_pr: GitHub PullRequest object (optional)
        base_url: Base URL for the repository (e.g., "https://wwwin-github.cisco.com")

    Returns:
        Updated test case dictionary
    """
    test_case["project_issue_number"] = github_issue.number
    test_case["project_issue_url"] = github_issue.html_url or f"{base_url}/issues/{github_issue.number}"

    if github_pr:
        test_case["project_pr_number"] = github_pr.number
        test_case["project_pr_url"] = github_pr.html_url or f"{base_url}/pull/{github_pr.number}"
        test_case["project_pr_branch"] = github_pr.head.ref

        logger.info(
            "Updated test case with project issue and PR metadata",
            title=test_case.get("title"),
            issue_number=github_issue.number,
            pr_number=github_pr.number,
            pr_branch=github_pr.head.ref,
        )
    else:
        logger.info(
            "Updated test case with project issue metadata (no PR)",
            title=test_case.get("title"),
            issue_number=github_issue.number,
        )

    return test_case


async def migrate_issues_to_metadata(
    issues_yaml_path: Path,
    test_cases_dir: Path,
    github_adapter: GitHubKitAdapter,
    github_api_url: str,
) -> dict:
    """Migrate issue/PR metadata from issues.yaml to test_cases.yaml files.

    Args:
        issues_yaml_path: Path to issues.yaml file
        test_cases_dir: Directory containing test_cases.yaml files
        github_adapter: GitHub adapter for API calls
        github_api_url: GitHub API URL for constructing URLs

    Returns:
        Dictionary with migration statistics
    """
    logger.info("Starting migration from issues.yaml to test_cases.yaml", issues_yaml=str(issues_yaml_path), test_cases_dir=str(test_cases_dir))

    # Build base URL
    if "api.github.com" in github_api_url:
        base_url = "https://github.com"
    else:
        base_url = github_api_url.replace("/api/v3", "").replace("/api", "").rstrip("/")

    # Load issues.yaml
    processor = YAMLProcessor()
    issues_model: IssuesYAMLModel = processor.load_issues_model([str(issues_yaml_path)])

    # Fetch all PRs once for efficiency
    logger.info("Fetching all pull requests from GitHub")
    simple_prs = await github_adapter.list_pull_requests()
    all_prs = [await github_adapter.get_pull_request(pr.number) for pr in simple_prs]
    logger.info("Fetched pull requests", count=len(all_prs))

    stats = {
        "issues_processed": 0,
        "test_cases_updated": 0,
        "issues_without_test_case": [],
        "issues_without_github_issue": [],
    }

    # Process each issue from issues.yaml
    for issue_model in issues_model.issues:
        logger.info("Processing issue from issues.yaml", title=issue_model.title)
        stats["issues_processed"] += 1

        # Find corresponding GitHub issue
        github_issue = await find_github_issue_by_title(issue_model.title, github_adapter)
        if not github_issue:
            logger.warning("Could not find GitHub issue for issues.yaml entry", title=issue_model.title)
            stats["issues_without_github_issue"].append(issue_model.title)
            continue

        # Find corresponding PR
        github_pr = await get_pull_request_associated_with_issue(github_issue, all_prs)

        # Find corresponding test case
        result = find_test_case_by_title(issue_model.title, test_cases_dir)
        if not result:
            logger.warning("Could not find test case for issue", title=issue_model.title)
            stats["issues_without_test_case"].append(issue_model.title)
            continue

        test_case_file, test_case, data = result

        # Update test case with metadata
        update_test_case_with_project_metadata(test_case, github_issue, github_pr, base_url)

        # Save updated test_cases.yaml
        if save_test_cases_yaml(test_case_file, data):
            stats["test_cases_updated"] += 1
            logger.info("Successfully updated test case file", file=str(test_case_file), title=issue_model.title)
        else:
            logger.error("Failed to save test case file", file=str(test_case_file), title=issue_model.title)

    # Find orphaned test cases (test cases without issue metadata)
    logger.info("Identifying orphaned test cases")
    orphaned_test_cases = []
    test_case_files = find_test_cases_files(test_cases_dir)

    for test_case_file in test_case_files:
        data = load_test_cases_yaml(test_case_file)
        if not data or "test_cases" not in data:
            continue

        for test_case in data.get("test_cases", []):
            # Check if test case has project metadata
            if not test_case.get("project_issue_number"):
                orphaned_test_cases.append(test_case.get("title", "Untitled"))

    stats["orphaned_test_cases"] = orphaned_test_cases
    logger.info("Migration complete", stats=stats)

    return stats
