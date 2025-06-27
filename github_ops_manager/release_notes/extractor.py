"""Extract PR and commit data from releases."""

import re
from typing import List, Tuple, Optional
import structlog
from githubkit.versions.latest.models import Release, PullRequest, Commit

from ..github.adapter import GitHubKitAdapter
from .models import PRWithCommits


logger = structlog.get_logger(__name__)


class DataExtractor:
    """Extracts PR and commit data from releases."""
    
    # Pattern to match PR references in release body
    PR_PATTERN = re.compile(
        r'https://[^/]+/[^/]+/[^/]+/pull/(\d+)|#(\d+)'
    )
    
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
        pr_matches = self.PR_PATTERN.findall(release_body)
        
        for match in pr_matches:
            pr_number = match[0] or match[1]
            if not pr_number:
                continue
                
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