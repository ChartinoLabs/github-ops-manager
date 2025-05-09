"""Contains synchronization logic for GitHub issues."""

from githubkit.versions.latest.models import Issue

from github_ops_manager.synchronize.models import SyncDecision


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
