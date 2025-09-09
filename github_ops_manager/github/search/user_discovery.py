"""User repository discovery using GitHub Search API."""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import structlog
from githubkit import GitHub
from githubkit.exception import RequestFailed

from github_ops_manager.utils.retry import retry_on_rate_limit

logger = structlog.get_logger(__name__)


class SearchRateLimiter:
    """Handle Search API's stricter rate limits (30 requests per minute)."""
    
    def __init__(self, max_per_minute: int = 30):
        """Initialize the rate limiter.
        
        Args:
            max_per_minute: Maximum requests per minute (default: 30 for search API)
        """
        self.max_per_minute = max_per_minute
        self.request_times: List[float] = []
    
    async def wait_if_needed(self) -> None:
        """Wait if we're hitting rate limits."""
        now = time.time()
        # Remove requests older than 1 minute
        self.request_times = [t for t in self.request_times if now - t < 60]
        
        if len(self.request_times) >= self.max_per_minute:
            # Wait until oldest request is > 1 minute old
            wait_time = 60 - (now - self.request_times[0]) + 1
            logger.info(
                "Search API rate limit reached, waiting",
                wait_seconds=wait_time,
                current_requests=len(self.request_times)
            )
            await asyncio.sleep(wait_time)
        
        self.request_times.append(now)


