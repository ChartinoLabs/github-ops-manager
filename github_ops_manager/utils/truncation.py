"""Utilities for truncating issue body content to fit within GitHub's character limits."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import structlog

from github_ops_manager.schemas.tac import TestingAsCodeCommand, TestingAsCodeTestCaseDefinition
from github_ops_manager.utils.constants import (
    BASE_TEMPLATE_OVERHEAD,
    DEFAULT_MAX_ISSUE_BODY_LENGTH,
    MIN_OUTPUT_LENGTH,
    TEMPLATE_OVERHEAD_PER_COMMAND,
    TRUNCATION_SUFFIX,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def truncate_string_at_end(
    content: str,
    max_length: int,
    truncation_suffix: str = TRUNCATION_SUFFIX,
) -> tuple[str, bool]:
    """Truncate a string at the end if it exceeds max_length.

    Args:
        content: The string to potentially truncate.
        max_length: Maximum allowed length for the result (including truncation suffix).
        truncation_suffix: Template for truncation indicator with {remaining} placeholder.

    Returns:
        Tuple of (truncated_content, was_truncated).
        If truncation occurs, the result includes the truncation suffix.
    """
    if not content or len(content) <= max_length:
        return content, False

    # Calculate how much space we need for the suffix
    # Use a reasonable estimate for the {remaining} placeholder
    remaining_chars = len(content) - max_length
    suffix = truncation_suffix.format(remaining=remaining_chars)

    # Truncate content to leave room for the suffix
    truncate_at = max_length - len(suffix)
    if truncate_at <= 0:
        # Edge case: max_length is smaller than the suffix itself
        return content[:max_length], True

    truncated = content[:truncate_at] + suffix
    return truncated, True


def estimate_template_overhead(test_case: TestingAsCodeTestCaseDefinition) -> int:
    """Estimate the non-output character overhead from the Jinja2 template.

    This estimates how many characters the template will use for fixed content
    like headers, markdown formatting, pass criteria, and per-command overhead.

    Args:
        test_case: The test case definition to estimate overhead for.

    Returns:
        Estimated character count for template overhead.
    """
    overhead = BASE_TEMPLATE_OVERHEAD

    # Add per-command overhead (markdown code fences, headers, etc.)
    overhead += len(test_case.commands) * TEMPLATE_OVERHEAD_PER_COMMAND

    # Add variable content that isn't truncated
    if test_case.purpose:
        overhead += len(test_case.purpose)
    if test_case.pass_criteria:
        overhead += len(test_case.pass_criteria)
    if test_case.jobfile_parameters:
        overhead += len(test_case.jobfile_parameters)
    if test_case.jobfile_parameters_mapping:
        overhead += len(test_case.jobfile_parameters_mapping)

    return overhead


def calculate_field_sizes(commands: list[TestingAsCodeCommand]) -> list[dict[str, int]]:
    """Calculate the current size of output fields in each command.

    Args:
        commands: List of commands to analyze.

    Returns:
        List of dicts with 'command_output' and 'parsed_output' sizes per command.
    """
    sizes = []
    for cmd in commands:
        sizes.append(
            {
                "command_output": len(cmd.command_output or ""),
                "parsed_output": len(cmd.parsed_output or ""),
            }
        )
    return sizes


def distribute_budget_proportionally(
    field_sizes: list[dict[str, int]],
    available_budget: int,
) -> list[dict[str, int]]:
    """Distribute character budget proportionally across output fields.

    Larger fields get a proportionally larger share of the budget.
    Each field is guaranteed at least MIN_OUTPUT_LENGTH chars if its original
    size was at least that large.

    Args:
        field_sizes: List of dicts with current field sizes per command.
        available_budget: Total character budget for all output fields.

    Returns:
        List of dicts with 'command_output' and 'parsed_output' budgets per command.
    """
    # Calculate total current size
    total_size = sum(sizes["command_output"] + sizes["parsed_output"] for sizes in field_sizes)

    if total_size == 0 or total_size <= available_budget:
        # No truncation needed, return original sizes as budgets
        return field_sizes

    # Distribute proportionally
    budgets = []
    for sizes in field_sizes:
        cmd_budget = {}
        for field in ["command_output", "parsed_output"]:
            field_size = sizes[field]
            if field_size == 0:
                cmd_budget[field] = 0
            else:
                # Proportional allocation
                proportion = field_size / total_size
                allocated = int(available_budget * proportion)
                # Ensure minimum readable content
                cmd_budget[field] = max(allocated, min(field_size, MIN_OUTPUT_LENGTH))
        budgets.append(cmd_budget)

    return budgets


def truncate_test_case_outputs(
    test_case: TestingAsCodeTestCaseDefinition,
    max_body_length: int = DEFAULT_MAX_ISSUE_BODY_LENGTH,
) -> TestingAsCodeTestCaseDefinition:
    """Truncate command outputs in a test case definition to fit within the body limit.

    This is the main entry point for truncation. It returns a new TestingAsCodeTestCaseDefinition
    with potentially truncated command_output and parsed_output fields.

    Args:
        test_case: The original test case definition.
        max_body_length: Maximum target issue body length.

    Returns:
        A new TestingAsCodeTestCaseDefinition with truncated outputs (if needed).
        The original test_case is not modified.
    """
    # Calculate available budget for outputs
    overhead = estimate_template_overhead(test_case)
    available_budget = max_body_length - overhead

    if available_budget <= 0:
        logger.warning(
            "Template overhead exceeds max body length",
            test_case_title=test_case.title,
            overhead=overhead,
            max_body_length=max_body_length,
        )
        available_budget = MIN_OUTPUT_LENGTH * len(test_case.commands) * 2

    # Calculate current field sizes
    field_sizes = calculate_field_sizes(test_case.commands)

    # Check if truncation is needed
    total_current_size = sum(sizes["command_output"] + sizes["parsed_output"] for sizes in field_sizes)
    if total_current_size <= available_budget:
        logger.debug(
            "No truncation needed for test case",
            test_case_title=test_case.title,
            total_output_size=total_current_size,
            available_budget=available_budget,
        )
        return test_case

    # Distribute budget and truncate
    budgets = distribute_budget_proportionally(field_sizes, available_budget)

    # Create a deep copy to avoid mutating the original
    truncated_test_case = deepcopy(test_case)

    for idx, (cmd, budget) in enumerate(zip(truncated_test_case.commands, budgets, strict=True)):
        # Truncate command_output
        if cmd.command_output and len(cmd.command_output) > budget["command_output"]:
            original_len = len(cmd.command_output)
            cmd.command_output, was_truncated = truncate_string_at_end(cmd.command_output, budget["command_output"])
            if was_truncated:
                logger.info(
                    "Truncated command_output",
                    test_case_title=test_case.title,
                    command_index=idx,
                    command=cmd.command,
                    original_length=original_len,
                    truncated_length=len(cmd.command_output),
                    characters_removed=original_len - len(cmd.command_output),
                )

        # Truncate parsed_output
        if cmd.parsed_output and len(cmd.parsed_output) > budget["parsed_output"]:
            original_len = len(cmd.parsed_output)
            cmd.parsed_output, was_truncated = truncate_string_at_end(cmd.parsed_output, budget["parsed_output"])
            if was_truncated:
                logger.info(
                    "Truncated parsed_output",
                    test_case_title=test_case.title,
                    command_index=idx,
                    command=cmd.command,
                    original_length=original_len,
                    truncated_length=len(cmd.parsed_output),
                    characters_removed=original_len - len(cmd.parsed_output),
                )

    return truncated_test_case


def truncate_data_dict_outputs(
    data: dict[str, Any],
    max_body_length: int = DEFAULT_MAX_ISSUE_BODY_LENGTH,
) -> dict[str, Any]:
    """Truncate command outputs within a generic data dictionary.

    This is for use with IssueModel.data which may contain a 'commands' list
    with command_output and parsed_output fields as plain dicts.

    Args:
        data: The data dictionary potentially containing 'commands'.
        max_body_length: Maximum target issue body length.

    Returns:
        A new data dictionary with truncated outputs (if needed).
        The original data is not modified.
    """
    if "commands" not in data:
        return data

    commands = data.get("commands", [])
    if not commands:
        return data

    # Calculate available budget (rough estimate without full test case context)
    overhead = BASE_TEMPLATE_OVERHEAD + len(commands) * TEMPLATE_OVERHEAD_PER_COMMAND

    # Add other fields that contribute to body length
    for field in ["purpose", "pass_criteria", "jobfile_parameters", "jobfile_parameters_mapping"]:
        if field in data and data[field]:
            overhead += len(str(data[field]))

    available_budget = max_body_length - overhead
    if available_budget <= 0:
        available_budget = MIN_OUTPUT_LENGTH * len(commands) * 2

    # Calculate current sizes
    field_sizes = []
    for cmd in commands:
        field_sizes.append(
            {
                "command_output": len(cmd.get("command_output") or ""),
                "parsed_output": len(cmd.get("parsed_output") or ""),
            }
        )

    # Check if truncation is needed
    total_current_size = sum(sizes["command_output"] + sizes["parsed_output"] for sizes in field_sizes)
    if total_current_size <= available_budget:
        return data

    # Distribute budget
    budgets = distribute_budget_proportionally(field_sizes, available_budget)

    # Deep copy and truncate
    truncated_data = deepcopy(data)
    for idx, (cmd, budget) in enumerate(zip(truncated_data["commands"], budgets, strict=True)):
        # Truncate command_output
        cmd_output = cmd.get("command_output")
        if cmd_output and len(cmd_output) > budget["command_output"]:
            cmd["command_output"], _ = truncate_string_at_end(cmd_output, budget["command_output"])
            logger.info(
                "Truncated command_output in data dict",
                command_index=idx,
                original_length=len(cmd_output),
                truncated_length=len(cmd["command_output"]),
            )

        # Truncate parsed_output
        parsed_output = cmd.get("parsed_output")
        if parsed_output and len(parsed_output) > budget["parsed_output"]:
            cmd["parsed_output"], _ = truncate_string_at_end(parsed_output, budget["parsed_output"])
            logger.info(
                "Truncated parsed_output in data dict",
                command_index=idx,
                original_length=len(parsed_output),
                truncated_length=len(cmd["parsed_output"]),
            )

    return truncated_data
