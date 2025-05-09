"""Contains synchronization logic for GitHub labels."""

import structlog
from githubkit.versions.latest.models import Label

from github_ops_manager.schemas.default_issue import LabelModel
from github_ops_manager.synchronize.models import SyncDecision

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def decide_github_label_sync_action(desired_label: LabelModel, github_label: Label | None = None) -> SyncDecision:
    """Compare a YAML label and a GitHub label, and decide whether to create, update, or no-op.

    Key is label name.
    """
    # For now, we'll only make decisions based on the label name
    if github_label is None:
        logger.info("Label not found in GitHub", label_name=desired_label.name)
        return SyncDecision.CREATE

    if github_label.name != desired_label.name:
        logger.info("Label needs to be updated", current_label_name=github_label.name, new_label_name=desired_label.name)
        return SyncDecision.UPDATE

    logger.info("Label is up to date", label_name=desired_label.name)
    return SyncDecision.NOOP
