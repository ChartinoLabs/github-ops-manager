"""Handles processing of test case YAML files for catalog workflow.

This module provides utilities for finding, loading, updating, and saving
test case definition files, particularly for writing PR metadata back after
catalog PR creation.
"""

from pathlib import Path
from typing import Any

import structlog
from githubkit.versions.latest.models import PullRequest
from ruamel.yaml import YAML

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Initialize YAML handler with format preservation
yaml = YAML()
yaml.preserve_quotes = True
yaml.default_flow_style = False
yaml.width = 4096  # Prevent line wrapping
yaml.indent(mapping=2, sequence=4, offset=2)  # Match original file formatting (- indented 2 from parent)


# Mapping from tac-quicksilver normalized OS to catalog directory names
OS_TO_CATALOG_DIR_MAP = {
    "iosxe": "IOS-XE",
    "ios-xe": "IOS-XE",
    "ios_xe": "IOS-XE",
    "nxos": "NX-OS",
    "nx-os": "NX-OS",
    "nx_os": "NX-OS",
    "iosxr": "IOS-XR",
    "ios-xr": "IOS-XR",
    "ios_xr": "IOS-XR",
    "ios": "IOS",
    "ise": "ISE",
    "aci": "ACI",
    "sdwan": "SD-WAN",
    "sd-wan": "SD-WAN",
    "dnac": "DNAC",
    "catalyst_center": "DNAC",
    "spirent": "Spirent",
}


def normalize_os_to_catalog_dir(os_name: str) -> str:
    """Convert normalized OS name to catalog directory name.

    Args:
        os_name: The OS name in normalized form (e.g., "iosxe", "nxos")

    Returns:
        Catalog directory name (e.g., "IOS-XE", "NX-OS")

    Example:
        >>> normalize_os_to_catalog_dir("ios_xe")
        'IOS-XE'
        >>> normalize_os_to_catalog_dir("nxos")
        'NX-OS'
    """
    normalized = OS_TO_CATALOG_DIR_MAP.get(os_name.lower(), os_name.upper())
    logger.debug("Normalized OS name to catalog directory", os_name=os_name, catalog_dir=normalized)
    return normalized


def extract_os_from_robot_content(robot_content: str) -> str | None:
    """Extract OS from robot file Test Tags section.

    Looks for the os:<os> tag in the Test Tags section of a Robot Framework file.
    This is more reliable than filename parsing since tags are structured metadata.

    Args:
        robot_content: Complete content of robot file

    Returns:
        Extracted OS name (e.g., "ios-xe", "nx-os") or None if not found

    Example:
        >>> content = '''
        ... Test Tags
        ... ...    os:ios-xe
        ... ...    category:foundations
        ... '''
        >>> extract_os_from_robot_content(content)
        'ios-xe'
    """
    import re

    # Regex pattern to find os:<os> tag in Test Tags section
    # Matches: os:ios-xe, os:nx-os, etc.
    pattern = r"(?:^|\s)os:(\S+)"

    match = re.search(pattern, robot_content, re.MULTILINE | re.IGNORECASE)

    if match:
        os_value = match.group(1).lower()
        logger.debug("Extracted OS from Test Tags", os=os_value)
        return os_value

    logger.warning("Could not find os: tag in robot file Test Tags section")
    return None


