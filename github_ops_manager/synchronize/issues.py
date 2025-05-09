"""Contains synchronization logic for GitHub issues."""

from typing import Any

from githubkit.versions.latest.models import Issue

from github_ops_manager.synchronize.models import SyncDecision
from github_ops_manager.synchronize.utils import value_is_noney


async def decide_github_issue_label_sync_action(desired_label: str, github_issue: Issue) -> SyncDecision:
    """Compare a YAML label and a GitHub issue, and decide whether to create, update, or no-op.

    Key is label name.
    """
    for github_label in github_issue.labels:
        if isinstance(github_label, str):
            if github_label == desired_label:
                return SyncDecision.NOOP
        else:
            if github_label.name == desired_label:
                return SyncDecision.NOOP
    return SyncDecision.UPDATE


async def compare_github_issue_field(desired_value: Any, github_value: Any) -> SyncDecision:
    """Compare a YAML field and a GitHub field, and decide whether to create, update, or no-op.

    Key is field name.
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
