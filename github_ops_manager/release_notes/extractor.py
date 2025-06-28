"""Extract PR and commit data from releases."""

import re
from typing import List, Tuple, Optional, Dict, Any
import structlog
from githubkit.versions.latest.models import Release, PullRequest

from ..github.adapter import GitHubKitAdapter
from .models import PRWithCommits
from ..utils.constants import PR_REFERENCE_PATTERN, COMMIT_SHA_PATTERN


logger = structlog.get_logger(__name__)


class DataExtractor:
    """Extracts PR and commit data from releases."""
    
    def __init__(self, adapter: GitHubKitAdapter):
        """Initialize with GitHub adapter."""
        self.adapter = adapter
        
    async def extract_release_data(self, specific_release: Optional[str] = None) -> Release:
        """Extract data from a release.
        
        Args:
            specific_release: Optional specific release to fetch. If None, gets latest.
            
        Returns:
            GitHub Release object from the API
        """
        if specific_release:
            release = await self.adapter.get_release(f"v{specific_release}")
        else:
            release = await self.adapter.get_latest_release()
        
        return release
        
    async def extract_pr_data(self, release_body: str) -> List[PRWithCommits]:
        """Extract PR data from release body.
        
        IMPORTANT: This method fetches full commit messages including extended bodies.
        The commit.message field will contain the complete message with any description
        after the summary line.
        
        Args:
            release_body: The body text of the release containing PR references
            
        Returns:
            List of PRWithCommits objects containing PR and commit data
        """
        pr_data = []
        
        # Find all PR references
        pr_matches = PR_REFERENCE_PATTERN.findall(release_body)
        
        logger.debug(f"Found {len(pr_matches)} PR references in release body")
        logger.debug(f"PR matches: {pr_matches}")
        
        for match in pr_matches:
            pr_number = match[0] or match[1]
            if not pr_number:
                continue
                
            logger.debug(f"Processing PR #{pr_number}")
                
            try:
                # Fetch PR details
                pr = await self.adapter.get_pull_request(int(pr_number))
                
                # Fetch commits for this PR using githubkit's async_list_commits
                commits_response = await self.adapter.client.rest.pulls.async_list_commits(
                    owner=self.adapter.owner,
                    repo=self.adapter.repo_name,
                    pull_number=int(pr_number)
                )
                commits = commits_response.parsed_data
                
                # Fetch detailed commit info INCLUDING FULL MESSAGE BODY
                detailed_commits = []
                for commit in commits:
                    try:
                        detailed = await self.adapter.get_commit(commit.sha)
                        detailed_commits.append(detailed)
                    except Exception as e:
                        logger.warning(
                            "Failed to fetch commit details",
                            sha=commit.sha,
                            error=str(e)
                        )
                        
                if detailed_commits:
                    pr_data.append(PRWithCommits(
                        pull_request=pr,
                        commits=detailed_commits
                    ))
                  
            except Exception as e:
                logger.error("Failed to fetch PR data", pr_number=pr_number, error=str(e))
                
        return pr_data

    def extract_commit_shas(self, release_body: str) -> List[str]:
        """Extract commit SHA references from release body.
        
        Args:
            release_body: The release body text
            
        Returns:
            List of unique commit SHAs found in the body
        """
        # Find all potential commit SHAs
        sha_matches = COMMIT_SHA_PATTERN.findall(release_body)
        
        # Filter out common false positives (e.g., version numbers that look like SHAs)
        valid_shas = []
        for sha in sha_matches:
            # Minimum 7 chars for short SHA
            if len(sha) >= 7:
                # Additional validation: check if it's not a common false positive
                # (e.g., all numeric, part of a version string)
                if not sha.isdigit() and not re.match(r'^\d+\.\d+', sha):
                    valid_shas.append(sha)
                    
        # Remove duplicates while preserving order
        seen = set()
        unique_shas = []
        for sha in valid_shas:
            if sha not in seen:
                seen.add(sha)
                unique_shas.append(sha)
                
        logger.debug(f"Found {len(unique_shas)} commit SHAs in release body")
        return unique_shas
    
    async def extract_commit_data_from_shas(self, shas: List[str]) -> List[Dict[str, Any]]:
        """Fetch full commit data for a list of SHAs.
        
        Args:
            shas: List of commit SHAs (short or full)
            
        Returns:
            List of commit dictionaries with full commit messages
        """
        commit_data = []
        
        for sha in shas:
            try:
                # Fetch full commit details including complete message body
                detailed = await self.adapter.get_commit(sha)
                commit_data.append(detailed)
                
                logger.debug(
                    "Fetched commit details",
                    sha=sha,
                    author=detailed.get('commit', {}).get('author', {}).get('name', 'Unknown'),
                    message_lines=len(detailed.get('commit', {}).get('message', '').split('\n'))
                )
                
            except Exception as e:
                logger.warning(
                    "Failed to fetch commit details",
                    sha=sha,
                    error=str(e)
                )
                
        return commit_data
    
    async def extract_pr_and_commit_data(self, release_body: str) -> Tuple[List[PRWithCommits], List[Dict[str, Any]]]:
        """Extract both PR data and standalone commit data from release body.
        
        This method will:
        1. First try to extract PR data (existing behavior)
        2. Also extract any commit SHAs mentioned in the release body
        3. Return both PR data and standalone commit data
        
        Args:
            release_body: The release body text
            
        Returns:
            Tuple of (PR data list, standalone commit data list)
        """
        # Extract PR data (existing logic)
        pr_data = await self.extract_pr_data(release_body)
        
        # Extract commit SHAs from release body
        commit_shas = self.extract_commit_shas(release_body)
        
        # Get commits that are already part of PRs
        pr_commit_shas = set()
        for pr in pr_data:
            for commit in pr.commits:
                # Handle both dict and object formats
                sha = commit.get('sha') if isinstance(commit, dict) else commit.sha
                pr_commit_shas.add(sha[:7])  # Use short SHA for comparison
                pr_commit_shas.add(sha)      # Also add full SHA
                
        # Filter out commits that are already part of PRs
        standalone_shas = [
            sha for sha in commit_shas 
            if sha not in pr_commit_shas and not any(
                existing_sha.startswith(sha) or sha.startswith(existing_sha)
                for existing_sha in pr_commit_shas
            )
        ]
        
        logger.info(
            "Extracted PR and commit references",
            pr_count=len(pr_data),
            total_commit_shas=len(commit_shas),
            standalone_commit_shas=len(standalone_shas)
        )
        
        # Fetch full data for standalone commits
        standalone_commits = await self.extract_commit_data_from_shas(standalone_shas)
        
        return pr_data, standalone_commits 