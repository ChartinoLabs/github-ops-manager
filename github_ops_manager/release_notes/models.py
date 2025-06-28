"""Data models for release notes generation."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Protocol
from pydantic import BaseModel, Field
from enum import Enum
from githubkit.versions.latest.models import Release, PullRequest, Commit
from dataclasses import dataclass

from ..utils.constants import (
    DEFAULT_RELEASE_NOTES_PATH,
    DEFAULT_RELEASE_NOTES_HEADER,
    VERSION_HEADER_PATTERN,
)


class ReleaseNotesStatus(str, Enum):
    """Status of release notes generation."""
    UP_TO_DATE = "up_to_date"
    SUCCESS = "success"
    ERROR = "error"
    DRY_RUN = "dry_run"
    NO_CONTENT = "no_content"
    
    
@dataclass
class ReleaseNotesFileConfig:
    """Configuration for release notes file management."""
    file_path: str = "RELEASE_NOTES.md"
    branch_name_prefix: str = "auto-release-notes"
    commit_message_template: str = "chore: Add release notes for version {version}"
    pr_title_template: str = "chore: Add release notes for version {version}"
    pr_body_template: str = "This PR adds release notes for version {version}.\n\nGenerated automatically."
    
    
class PRWithCommits:
    """Pull request with its associated commits."""
    pull_request: PullRequest
    commits: List[Dict[str, Any]]  # Raw commit data from GitHub API
    
    
class ReleaseNotesResult(BaseModel):
    """Result of release notes generation."""
    status: ReleaseNotesStatus
    pr_url: str | None = None
    version: str | None = None
    error: str | None = None
    generated_content: str | None = None
    
    
class ContentGenerator(Protocol):
    """Protocol for release notes content generators."""
    
    async def generate(
        self, 
        version: str,
        prs: List[PRWithCommits],
        commits: List[Dict[str, Any]],
        release: Release
    ) -> str:
        """Generate release notes content.
        
        Args:
            version: The version being documented
            prs: List of PRs with their commits
            commits: List of standalone commits (raw dicts from GitHub API)
            release: The GitHub release object
            
        Returns:
            Generated release notes content as markdown
        """
        ... 