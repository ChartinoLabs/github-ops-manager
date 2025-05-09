"""Contains utility functions for synchronization actions."""

from typing import Any

from github_ops_manager.synchronize.models import SyncDecision


async def value_is_noney(value: Any) -> bool:
    """Check if a value is None, an empty list, an empty string, or an empty dict."""
    if value is None:
        return True
    elif isinstance(value, list) and value == []:
        return True
    elif isinstance(value, str) and value == "":
        return True
    elif isinstance(value, dict) and not value:
        return True
    return False


async def compare_github_field(desired_value: Any, github_value: Any) -> SyncDecision:
    """Compare a YAML field and a GitHub field, and decide whether to create, update, or no-op.

    Used for both issues and pull requests. Key is field name.
    """
    desired_value_is_noney = await value_is_noney(desired_value)
    github_value_is_noney = await value_is_noney(github_value)
    if desired_value_is_noney and github_value_is_noney:
        return SyncDecision.NOOP
    elif desired_value_is_noney:
        return SyncDecision.CREATE
    elif github_value_is_noney:
        return SyncDecision.UPDATE
    elif desired_value == github_value:
        return SyncDecision.NOOP
    else:
        return SyncDecision.UPDATE