def extract_os_from_robot_filename(filename: str) -> str | None:
    """Extract OS from robot filename pattern like verify_ios_xe_*.robot.

    This is a fallback method if Test Tags parsing fails.
    Prefer extract_os_from_robot_content() for more reliable extraction.

    Args:
        filename: Robot filename (e.g., "verify_ios_xe_interfaces.robot")

    Returns:
        Extracted OS name or None if pattern doesn't match

    Example:
        >>> extract_os_from_robot_filename("verify_ios_xe_interfaces.robot")
        'ios_xe'
        >>> extract_os_from_robot_filename("verify_nx_os_vlans.robot")
        'nx_os'
    """
    # Remove .robot extension
    base_name = filename.replace(".robot", "")

    # Pattern: <action>_<os>_<feature>.robot
    # OS is typically second part (verify_ios_xe_...)
    parts = base_name.split("_")

    if len(parts) >= 3:
        # Try two-part OS first (ios_xe, nx_os, ios_xr)
        potential_os = f"{parts[1]}_{parts[2]}"
        if potential_os in OS_TO_CATALOG_DIR_MAP:
            logger.debug("Extracted two-part OS from filename", filename=filename, os=potential_os)
            return potential_os

    if len(parts) >= 2:
        # Try single-part OS (iosxe, nxos, iosxr, ise, aci, etc.)
        potential_os = parts[1]
        if potential_os in OS_TO_CATALOG_DIR_MAP:
            logger.debug("Extracted single-part OS from filename", filename=filename, os=potential_os)
            return potential_os

    logger.warning("Could not extract OS from robot filename", filename=filename)
    return None


def find_test_cases_files(test_cases_dir: Path) -> list[Path]:
    """Find all test_cases.yaml files in directory (non-recursive).

    Only searches the immediate directory to avoid picking up backup files
    in subdirectories like .backups/

    Args:
        test_cases_dir: Directory to search for test case files

    Returns:
        List of paths to test_cases.yaml files
    """
    if not test_cases_dir.exists():
        logger.error("Test cases directory does not exist", test_cases_dir=str(test_cases_dir))
        return []

    # Look for .yaml and .yml files in immediate directory only (non-recursive)
    yaml_files = list(test_cases_dir.glob("*.yaml")) + list(test_cases_dir.glob("*.yml"))

    # Filter for files that likely contain test cases
    test_case_files = []
    for yaml_file in yaml_files:
        if "test_case" in yaml_file.name.lower():
            test_case_files.append(yaml_file)

    logger.info("Found test case files", count=len(test_case_files), test_cases_dir=str(test_cases_dir))
    return test_case_files


