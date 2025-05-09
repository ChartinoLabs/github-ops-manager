"""Contains utility functions for synchronization actions."""

from typing import Any, Sequence

from github_ops_manager.synchronize.models import SyncDecision
from github_ops_manager.synchronize.types import HasName, LabelType


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


def extract_label_names(labels: Sequence[LabelType]) -> set[str]:
    """Extract label names from a list of GitHub label objects, strings, or dicts."""
    names: set[str] = set()
    for label in labels:
        if isinstance(label, str):
            names.add(label)
        elif isinstance(label, dict) and "name" in label:
            names.add(label["name"])
        elif isinstance(label, HasName):
            names.add(label.name)
    return names


async def compare_label_sets(desired_labels: Sequence[str] | None, github_labels: Sequence[LabelType] | None) -> SyncDecision:
    """Compare two sets of labels (desired and GitHub), return NOOP if they match, UPDATE otherwise."""
    if not desired_labels:
        desired_set = set()
    else:
        desired_set = set(desired_labels)
    if not github_labels:
        github_set = set()
    else:
        github_set = extract_label_names(github_labels)
    if desired_set == github_set:
        return SyncDecision.NOOP
    return SyncDecision.UPDATE
