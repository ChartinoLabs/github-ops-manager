"""Contains logic for creating tracking issues for catalog PRs and parameter learning tasks."""

from pathlib import Path
from typing import Any

import structlog
from githubkit.versions.latest.models import Issue, PullRequest
from jinja2 import Environment, FileSystemLoader, Template

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.test_cases_processor import (
    load_test_cases_yaml,
    save_test_cases_yaml,
    update_test_case_with_issue_metadata,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Set up Jinja2 environment for loading templates
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)


def load_tracking_issue_template() -> Template:
    """Load the tracking issue template from disk.

    Returns:
        Jinja2 Template object
    """
    return jinja_env.get_template("tracking_issue.j2")


def strip_os_tag_from_title(title: str) -> str:
    """Strip OS tag prefix from test case title.

    Removes leading OS tags like [IOS-XE], [NX-OS], etc. from the title
    to get the clean test case group name that appears in cxtm.yaml.

    Args:
        title: Test case title potentially with OS tag prefix

    Returns:
        Title without OS tag prefix

    Examples:
        >>> strip_os_tag_from_title("[IOS-XE] Verify Interface Status")
        "Verify Interface Status"
        >>> strip_os_tag_from_title("[NX-OS] Check BGP Neighbors")
        "Check BGP Neighbors"
        >>> strip_os_tag_from_title("Verify LLDP on all devices")
        "Verify LLDP on all devices"
    """
    import re

    # Pattern matches [ANYTHING] at the start of the string, followed by optional whitespace
    pattern = r"^\[.*?\]\s*"
    cleaned_title = re.sub(pattern, "", title)
    return cleaned_title


async def create_tracking_issue_for_catalog_pr(
    github_adapter: GitHubKitAdapter,
    catalog_pr: PullRequest,
    test_cases: list[dict[str, Any]],
    os_name: str,
    catalog_repo: str,
    labels: list[str] | None = None,
) -> Issue:
    """Create a tracking issue in project repo for a catalog PR.

    Args:
        github_adapter: GitHub adapter for project repository
        catalog_pr: The catalog PR that was created
        test_cases: List containing single test case dict (always one test case per catalog PR)
        os_name: Operating system name (e.g., "ios-xe", "nxos")
        catalog_repo: Catalog repository name (owner/repo)
        labels: Optional list of label names to apply to the issue

    Returns:
        Created Issue object
    """
    # Build issue title
    # Since each catalog PR contains exactly one test case, get the test case title
    test_case = test_cases[0]
    test_case_title = test_case.get("title", "Untitled Test Case")

    # Strip OS tag from title for CLI commands (e.g., "[IOS-XE] Do Thing" -> "Do Thing")
    # This matches the test case group name that will appear in cxtm.yaml
    clean_title = strip_os_tag_from_title(test_case_title)

    title = f"Review Catalog PR and Learn Parameters: {test_case_title}"

    # Load and render the tracking issue template
    template = load_tracking_issue_template()
    body = template.render(
        catalog_pr_title=catalog_pr.title,
        catalog_pr_url=catalog_pr.html_url,
        catalog_pr_number=catalog_pr.number,
        catalog_branch=catalog_pr.head.ref,
        test_case_title=test_case_title,  # Original title with OS tag for display
        test_case_title_clean=clean_title,  # Clean title for CLI commands
        os_name=os_name.upper(),
    )

    logger.info(
        "Creating tracking issue in project repository",
        catalog_pr_number=catalog_pr.number,
        catalog_pr_url=catalog_pr.html_url,
        test_case_title=test_case_title,
        os_name=os_name,
    )

    # Create the issue
    issue = await github_adapter.create_issue(
        title=title,
        body=body,
    )

    # Apply labels if provided
    if labels:
        logger.info("Applying labels to tracking issue", issue_number=issue.number, labels=labels)
        await github_adapter.set_labels_on_issue(issue.number, labels)

    logger.info(
        "Created tracking issue",
        issue_number=issue.number,
        issue_url=issue.html_url,
        catalog_pr_number=catalog_pr.number,
    )

    # Write issue metadata back to test_cases.yaml
    source_file_path = test_case.get("_source_file")
    if source_file_path:
        source_file = Path(source_file_path)
        logger.info("Writing project issue metadata back to test case file", source_file=str(source_file))

        # Reload the source file
        data = load_test_cases_yaml(source_file)
        if data and "test_cases" in data:
            # Find the test case and update it
            # Match by title since that's unique and reliable
            for tc in data["test_cases"]:
                if tc.get("title") == test_case_title:
                    update_test_case_with_issue_metadata(tc, issue.number, issue.html_url)
                    break

            # Save back to file
            if save_test_cases_yaml(source_file, data):
                logger.info("Successfully wrote project issue metadata back to test case file", source_file=str(source_file))
            else:
                logger.error("Failed to save test case file", source_file=str(source_file))
        else:
            logger.warning("Could not load test cases from source file", source_file=str(source_file))
    else:
        logger.warning("Test case missing _source_file metadata, cannot write back issue metadata", test_case_title=test_case_title)

    return issue


async def create_tracking_issues_for_catalog_prs(
    github_adapter: GitHubKitAdapter,
    catalog_pr_data: list[dict[str, Any]],
    catalog_repo: str,
    labels: list[str] | None = None,
) -> list[Issue]:
    """Create tracking issues for all catalog PRs that were created.

    Args:
        github_adapter: GitHub adapter for project repository
        catalog_pr_data: List of dicts with keys: pr, test_cases, os_name
        catalog_repo: Catalog repository name (owner/repo)
        labels: Optional list of label names to apply to issues

    Returns:
        List of created Issue objects
    """
    if not catalog_pr_data:
        logger.info("No catalog PR data provided, skipping tracking issue creation")
        return []

    logger.info("Creating tracking issues for catalog PRs", count=len(catalog_pr_data), catalog_repo=catalog_repo)

    created_issues = []

    for pr_data in catalog_pr_data:
        pr = pr_data["pr"]
        test_cases = pr_data["test_cases"]
        os_name = pr_data["os_name"]

        try:
            issue = await create_tracking_issue_for_catalog_pr(
                github_adapter=github_adapter,
                catalog_pr=pr,
                test_cases=test_cases,
                os_name=os_name,
                catalog_repo=catalog_repo,
                labels=labels,
            )
            created_issues.append(issue)
        except Exception as e:
            logger.error(
                "Failed to create tracking issue for catalog PR",
                catalog_pr_number=pr.number,
                error=str(e),
                exc_info=True,
            )

    logger.info("Completed tracking issue creation", created_count=len(created_issues), total_prs=len(catalog_pr_data))

    return created_issues
