"""Markdown manipulation for release notes."""

import structlog

logger = structlog.get_logger(__name__)


class MarkdownWriter:
    """Handles markdown manipulation for release notes."""

    def __init__(self, expected_header: str) -> None:
        """Initialize with expected header."""
        self.expected_header = expected_header.strip()

    def validate_structure(self, content: str) -> bool:
        """Validate that the markdown has expected structure."""
        if self.expected_header not in content:
            logger.error("Missing expected header")
            return False
        return True

    def insert_release_notes(self, existing_content: str, new_content: str, version: str) -> str:
        """Insert new release notes after the document header."""
        # Ensure proper formatting
        if not new_content.strip().startswith(f"## v{version}"):
            logger.warning("Release notes don't start with expected version header", expected=f"## v{version}")

        # Find position after header
        header_end = existing_content.find(self.expected_header)
        if header_end == -1:
            raise ValueError("Release notes file missing expected header")

        header_end += len(self.expected_header)

        # Insert new content
        updated = existing_content[:header_end] + "\n\n" + new_content.strip() + "\n" + existing_content[header_end:]

        logger.info("Inserted new release notes", version=version)
        return updated