def load_test_cases_yaml(filepath: Path) -> dict[str, Any] | None:
    """Load test cases YAML preserving formatting.

    Args:
        filepath: Path to test cases YAML file

    Returns:
        Dictionary containing test cases data, or None on error
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            data = yaml.load(f)

        if not isinstance(data, dict):
            logger.error("Test cases file is not a dictionary", filepath=str(filepath))
            return None

        logger.debug("Loaded test cases YAML", filepath=str(filepath), has_test_cases="test_cases" in data)
        return data

    except Exception as e:
        logger.error("Failed to load test cases YAML", filepath=str(filepath), error=str(e))
        return None


def save_test_cases_yaml(filepath: Path, data: dict[str, Any]) -> bool:
    """Save test cases YAML preserving formatting.

    Args:
        filepath: Path to test cases YAML file
        data: Dictionary containing test cases data

    Returns:
        True if save succeeded, False otherwise
    """
    try:
        # CRITICAL: Use atomic write to prevent data loss if yaml.dump() fails
        # Write to temporary file first, then rename atomically
        import os
        import tempfile

        temp_fd, temp_path = tempfile.mkstemp(dir=filepath.parent, prefix=f".{filepath.name}.", suffix=".tmp")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                yaml.dump(data, f)

            # Atomic rename - if this fails, original file is untouched
            os.replace(temp_path, filepath)

            logger.info("Saved test cases YAML", filepath=str(filepath))
            return True

        except Exception as e:
            # Clean up temp file if something went wrong
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            raise e

    except Exception as e:
        logger.error("Failed to save test cases YAML", filepath=str(filepath), error=str(e))
        return False


def find_test_case_by_filename(test_cases: list[dict[str, Any]], generated_script_path: str) -> tuple[int, dict[str, Any]] | None:
    """Find test case by matching generated_script_path field.

    Args:
        test_cases: List of test case dictionaries
        generated_script_path: Generated script path to match

    Returns:
        Tuple of (index, test_case) or None if not found
    """
    for idx, test_case in enumerate(test_cases):
        if test_case.get("generated_script_path") == generated_script_path:
            logger.debug("Found matching test case", index=idx, generated_script_path=generated_script_path)
            return (idx, test_case)

    logger.debug("No matching test case found", generated_script_path=generated_script_path)
    return None


def update_test_case_with_pr_metadata(test_case: dict[str, Any], pr: PullRequest, catalog_repo_url: str) -> dict[str, Any]:
    """Add PR metadata fields to test case.

    Args:
        test_case: Test case dictionary to update
        pr: GitHub PullRequest object
        catalog_repo_url: Full URL to catalog repository

    Returns:
        Updated test case dictionary
    """
    test_case["catalog_pr_git_url"] = catalog_repo_url
    test_case["catalog_pr_number"] = pr.number
    test_case["catalog_pr_url"] = pr.html_url
    test_case["catalog_pr_branch"] = pr.head.ref

    logger.info(
        "Updated test case with PR metadata",
        catalog_pr_number=pr.number,
        catalog_pr_url=pr.html_url,
        catalog_pr_branch=pr.head.ref,
    )

    return test_case


def update_test_case_with_issue_metadata(test_case: dict[str, Any], issue_number: int, issue_url: str) -> dict[str, Any]:
    """Add project issue metadata fields to test case.

    Args:
        test_case: Test case dictionary to update
        issue_number: GitHub Issue number
        issue_url: GitHub Issue URL

    Returns:
        Updated test case dictionary
    """
    test_case["project_issue_number"] = issue_number
    test_case["project_issue_url"] = issue_url

    logger.info(
        "Updated test case with project issue metadata",
        project_issue_number=issue_number,
        project_issue_url=issue_url,
    )

    return test_case


def update_test_case_with_project_pr_metadata(
    test_case: dict[str, Any],
    pr_number: int,
    pr_url: str,
    pr_branch: str,
    repo_url: str,
) -> dict[str, Any]:
    """Add project PR metadata fields to test case.

    Args:
        test_case: Test case dictionary to update
        pr_number: GitHub Pull Request number
        pr_url: GitHub Pull Request URL
        pr_branch: Branch name for the PR
        repo_url: Full URL to the project repository

    Returns:
        Updated test case dictionary
    """
    test_case["project_pr_git_url"] = repo_url
    test_case["project_pr_number"] = pr_number
    test_case["project_pr_url"] = pr_url
    test_case["project_pr_branch"] = pr_branch

    logger.info(
        "Updated test case with project PR metadata",
        project_pr_number=pr_number,
        project_pr_url=pr_url,
        project_pr_branch=pr_branch,
    )

    return test_case


def requires_issue_creation(test_case: dict[str, Any]) -> bool:
    """Check if a test case needs an issue to be created.

    An issue is needed if the test case doesn't already have issue metadata.

    Args:
        test_case: Test case dictionary to check

    Returns:
        True if issue needs to be created, False otherwise
    """
    has_issue_number = test_case.get("project_issue_number") is not None
    has_issue_url = test_case.get("project_issue_url") is not None

    return not (has_issue_number and has_issue_url)


def requires_project_pr_creation(test_case: dict[str, Any]) -> bool:
    """Check if a test case needs a project PR to be created.

    A project PR is needed if:
    - The test case has a generated_script_path (script exists)
    - The test case is NOT catalog-destined
    - The test case doesn't already have project PR metadata

    Args:
        test_case: Test case dictionary to check

    Returns:
        True if project PR needs to be created, False otherwise
    """
    has_script = test_case.get("generated_script_path") is not None
    is_catalog = test_case.get("catalog_destined", False)
    has_pr_number = test_case.get("project_pr_number") is not None
    has_pr_url = test_case.get("project_pr_url") is not None

    return has_script and not is_catalog and not (has_pr_number and has_pr_url)


def requires_catalog_pr_creation(test_case: dict[str, Any]) -> bool:
    """Check if a test case needs a catalog PR to be created.

    A catalog PR is needed if:
    - The test case has a generated_script_path (script exists)
    - The test case IS catalog-destined
    - The test case doesn't already have catalog PR metadata

    Args:
        test_case: Test case dictionary to check

    Returns:
        True if catalog PR needs to be created, False otherwise
    """
    has_script = test_case.get("generated_script_path") is not None
    is_catalog = test_case.get("catalog_destined", False)
    has_pr_number = test_case.get("catalog_pr_number") is not None
    has_pr_url = test_case.get("catalog_pr_url") is not None

    return has_script and is_catalog and not (has_pr_number and has_pr_url)


def load_catalog_destined_test_cases(test_cases_dir: Path) -> list[dict[str, Any]]:
    """Load test cases that are catalog-destined from test_cases.yaml files.

    Args:
        test_cases_dir: Directory containing test_cases.yaml files

    Returns:
        List of test case dictionaries with catalog_destined=true
    """
    catalog_test_cases = []
    test_case_files = find_test_cases_files(test_cases_dir)

    for test_case_file in test_case_files:
        data = load_test_cases_yaml(test_case_file)
        if not data or "test_cases" not in data:
            continue

        test_cases = data["test_cases"]
        if not isinstance(test_cases, list):
            logger.warning("test_cases field is not a list", filepath=str(test_case_file))
            continue

        # Filter for catalog-destined test cases with generated scripts
        for test_case in test_cases:
            is_catalog = test_case.get("catalog_destined", False)
            has_script = test_case.get("generated_script_path")

            if is_catalog and has_script:
                # Add metadata about source file for later writeback
                test_case["_source_file"] = str(test_case_file)
                catalog_test_cases.append(test_case)
                logger.debug(
                    "Found catalog-destined test case",
                    title=test_case.get("title"),
                    script=has_script,
                    source_file=str(test_case_file),
                )

    logger.info("Loaded catalog-destined test cases", count=len(catalog_test_cases), test_cases_dir=str(test_cases_dir))
    return catalog_test_cases


def load_all_test_cases(test_cases_dir: Path) -> list[dict[str, Any]]:
    """Load all test cases from test_cases.yaml files.

    Each test case is annotated with _source_file metadata for writeback.

    Args:
        test_cases_dir: Directory containing test_cases.yaml files

    Returns:
        List of all test case dictionaries
    """
    all_test_cases = []
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
            # Add metadata about source file for later writeback
            test_case["_source_file"] = str(test_case_file)
            all_test_cases.append(test_case)
            logger.debug(
                "Loaded test case",
                title=test_case.get("title"),
                catalog_destined=test_case.get("catalog_destined", False),
                has_script=test_case.get("generated_script_path") is not None,
                source_file=str(test_case_file),
            )

    logger.info("Loaded all test cases", count=len(all_test_cases), test_cases_dir=str(test_cases_dir))
    return all_test_cases


def save_test_case_metadata(test_case: dict[str, Any]) -> bool:
    """Save updated test case metadata back to its source file.

    Uses the _source_file metadata to find and update the correct file.

    Args:
        test_case: Test case dictionary with updated metadata and _source_file

    Returns:
        True if save succeeded, False otherwise
    """
    source_file = test_case.get("_source_file")
    if not source_file:
        logger.error("Test case missing _source_file metadata, cannot save")
        return False

    source_path = Path(source_file)
    title = test_case.get("title")

    # Load the source file
    data = load_test_cases_yaml(source_path)
    if not data or "test_cases" not in data:
        logger.error("Failed to load source file for metadata save", source_file=source_file)
        return False

    # Find and update the matching test case
    test_cases = data["test_cases"]
    if not isinstance(test_cases, list):
        logger.error("test_cases field is not a list", source_file=source_file)
        return False

    found = False
    for tc in test_cases:
        if tc.get("title") == title:
            # Update all metadata fields (excluding internal _source_file)
            for key, value in test_case.items():
                if not key.startswith("_"):
                    tc[key] = value
            found = True
            break

    if not found:
        logger.error("Test case not found in source file", title=title, source_file=source_file)
        return False

    # Save back to file
    if save_test_cases_yaml(source_path, data):
        logger.info("Saved test case metadata", title=title, source_file=source_file)
        return True
    else:
        logger.error("Failed to save test case metadata", title=title, source_file=source_file)
        return False
