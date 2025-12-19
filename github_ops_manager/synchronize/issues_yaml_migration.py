"""Migration utilities for transitioning from issues.yaml to test_cases.yaml workflow.

╔══════════════════════════════════════════════════════════════════════════════╗
║  ⚠️  DEPRECATION NOTICE - PENDING REMOVAL POST-MIGRATION  ⚠️                 ║
║                                                                              ║
║  This module provides backwards compatibility with the legacy issues.yaml    ║
║  workflow. It migrates existing issue/PR metadata from issues.yaml to the    ║
║  new test_cases.yaml format.                                                 ║
║                                                                              ║
║  This entire module should be REMOVED once all projects have been migrated   ║
║  away from using issues.yaml files.                                          ║
║                                                                              ║
║  Migration tracking: Issues in issues.yaml are marked with `migrated: true`  ║
║  after their metadata has been written to the corresponding test case.       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from pathlib import Path
from typing import Any

import structlog

from github_ops_manager.processing.test_cases_processor import (
    load_all_test_cases,
    save_test_case_metadata,
    update_test_case_with_issue_metadata,
    update_test_case_with_project_pr_metadata,
)
from github_ops_manager.utils.yaml import dump_yaml_to_file, load_yaml_file

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def load_issues_yaml(issues_yaml_path: Path) -> dict[str, Any] | None:
    """Load and validate the issues.yaml file.

    ⚠️ DEPRECATED: Part of issues.yaml migration - remove post-migration.

    Args:
        issues_yaml_path: Path to the issues.yaml file

    Returns:
        Dictionary containing issues data, or None if file doesn't exist or is invalid
    """
    if not issues_yaml_path.exists():
        logger.info("No issues.yaml file found, skipping migration", path=str(issues_yaml_path))
        return None

    try:
        data = load_yaml_file(issues_yaml_path)
        if not isinstance(data, dict):
            logger.warning("issues.yaml is not a valid dictionary", path=str(issues_yaml_path))
            return None

        if "issues" not in data:
            logger.warning("issues.yaml has no 'issues' key", path=str(issues_yaml_path))
            return None

        logger.info(
            "Loaded issues.yaml for migration",
            path=str(issues_yaml_path),
            issue_count=len(data.get("issues", [])),
        )
        return data

    except Exception as e:
        logger.error("Failed to load issues.yaml", path=str(issues_yaml_path), error=str(e))
        return None


def is_issue_migrated(issue: dict[str, Any]) -> bool:
    """Check if an issue has already been migrated.

    ⚠️ DEPRECATED: Part of issues.yaml migration - remove post-migration.

    Args:
        issue: Issue dictionary from issues.yaml

    Returns:
        True if the issue has been migrated, False otherwise
    """
    return issue.get("migrated", False) is True


def mark_issue_as_migrated(issue: dict[str, Any]) -> None:
    """Mark an issue as migrated by setting the migrated field to true.

    ⚠️ DEPRECATED: Part of issues.yaml migration - remove post-migration.

    Args:
        issue: Issue dictionary to mark as migrated
    """
    issue["migrated"] = True


def find_matching_test_case(
    issue_title: str,
    test_cases: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Find a test case that matches the given issue title.

    ⚠️ DEPRECATED: Part of issues.yaml migration - remove post-migration.

    Matching is done by exact title comparison.

    Args:
        issue_title: Title of the issue to match
        test_cases: List of test case dictionaries

    Returns:
        Matching test case dictionary, or None if no match found
    """
    for test_case in test_cases:
        if test_case.get("title") == issue_title:
            logger.debug("Found matching test case", issue_title=issue_title)
            return test_case

    logger.debug("No matching test case found", issue_title=issue_title)
    return None


def extract_issue_metadata_from_issues_yaml(issue: dict[str, Any]) -> dict[str, Any] | None:
    """Extract issue metadata from an issues.yaml entry.

    ⚠️ DEPRECATED: Part of issues.yaml migration - remove post-migration.

    Args:
        issue: Issue dictionary from issues.yaml

    Returns:
        Dictionary with issue_number and issue_url, or None if not available
    """
    issue_number = issue.get("number")
    issue_url = issue.get("url")

    if issue_number is not None:
        return {
            "issue_number": issue_number,
            "issue_url": issue_url or "",
        }

    return None


def extract_pr_metadata_from_issues_yaml(issue: dict[str, Any]) -> dict[str, Any] | None:
    """Extract PR metadata from an issues.yaml entry.

    ⚠️ DEPRECATED: Part of issues.yaml migration - remove post-migration.

    Args:
        issue: Issue dictionary from issues.yaml

    Returns:
        Dictionary with PR metadata, or None if not available
    """
    pr_data = issue.get("pull_request")
    if not pr_data:
        return None

    pr_number = pr_data.get("number")
    if pr_number is None:
        return None

    return {
        "pr_number": pr_number,
        "pr_url": pr_data.get("url", ""),
        "pr_branch": pr_data.get("branch", ""),
    }


