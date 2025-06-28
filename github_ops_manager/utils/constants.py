"""Shared constants used across the application."""

# This file is intended to hold shared constants.

import re

# Release Notes Constants
# -----------------------

# Regex Patterns
PR_REFERENCE_PATTERN = re.compile(
    r'https://[^/]+/[^/]+/[^/]+/pull/(\d+)|#(\d+)'
)
"""Pattern to match PR references in release body (GitHub URLs or #123 format)."""

COMMIT_SHA_PATTERN = re.compile(
    r'\b([0-9a-fA-F]{7,40})\b'
)
"""Pattern to match commit SHAs (7-40 character hex strings)."""

VERSION_HEADER_PATTERN = r'^##\s+v?(\d+\.\d+\.\d+)\s*$'
"""Regex pattern to match version headers in markdown (e.g., ## v1.2.3)."""

# Default File Settings
DEFAULT_RELEASE_NOTES_PATH = "docs/release-notes.md"
"""Default path to release notes file in repository."""

DEFAULT_RELEASE_NOTES_HEADER = (
    "# Release Notes\n\n"
    "This document tracks the new features, enhancements, and bug fixes for each release."
)
"""Default header expected in release notes file."""
