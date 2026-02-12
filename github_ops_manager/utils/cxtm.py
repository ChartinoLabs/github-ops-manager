"""Utility functions for parsing and working with cxtm.yaml files.

The cxtm.yaml file is the authoritative source for test case definitions
used by tac-tools. This module provides functions to extract test case
metadata that can be embedded into GitHub issues for traceability.
"""

import logging
import re
from pathlib import Path

from github_ops_manager.schemas.tac import (
    CXTMConfiguration,
    CXTMTestCase,
    CXTMTestCaseGroup,
)
from github_ops_manager.utils.yaml import load_yaml_file

logger = logging.getLogger(__name__)


def load_cxtm_configuration(cxtm_file_path: Path) -> CXTMConfiguration:
    """Load and parse a cxtm.yaml configuration file.

    Args:
        cxtm_file_path: Path to the cxtm.yaml file.

    Returns:
        CXTMConfiguration object with parsed data.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValidationError: If the file has invalid structure.
    """
    if not cxtm_file_path.exists():
        raise FileNotFoundError(f"cxtm.yaml not found: {cxtm_file_path.absolute()}")

    yaml_content = load_yaml_file(cxtm_file_path)
    return CXTMConfiguration.model_validate(yaml_content)


def find_test_case_by_title(
    cxtm_config: CXTMConfiguration,
    title: str,
    fuzzy_match: bool = True,
) -> tuple[CXTMTestCaseGroup | None, CXTMTestCase | None]:
    """Find a test case in cxtm.yaml by its title.

    Searches through all test case groups to find a test case matching
    the given title. Supports both exact and fuzzy matching.

    Args:
        cxtm_config: Parsed cxtm.yaml configuration.
        title: Title to search for (e.g., "[NX-OS] Verify Module Serial Number").
        fuzzy_match: If True, performs case-insensitive partial matching.

    Returns:
        Tuple of (test_case_group, test_case) if found, (None, None) otherwise.
    """
    # Normalize title for comparison
    normalized_title = title.strip().lower() if fuzzy_match else title.strip()

    for group in cxtm_config.test_case_groups:
        # Check group name
        group_name = group.name.strip().lower() if fuzzy_match else group.name.strip()

        if fuzzy_match:
            # Check if title matches group name or is contained within it
            if normalized_title in group_name or group_name in normalized_title:
                if group.test_cases:
                    return group, group.test_cases[0]
        else:
            if group_name == normalized_title:
                if group.test_cases:
                    return group, group.test_cases[0]

        # Also check individual test case titles within the group
        for test_case in group.test_cases:
            tc_title = test_case.title.strip().lower() if fuzzy_match else test_case.title.strip()
            if fuzzy_match:
                if normalized_title in tc_title or tc_title in normalized_title:
                    return group, test_case
            else:
                if tc_title == normalized_title:
                    return group, test_case

    return None, None


def find_test_case_by_robot_file(
    cxtm_config: CXTMConfiguration,
    robot_file_path: str,
) -> tuple[CXTMTestCaseGroup | None, CXTMTestCase | None]:
    """Find a test case in cxtm.yaml by its robot file path.

    Args:
        cxtm_config: Parsed cxtm.yaml configuration.
        robot_file_path: Path to the robot file (can be partial path).

    Returns:
        Tuple of (test_case_group, test_case) if found, (None, None) otherwise.
    """
    # Normalize path for comparison
    normalized_path = robot_file_path.strip().lower()

    for group in cxtm_config.test_case_groups:
        for test_case in group.test_cases:
            if test_case.robot_file:
                tc_robot_file = test_case.robot_file.strip().lower()
                # Check for exact match or if one contains the other
                if normalized_path in tc_robot_file or tc_robot_file in normalized_path:
                    return group, test_case

    return None, None


def extract_test_name_from_title(title: str) -> str:
    """Extract the test name from a title in format '[OS] Test Name'.

    Args:
        title: Full title string (e.g., "[NX-OS] Verify Module Serial Number").

    Returns:
        The test name portion (e.g., "Verify Module Serial Number").
    """
    pattern = re.compile(r"^\[(?P<os>[^\]]+)\]\s+(?P<test_name>.+)$")
    match = pattern.match(title.strip())
    if match:
        return match.group("test_name")
    return title.strip()


def format_test_case_yaml_block(
    group: CXTMTestCaseGroup,
    test_case: CXTMTestCase,
) -> str:
    """Format a test case definition as a YAML block for embedding in issues.

    Creates a structured YAML representation of the test case that can be
    parsed by the webhook receiver to extract test case metadata.

    Args:
        group: The test case group containing the test case.
        test_case: The test case to format.

    Returns:
        Formatted YAML string ready for embedding in an issue body.
    """
    lines = [
        "test_case_group:",
        f'  name: "{group.name}"',
        "test_case:",
        f'  identifier: "{test_case.identifier}"',
        f'  title: "{test_case.title}"',
    ]

    if test_case.robot_file:
        lines.append(f'  robot_file: "{test_case.robot_file}"')

    if test_case.git_url:
        lines.append(f'  git_url: "{test_case.git_url}"')

    if test_case.git_commit_sha:
        lines.append(f'  git_commit_sha: "{test_case.git_commit_sha}"')

    return "\n".join(lines)