def migrate_issue_to_test_case(
    issue: dict[str, Any],
    test_case: dict[str, Any],
    repo_url: str,
) -> bool:
    """Migrate metadata from an issues.yaml issue to a test case.

    ⚠️ DEPRECATED: Part of issues.yaml migration - remove post-migration.

    This function reads metadata directly from the issues.yaml entry
    and writes it to the corresponding test case.

    Args:
        issue: Issue dictionary from issues.yaml
        test_case: Test case dictionary to update
        repo_url: Base URL of the repository

    Returns:
        True if migration was successful, False otherwise
    """
    title = issue.get("title")
    if not title:
        logger.warning("Issue has no title, skipping migration")
        return False

    logger.info("Migrating issue to test case", title=title)

    metadata_updated = False

    # Extract and apply issue metadata
    issue_metadata = extract_issue_metadata_from_issues_yaml(issue)
    if issue_metadata:
        update_test_case_with_issue_metadata(
            test_case,
            issue_metadata["issue_number"],
            issue_metadata["issue_url"],
        )
        metadata_updated = True
        logger.debug(
            "Applied issue metadata",
            title=title,
            issue_number=issue_metadata["issue_number"],
        )

    # Extract and apply PR metadata
    pr_metadata = extract_pr_metadata_from_issues_yaml(issue)
    if pr_metadata:
        update_test_case_with_project_pr_metadata(
            test_case,
            pr_metadata["pr_number"],
            pr_metadata["pr_url"],
            pr_metadata["pr_branch"],
            repo_url,
        )
        metadata_updated = True
        logger.debug(
            "Applied PR metadata",
            title=title,
            pr_number=pr_metadata["pr_number"],
        )

    if not metadata_updated:
        logger.warning(
            "No issue or PR metadata found in issues.yaml entry",
            title=title,
        )
        return False

    # Save the test case metadata back to its source file
    if save_test_case_metadata(test_case):
        logger.info("Successfully migrated issue to test case", title=title)
        return True
    else:
        logger.error("Failed to save migrated test case metadata", title=title)
        return False


def run_issues_yaml_migration(
    issues_yaml_path: Path,
    test_cases_dir: Path,
    repo_url: str,
) -> dict[str, Any]:
    """Run the migration from issues.yaml to test_cases.yaml.

    ⚠️ DEPRECATED: Part of issues.yaml migration - remove post-migration.

    TODO: Remove this function and the entire issues_yaml_migration module
    once all projects have been migrated away from issues.yaml.

    This function:
    1. Loads the issues.yaml file
    2. Loads all test cases from test_cases.yaml files
    3. For each non-migrated issue in issues.yaml:
       a. Finds the matching test case by title
       b. Extracts issue/PR metadata from issues.yaml
       c. Updates the test case with the metadata
       d. Marks the issue as migrated in issues.yaml
    4. Saves the updated issues.yaml file

    Args:
        issues_yaml_path: Path to the issues.yaml file
        test_cases_dir: Directory containing test_cases.yaml files
        repo_url: Base URL of the repository

    Returns:
        Dictionary with migration statistics:
        - total_issues: Total number of issues in issues.yaml
        - already_migrated: Number of issues already marked as migrated
        - newly_migrated: Number of issues migrated in this run
        - skipped_no_match: Number of issues skipped (no matching test case)
        - skipped_no_metadata: Number of issues skipped (no metadata to migrate)
        - errors: List of error messages
    """
    results: dict[str, Any] = {
        "total_issues": 0,
        "already_migrated": 0,
        "newly_migrated": 0,
        "skipped_no_match": 0,
        "skipped_no_metadata": 0,
        "errors": [],
    }

    # Load issues.yaml
    issues_data = load_issues_yaml(issues_yaml_path)
    if issues_data is None:
        logger.info("No issues.yaml to migrate")
        return results

    issues = issues_data.get("issues", [])
    results["total_issues"] = len(issues)

    if not issues:
        logger.info("No issues in issues.yaml to migrate")
        return results

    # Load all test cases
    test_cases = load_all_test_cases(test_cases_dir)
    if not test_cases:
        logger.warning("No test cases found, cannot perform migration")
        results["errors"].append("No test cases found in test_cases_dir")
        return results

    logger.info(
        "Starting issues.yaml migration",
        issues_count=len(issues),
        test_cases_count=len(test_cases),
    )

    issues_modified = False

    for issue in issues:
        title = issue.get("title", "Unknown")

        # Skip already migrated issues
        if is_issue_migrated(issue):
            logger.debug("Issue already migrated, skipping", title=title)
            results["already_migrated"] += 1
            continue

        # Check if there's any metadata to migrate
        has_issue_metadata = extract_issue_metadata_from_issues_yaml(issue) is not None
        has_pr_metadata = extract_pr_metadata_from_issues_yaml(issue) is not None

        if not has_issue_metadata and not has_pr_metadata:
            logger.debug("No metadata to migrate for issue", title=title)
            results["skipped_no_metadata"] += 1
            continue

        # Find matching test case
        matching_test_case = find_matching_test_case(title, test_cases)
        if matching_test_case is None:
            logger.warning("No matching test case found for issue", title=title)
            results["skipped_no_match"] += 1
            continue

        # Migrate the issue metadata to the test case
        try:
            success = migrate_issue_to_test_case(
                issue,
                matching_test_case,
                repo_url,
            )

            if success:
                # Mark the issue as migrated
                mark_issue_as_migrated(issue)
                issues_modified = True
                results["newly_migrated"] += 1
                logger.info("Successfully migrated issue", title=title)
            else:
                results["errors"].append(f"Failed to migrate issue: {title}")

        except Exception as e:
            logger.error("Error migrating issue", title=title, error=str(e))
            results["errors"].append(f"Error migrating {title}: {str(e)}")

    # Save updated issues.yaml if any issues were migrated
    if issues_modified:
        try:
            dump_yaml_to_file(issues_data, issues_yaml_path)
            logger.info("Saved updated issues.yaml with migration markers")
        except Exception as e:
            logger.error("Failed to save updated issues.yaml", error=str(e))
            results["errors"].append(f"Failed to save issues.yaml: {str(e)}")

    logger.info(
        "Completed issues.yaml migration",
        total=results["total_issues"],
        already_migrated=results["already_migrated"],
        newly_migrated=results["newly_migrated"],
        skipped_no_match=results["skipped_no_match"],
        skipped_no_metadata=results["skipped_no_metadata"],
        errors=len(results["errors"]),
    )

    return results
