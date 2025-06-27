"""Data models for release notes generation."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Protocol
from pydantic import BaseModel, Field
from enum import Enum
from githubkit.versions.latest.models import Release, PullRequest, Commit


class ReleaseNotesStatus(str, Enum):
    """Status of release notes generation."""
    UP_TO_DATE = "up_to_date"
    SUCCESS = "success"
    ERROR = "error"
    DRY_RUN = "dry_run"
    NO_PRS = "no_prs"
    
    
class ReleaseNotesFileConfig(BaseModel):
    """Configuration specific to release notes file handling."""
    
    # File settings
    release_notes_path: str = Field(
        default="docs/release-notes.md",
        description="Path to release notes file in repo"
    )
    release_notes_header: str = Field(
        default="# Release Notes\n\nThis document tracks the new features, enhancements, and bug fixes for each release.",
        description="Expected header in release notes file"
    )
    
    # Behavior settings
    version_pattern: str = Field(
        default=r'^##\s+v?(\d+\.\d+\.\d+)\s*$',
        description="Regex pattern to match version headers"
    )
    
    
class PRWithCommits(BaseModel):
    """Wrapper for a pull request with its associated commits.
    
    This combines the GitHub API PullRequest object with the list of commits
    for easier processing by the content generator.
    """
    pull_request: PullRequest
    commits: List[Commit]
    
    
class ReleaseNotesResult(BaseModel):
    """Result of release notes generation."""
    status: ReleaseNotesStatus
    pr_url: str | None = None
    version: str | None = None
    error: str | None = None
    generated_content: str | None = None
    
    
class ContentGenerator(Protocol):
    """Protocol for pluggable content generation.
    
    Implementations can use AI, templates, or any other method
    to generate release notes content from the provided data.
    """
    
    async def generate_content(
        self,
        release: Release,
        pr_data: List[PRWithCommits],
        current_content: str,
        file_config: ReleaseNotesFileConfig
    ) -> str:
        """Generate release notes content.
        
        Args:
            release: GitHub Release object from the API
            pr_data: List of PRs with their commits
            current_content: Current release notes file content
            file_config: Configuration for file handling
            
        Returns:
            Generated markdown content for the new release
        """
        ... 