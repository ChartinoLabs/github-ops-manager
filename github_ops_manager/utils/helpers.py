"""General utility functions and helper classes."""

import re


def slugify_title(title: str) -> str:
    """Slugify a title for use in branch names (lowercase, hyphens, alphanum only)."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug


def generate_branch_name(issue_number: int | str, title: str, prefix: str = "feature") -> str:
    """Generate a deterministic branch name like 'feature/123-title-slug'."""
    slug = slugify_title(title)
    return f"{prefix}/{issue_number}-{slug}"
