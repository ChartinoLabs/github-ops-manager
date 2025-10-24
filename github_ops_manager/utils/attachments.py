"""Utilities for handling large content attachments in GitHub issues."""

import structlog

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.utils.constants import TAC_MAX_INLINE_OUTPUT_SIZE

logger = structlog.get_logger(__name__)


async def process_large_content_for_attachment(
    content: str | None,
    filename: str,
    github_adapter: GitHubKitAdapter,
    issue_number: int,
    max_inline_size: int = TAC_MAX_INLINE_OUTPUT_SIZE,
) -> str | None:
    """Process content and upload as attachment if too large.

    Args:
        content: The content to process
        filename: Filename for attachment if uploaded
        github_adapter: GitHub client for uploading
        issue_number: Issue number to attach to
        max_inline_size: Max size (chars) before uploading as attachment

    Returns:
        - If content is None: None
        - If content <= threshold: content (for inline display)
        - If content > threshold: None (uploaded as attachment, omitted from body)
    """
    if content is None:
        return None

    if len(content) <= max_inline_size:
        return content

    logger.info(
        "Content exceeds inline threshold, uploading as attachment",
        filename=filename,
        content_size=len(content),
        threshold=max_inline_size,
        issue_number=issue_number,
    )

    # Upload full content as issue attachment
    try:
        await github_adapter.upload_issue_attachment(
            issue_number=issue_number,
            content=content,
            filename=filename,
        )
    except NotImplementedError:
        logger.warning(
            "Issue attachment upload not yet implemented, falling back to inline content",
            filename=filename,
            issue_number=issue_number,
        )
        # Fallback: return content for inline display
        # This prevents breaking existing functionality while attachment upload is implemented
        return content
    except Exception as exc:
        logger.error(
            "Failed to upload attachment, falling back to inline content",
            filename=filename,
            issue_number=issue_number,
            error=str(exc),
        )
        # Fallback on any error: return content for inline display
        return content

    # Return None to omit from template (attachment visible in GitHub UI)
    return None