class UserRepositoryDiscoverer:
    """Discover repositories from user activity using Search API."""
    
    def __init__(self, github_client: GitHub):
        """Initialize the discoverer.
        
        Args:
            github_client: Authenticated GitHub client
        """
        self.client = github_client
        self.rate_limiter = SearchRateLimiter()
    
    async def discover_user_repositories(
        self,
        username: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Set[str]:
        """Discover ALL repositories where user has activity.
        
        Uses Search API to find:
        1. All PRs authored by user
        2. All issues created by user  
        3. All PRs reviewed by user
        4. Commits (if searchable)
        
        Args:
            username: GitHub username to search for
            start_date: Start date for search range
            end_date: End date for search range
            
        Returns:
            Set of repository full names (owner/repo format)
        """
        repositories = set()
        
        logger.info(
            "Starting repository discovery for user",
            username=username,
            start_date=start_date.date().isoformat(),
            end_date=end_date.date().isoformat()
        )
        
        # 1. Search for PRs authored by user
        pr_repos = await self._discover_from_authored_prs(username, start_date, end_date)
        repositories.update(pr_repos)
        logger.debug(f"Found {len(pr_repos)} repos from authored PRs", username=username, count=len(pr_repos))
        
        # 2. Search for PRs reviewed by user
        review_repos = await self._discover_from_reviewed_prs(username, start_date, end_date)
        repositories.update(review_repos)
        logger.debug(f"Found {len(review_repos)} repos from reviewed PRs", username=username, count=len(review_repos))
        
        # 3. Search for issues (including CXTM)
        issue_repos = await self._discover_from_issues(username, start_date, end_date)
        repositories.update(issue_repos)
        logger.debug(f"Found {len(issue_repos)} repos from issues", username=username, count=len(issue_repos))
        
        # 4. Search for commits (if API allows)
        try:
            commit_repos = await self._discover_from_commits(username, start_date, end_date)
            repositories.update(commit_repos)
            logger.debug(f"Found {len(commit_repos)} repos from commits", username=username, count=len(commit_repos))
        except Exception as e:
            # Commit search might not be available or might fail
            logger.warning(
                "Could not search commits for user",
                username=username,
                error=str(e)
            )
        
        logger.info(
            "Repository discovery complete for user",
            username=username,
            total_repos=len(repositories),
            date_range=f"{start_date.date()} to {end_date.date()}"
        )
        
        return repositories
    
    async def _discover_from_authored_prs(
        self,
        username: str,
        start_date: datetime,
        end_date: datetime
    ) -> Set[str]:
        """Discover repositories from PRs authored by the user."""
        query = f"author:{username} type:pr created:{start_date.date()}..{end_date.date()}"
        results = await self._search_issues(query)
        
        repos = set()
        for item in results:
            repo_name = self._extract_repo_from_url(item.get('repository_url', ''))
            if repo_name:
                repos.add(repo_name)
        
        return repos
    
    async def _discover_from_reviewed_prs(
        self,
        username: str,
        start_date: datetime,
        end_date: datetime
    ) -> Set[str]:
        """Discover repositories from PRs reviewed by the user."""
        query = f"reviewed-by:{username} type:pr created:{start_date.date()}..{end_date.date()}"
        results = await self._search_issues(query)
        
        repos = set()
        for item in results:
            repo_name = self._extract_repo_from_url(item.get('repository_url', ''))
            if repo_name:
                repos.add(repo_name)
        
        return repos
    
    async def _discover_from_issues(
        self,
        username: str,
        start_date: datetime,
        end_date: datetime
    ) -> Set[str]:
        """Discover repositories from issues created by the user."""
        query = f"author:{username} type:issue created:{start_date.date()}..{end_date.date()}"
        results = await self._search_issues(query)
        
        repos = set()
        for item in results:
            repo_name = self._extract_repo_from_url(item.get('repository_url', ''))
            if repo_name:
                repos.add(repo_name)
        
        return repos
    
    async def _discover_from_commits(
        self,
        username: str,
        start_date: datetime,
        end_date: datetime
    ) -> Set[str]:
        """Discover repositories from commits by the user."""
        query = f"author:{username} committer-date:{start_date.date()}..{end_date.date()}"
        results = await self._search_commits(query)
        
        repos = set()
        for item in results:
            if 'repository' in item and 'full_name' in item['repository']:
                repos.add(item['repository']['full_name'])
        
        return repos
    
    @retry_on_rate_limit
    async def _search_issues(self, query: str, per_page: int = 100) -> List[Dict[str, Any]]:
        """Search issues/PRs using GitHub Search API.
        
        Handles pagination automatically.
        
        Args:
            query: Search query string
            per_page: Results per page (max 100)
            
        Returns:
            List of search results
        """
        await self.rate_limiter.wait_if_needed()
        
        all_results = []
        page = 1
        
        while True:
            try:
                response = await self.client.rest.search.issues_and_pull_requests(
                    q=query,
                    per_page=per_page,
                    page=page,
                    sort="created",
                    order="desc"
                )
                
                items = response.parsed_data.items if hasattr(response.parsed_data, 'items') else []
                
                # Convert items to dict for easier processing
                for item in items:
                    all_results.append(item.model_dump() if hasattr(item, 'model_dump') else item)
                
                # Check if more pages exist
                if len(items) < per_page:
                    break
                    
                page += 1
                
                # Don't fetch too many pages (safety limit)
                if page > 10:
                    logger.warning(
                        "Reached page limit for search",
                        query=query,
                        pages_fetched=page-1,
                        results_count=len(all_results)
                    )
                    break
                    
            except RequestFailed as e:
                if e.response.status_code == 403:
                    # Rate limit hit - retry decorator should handle this
                    raise
                elif e.response.status_code == 422:
                    # Invalid query
                    logger.error(
                        "Invalid search query",
                        query=query,
                        error=str(e)
                    )
                    break
                else:
                    logger.error(
                        "Search API error",
                        query=query,
                        status_code=e.response.status_code,
                        error=str(e)
                    )
                    break
            except Exception as e:
                logger.error(
                    "Unexpected error during search",
                    query=query,
                    error=str(e)
                )
                break
        
        return all_results
    
    @retry_on_rate_limit
    async def _search_commits(self, query: str, per_page: int = 100) -> List[Dict[str, Any]]:
        """Search commits using GitHub Search API.
        
        Args:
            query: Search query string
            per_page: Results per page (max 100)
            
        Returns:
            List of commit search results
        """
        await self.rate_limiter.wait_if_needed()
        
        try:
            response = await self.client.rest.search.commits(
                q=query,
                per_page=per_page,
                sort="committer-date",
                order="desc"
            )
            
            items = response.parsed_data.items if hasattr(response.parsed_data, 'items') else []
            
            # Convert to dict
            results = []
            for item in items:
                results.append(item.model_dump() if hasattr(item, 'model_dump') else item)
            
            return results
            
        except RequestFailed as e:
            if e.response.status_code == 422:
                # Commit search might not be available
                logger.warning(
                    "Commit search not available or invalid query",
                    query=query,
                    error=str(e)
                )
                return []
            raise
        except Exception as e:
            logger.error(
                "Error searching commits",
                query=query,
                error=str(e)
            )
            return []
    
    def _extract_repo_from_url(self, url: str) -> Optional[str]:
        """Extract owner/repo from repository URL.
        
        Example: 
        https://api.github.com/repos/cisco/repo -> cisco/repo
        
        Args:
            url: Repository API URL
            
        Returns:
            Repository name in owner/repo format or None
        """
        if not url:
            return None
            
        try:
            # URL format: https://api.github.com/repos/OWNER/REPO
            parts = url.split('/')
            if 'repos' in parts:
                idx = parts.index('repos')
                if len(parts) > idx + 2:
                    owner = parts[idx + 1]
                    repo = parts[idx + 2]
                    return f"{owner}/{repo}"
        except Exception as e:
            logger.warning(
                "Could not extract repo from URL",
                url=url,
                error=str(e)
            )
        
        return None
