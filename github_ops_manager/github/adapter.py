"""GitHub client adapter for the githubkit library."""

import base64
from functools import wraps
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, Self, TypeVar

import structlog
from githubkit import Response
from githubkit.exception import RequestFailed
from githubkit.versions.latest.models import (
    FullRepository,
    Issue,
    Label,
    PullRequest,
    PullRequestSimple,
    Release,
)

from github_ops_manager.configuration.models import GitHubAuthenticationType
from github_ops_manager.utils.github import split_repository_in_configuration
from github_ops_manager.utils.retry import retry_on_rate_limit

from .abc import GitHubClientBase
from .client import GitHubClient, get_github_client

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def handle_github_422(func: F) -> F:
    """Decorator to handle GitHub 422 Unprocessable Entity errors, logging and raising with details."""

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except RequestFailed as exc:
            if exc.response.status_code == 422:
                try:
                    error_data = exc.response.json()
                except Exception:
                    error_data = {}
                message = error_data.get("message", "Unprocessable Entity")
                errors = error_data.get("errors", [])
                logger.error(
                    "GitHub 422 Unprocessable Entity",
                    function=func.__name__,
                    message=message,
                    errors=errors,
                    url=getattr(exc.response, "url", None),
                    status_code=422,
                )
                raise ValueError(
                    f"GitHub 422 error in {func.__name__}: {message} | errors: {errors} | url: {getattr(exc.response, 'url', None)}"
                ) from exc
            raise

    return wrapper  # type: ignore


class GitHubKitAdapter(GitHubClientBase):
    """GitHub client adapter for the githubkit library."""

    def __init__(self, client: GitHubClient, owner: str, repo_name: str) -> None:
        """Initialize the GitHub client adapter with an already-initialized client."""
        self.client = client
        self.owner = owner
        self.repo_name = repo_name

    def _omit_null_parameters(self, **kwargs: Any) -> dict[str, Any]:
        """Omit parameters that are None."""
        return {k: v for k, v in kwargs.items() if v is not None}

    @classmethod
    async def create(
        cls,
        repo: str,
        github_auth_type: GitHubAuthenticationType,
        github_pat_token: str | None = None,
        github_app_id: int | None = None,
        github_app_private_key_path: Path | None = None,
        github_app_installation_id: int | None = None,
        github_api_url: str = "https://api.github.com",
    ) -> Self:
        """Create a new GitHub client adapter.

        Args:
            repo: Repository in 'owner/repo' format
            github_auth_type: Type of authentication (PAT or APP)
            github_pat_token: Personal access token (required for PAT auth)
            github_app_id: GitHub App ID (required for APP auth)
            github_app_private_key_path: Path to private key file (required for APP auth)
            github_app_installation_id: Installation ID (required for APP auth)
            github_api_url: GitHub API URL (defaults to https://api.github.com)

        Returns:
            Configured GitHubKitAdapter instance

        Raises:
            ValueError: If required parameters for the chosen auth type are missing
        """
        owner, repo_name = await split_repository_in_configuration(repo=repo)
        logger.info(
            "Creating client for GitHub instance and repository",
            github_api_url=github_api_url,
            owner=owner,
            repo_name=repo_name,
        )
        client = await get_github_client(
            repo=repo,
            github_auth_type=github_auth_type,
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
            github_api_url=github_api_url,
        )
        return cls(client, owner, repo_name)

    # Repository CRUD
    @retry_on_rate_limit()
    async def get_repository(self) -> FullRepository:
        """Get the repository for the current client."""
        response: Response[FullRepository] = await self.client.rest.repos.async_get(owner=self.owner, repo=self.repo_name)
        return response.parsed_data

    # Issue CRUD
    @handle_github_422
    @retry_on_rate_limit()
    async def create_issue(
        self,
        title: str,
        body: str | None = None,
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
        milestone: str | int | None = None,
        **kwargs: Any,
    ) -> Issue:
        """Create an issue for a repository."""
        params = self._omit_null_parameters(
            title=title,
            body=body,
            assignees=assignees,
            labels=labels,  # type: ignore
            milestone=milestone,
            **kwargs,
        )
        response: Response[Issue] = await self.client.rest.issues.async_create(
            owner=self.owner,
            repo=self.repo_name,
            **params,
        )
        return response.parsed_data

    @handle_github_422
    @retry_on_rate_limit()
    async def update_issue(
        self,
        issue_number: int,
        title: str | None = None,
        body: str | None = None,
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
        milestone: str | int | None = None,
        state: Literal["open", "closed"] | None = None,
        **kwargs: Any,
    ) -> Issue:
        """Update an issue for a repository."""
        params = self._omit_null_parameters(
            title=title,
            body=body,
            assignees=assignees,
            labels=labels,  # type: ignore
            milestone=milestone,
            state=state,
            **kwargs,
        )
        response: Response[Issue] = await self.client.rest.issues.async_update(
            owner=self.owner,
            repo=self.repo_name,
            issue_number=issue_number,
            **params,
        )
        return response.parsed_data

    @retry_on_rate_limit()
    async def list_issues(self, state: Literal["open", "closed", "all"] = "all", per_page: int = 100, **kwargs: Any) -> list[Issue]:
        """List all issues for a repository, handling pagination."""
        all_issues: list[Issue] = []
        page: int = 1
        while True:
            response: Response[list[Issue]] = await self.client.rest.issues.async_list_for_repo(
                owner=self.owner,
                repo=self.repo_name,
                state=state,
                per_page=per_page,
                page=page,
                **kwargs,
            )
            issues: list[Issue] = response.parsed_data
            if not issues:
                break
            all_issues.extend(issues)
            if len(issues) < per_page:
                break
            page += 1
        return all_issues

    @handle_github_422
    @retry_on_rate_limit()
    async def close_issue(self, issue_number: int, **kwargs: Any) -> Issue:
        """Close an issue for a repository."""
        response: Response[Issue] = await self.client.rest.issues.async_update(
            owner=self.owner,
            repo=self.repo_name,
            issue_number=issue_number,
            state="closed",
            **kwargs,
        )
        return response.parsed_data

    # Label CRUD
    @handle_github_422
    @retry_on_rate_limit()
    async def create_label(self, name: str, color: str, description: str | None = None, **kwargs: Any) -> Label:
        """Create a label for a repository."""
        params = self._omit_null_parameters(
            name=name,
            color=color,
            description=description,
            **kwargs,
        )
        response: Response[Label] = await self.client.rest.issues.async_create_label(
            owner=self.owner,
            repo=self.repo_name,
            **params,
        )
        return response.parsed_data

    @handle_github_422
    @retry_on_rate_limit()
    async def update_label(
        self,
        name: str,
        new_name: str | None = None,
        color: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> Label:
        """Update a label for a repository."""
        params = self._omit_null_parameters(
            new_name=new_name,
            color=color,
            description=description,
            **kwargs,
        )
        response: Response[Label] = await self.client.rest.issues.async_update_label(
            owner=self.owner,
            repo=self.repo_name,
            name=name,
            **params,
        )
        return response.parsed_data

    @retry_on_rate_limit()
    async def delete_label(self, name: str) -> None:
        """Delete a label for a repository."""
        await self.client.rest.issues.async_delete_label(owner=self.owner, repo=self.repo_name, name=name)
        return None

    @retry_on_rate_limit()
    async def list_labels(self, **kwargs: Any) -> list[Label]:
        """List labels for a repository."""
        response: Response[list[Label]] = await self.client.rest.issues.async_list_labels_for_repo(owner=self.owner, repo=self.repo_name, **kwargs)
        return response.parsed_data

    @handle_github_422
    @retry_on_rate_limit()
    async def set_labels_on_issue(self, issue_number: int, labels: list[str]) -> None:
        """Set labels on a specific issue (or pull request - GitHub considers them the same for label purposes)."""
        if labels:
            await self.client.rest.issues.async_set_labels(
                owner=self.owner,
                repo=self.repo_name,
                issue_number=issue_number,
                labels=labels,
            )
        else:
            await self.client.rest.issues.async_remove_all_labels(
                owner=self.owner,
                repo=self.repo_name,
                issue_number=issue_number,
            )

    # Pull Request CRUD
    @retry_on_rate_limit()
    async def get_pull_request(self, pull_request_number: int) -> PullRequest:
        """Get a pull request from the repository."""
        response: Response[PullRequest] = await self.client.rest.pulls.async_get(
            owner=self.owner, repo=self.repo_name, pull_number=pull_request_number
        )
        return response.parsed_data

    @handle_github_422
    @retry_on_rate_limit()
    async def create_pull_request(
        self,
        title: str,
        head: str,
        base: str,
        body: str | None = None,
        draft: bool | None = None,
        maintainer_can_modify: bool | None = None,
        **kwargs: Any,
    ) -> PullRequest:
        """Create a pull request for a repository."""
        params = self._omit_null_parameters(
            title=title,
            head=head,
            base=base,
            body=body,
            draft=draft,
            maintainer_can_modify=maintainer_can_modify,
            **kwargs,
        )
        response: Response[PullRequest] = await self.client.rest.pulls.async_create(
            owner=self.owner,
            repo=self.repo_name,
            **params,
        )
        return response.parsed_data

    @handle_github_422
    @retry_on_rate_limit()
    async def update_pull_request(
        self,
        pull_number: int,
        title: str | None = None,
        body: str | None = None,
        state: Literal["open", "closed"] | None = None,
        base: str | None = None,
        maintainer_can_modify: bool | None = None,
        **kwargs: Any,
    ) -> PullRequest:
        """Update a pull request for a repository."""
        params = self._omit_null_parameters(
            title=title,
            body=body,
            state=state,
            base=base,
            maintainer_can_modify=maintainer_can_modify,
            **kwargs,
        )
        response: Response[PullRequest] = await self.client.rest.pulls.async_update(
            owner=self.owner,
            repo=self.repo_name,
            pull_number=pull_number,
            **params,
        )
        return response.parsed_data

    @retry_on_rate_limit()
    async def list_pull_requests(
        self, state: Literal["open", "closed", "all"] = "all", per_page: int = 100, **kwargs: Any
    ) -> list[PullRequestSimple]:
        """List all pull requests for a repository, handling pagination."""
        all_pull_requests: list[PullRequestSimple] = []
        page: int = 1
        while True:
            response: Response[list[PullRequestSimple]] = await self.client.rest.pulls.async_list(
                owner=self.owner,
                repo=self.repo_name,
                state=state,
                per_page=per_page,
                page=page,
                **kwargs,
            )
            pull_requests: list[PullRequestSimple] = response.parsed_data
            if not pull_requests:
                break
            all_pull_requests.extend(pull_requests)
            if len(pull_requests) < per_page:
                break
            page += 1
        return all_pull_requests

    @handle_github_422
    async def merge_pull_request(self, pull_number: int, **kwargs: Any) -> Any:
        """Merge a pull request for a repository."""
        response = await self.client.rest.pulls.async_merge(owner=self.owner, repo=self.repo_name, pull_number=pull_number, **kwargs)
        return response.parsed_data

    @handle_github_422
    @retry_on_rate_limit()
    async def close_pull_request(self, pull_number: int, **kwargs: Any) -> PullRequest:
        """Close a pull request for a repository."""
        response: Response[PullRequest] = await self.client.rest.pulls.async_update(
            owner=self.owner,
            repo=self.repo_name,
            pull_number=pull_number,
            state="closed",
            **kwargs,
        )
        return response.parsed_data

    @retry_on_rate_limit()
    async def branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists in the repository."""
        try:
            await self.client.rest.repos.async_get_branch(owner=self.owner, repo=self.repo_name, branch=branch_name)
            return True
        except Exception as e:
            if "not found" in str(e).lower():
                return False
            raise

    @handle_github_422
    @retry_on_rate_limit()
    async def create_branch(self, branch_name: str, base_branch: str) -> None:
        """Create a new branch from the base branch."""
        try:
            base_ref = await self.client.rest.git.async_get_ref(owner=self.owner, repo=self.repo_name, ref=f"heads/{base_branch}")
        except RequestFailed as exc:
            # If a 409 conflict is raise, it means the base branch is empty.
            # The default branch must contain at least one commit before a PR
            # into the default branch can be created.
            if exc.response.status_code == 409:
                logger.error(
                    f"A 409 Conflict was returned when accessing base branch '{base_branch}'. This may be because the default branch is empty. "
                    f"You must have at least one commit on the default branch ('{base_branch}') to create a pull request against it."
                )
            raise
        sha = base_ref.parsed_data.object_.sha
        # Create the new branch
        await self.client.rest.git.async_create_ref(
            owner=self.owner,
            repo=self.repo_name,
            ref=f"refs/heads/{branch_name}",
            sha=sha,
        )
        logger.info("Created branch", branch=branch_name, base_branch=base_branch)

    @handle_github_422
    @retry_on_rate_limit()
    async def commit_files_to_branch(
        self,
        branch_name: str,
        files: list[tuple[str, str]],  # (file_path, file_content)
        commit_message: str,
    ) -> None:
        """Commit or update files on a branch using the GitHub Contents API."""
        for file_path, file_content in files:
            # Check if the file exists to get its SHA (required for update)
            try:
                file_resp = await self.client.rest.repos.async_get_content(
                    owner=self.owner,
                    repo=self.repo_name,
                    path=file_path,
                    ref=branch_name,
                )
                file_sha = file_resp.parsed_data.sha
            except Exception as e:
                if "not found" in str(e).lower():
                    file_sha = None
                else:
                    raise
            import base64

            encoded_content = base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
            params = {
                "owner": self.owner,
                "repo": self.repo_name,
                "path": file_path,
                "message": commit_message,
                "content": encoded_content,
                "branch": branch_name,
            }
            if file_sha:
                params["sha"] = file_sha
            await self.client.rest.repos.async_create_or_update_file_contents(**params)
            logger.info("Committed file to branch", file=file_path, branch=branch_name)

    @retry_on_rate_limit()
    async def list_files_in_pull_request(self, pull_number: int) -> list[Any]:
        """List files changed in a pull request."""
        response = await self.client.rest.pulls.async_list_files(
            owner=self.owner,
            repo=self.repo_name,
            pull_number=pull_number,
        )
        return response.parsed_data

    def _normalize_pr_file_data(self, file_data: Any) -> dict[str, Any]:
        """Normalize PR file data to consistent format (helper for DRY).

        This helper handles file data from various sources (API objects, dicts)
        and ensures a consistent output format.

        Args:
            file_data: File data from GitHub API (could be object or dict)

        Returns:
            Dictionary with normalized file statistics
        """
        # Handle both API objects (with getattr) and dicts (with .get)
        if isinstance(file_data, dict):
            filename = file_data.get("filename", "")
            additions = file_data.get("additions", 0) or 0
            deletions = file_data.get("deletions", 0) or 0
            status = file_data.get("status", "unknown")
            patch = file_data.get("patch")
        else:
            # API object
            filename = getattr(file_data, "filename", "")
            additions = getattr(file_data, "additions", 0) or 0
            deletions = getattr(file_data, "deletions", 0) or 0
            status = getattr(file_data, "status", "unknown")
            patch = getattr(file_data, "patch", None)

        return {
            "filename": filename,
            "additions": int(additions),
            "deletions": int(deletions),
            "changes": int(additions) + int(deletions),
            "status": status,
            "patch": patch,
        }

    async def _get_pr_files_method_1_standard_api(self, pr_number: int) -> list[dict[str, Any]] | None:
        """Method 1: Get PR files using standard PR files API (primary method).

        This is the primary method that has worked reliably for most cases.
        It uses the standard GitHub pulls.list_files endpoint.

        Args:
            pr_number: Pull request number

        Returns:
            List of normalized file dictionaries if successful, None if this method fails
        """
        try:
            logger.debug("Method 1: Trying standard PR files API", owner=self.owner, repo=self.repo_name, pr_number=pr_number)

            files = await self.list_files_in_pull_request(pr_number)

            if not files:
                logger.debug("Method 1: No files returned", owner=self.owner, repo=self.repo_name, pr_number=pr_number)
                return []

            # Normalize all files
            normalized_files = [self._normalize_pr_file_data(file_data) for file_data in files]

            logger.debug(
                "Method 1 (standard API) SUCCESS",
                owner=self.owner,
                repo=self.repo_name,
                pr_number=pr_number,
                file_count=len(normalized_files),
                total_additions=sum(f["additions"] for f in normalized_files),
                total_deletions=sum(f["deletions"] for f in normalized_files),
            )
            return normalized_files

        except Exception as e:
            logger.warning(
                "Method 1 (standard API) failed, will try fallback methods",
                owner=self.owner,
                repo=self.repo_name,
                pr_number=pr_number,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def _get_pr_files_method_2_from_commits(self, pr_number: int) -> list[dict[str, Any]] | None:
        """Method 2: Get PR files by aggregating from PR commits.

        This method gets all commits in the PR and aggregates their changed files.
        Useful when the standard files API fails or returns incomplete data.

        Args:
            pr_number: Pull request number

        Returns:
            List of normalized file dictionaries if successful, None if this method fails
        """
        try:
            logger.debug("Method 2: Trying to aggregate files from PR commits", owner=self.owner, repo=self.repo_name, pr_number=pr_number)

            # Get all commits in the PR
            commits_response = await self.client.rest.pulls.async_list_commits(
                owner=self.owner, repo=self.repo_name, pull_number=pr_number, per_page=100
            )
            # Use raw JSON to avoid Pydantic validation issues with commit verification field
            commits = commits_response.json()

            if not commits:
                logger.debug("Method 2: No commits found in PR", owner=self.owner, repo=self.repo_name, pr_number=pr_number)
                return None

            # Aggregate files from all commits
            files_dict: dict[str, dict[str, Any]] = {}

            for commit in commits:
                # Handle commit as dict (from JSON) instead of Pydantic object
                commit_sha = commit.get("sha") if isinstance(commit, dict) else getattr(commit, "sha", None)
                try:
                    # Get files for this commit
                    commit_stats = await self.get_commit_stats(commit_sha)
                    commit_files = commit_stats.get("files", [])

                    for file_data in commit_files:
                        filename = file_data.get("filename", "")
                        if not filename:
                            continue

                        # Aggregate stats per file (take max to avoid double counting)
                        if filename in files_dict:
                            # Keep the maximum changes seen for this file
                            existing = files_dict[filename]
                            existing["additions"] = max(existing["additions"], file_data.get("additions", 0))
                            existing["deletions"] = max(existing["deletions"], file_data.get("deletions", 0))
                            existing["changes"] = existing["additions"] + existing["deletions"]
                        else:
                            files_dict[filename] = self._normalize_pr_file_data(file_data)

                except Exception as commit_error:
                    logger.debug(
                        f"Method 2: Failed to get stats for commit {commit_sha}, continuing",
                        owner=self.owner,
                        repo=self.repo_name,
                        commit_sha=commit_sha,
                        error=str(commit_error),
                    )
                    continue

            if not files_dict:
                logger.debug("Method 2: No files aggregated from commits", owner=self.owner, repo=self.repo_name, pr_number=pr_number)
                return None

            normalized_files = list(files_dict.values())

            logger.debug(
                "Method 2 (from commits) SUCCESS",
                owner=self.owner,
                repo=self.repo_name,
                pr_number=pr_number,
                file_count=len(normalized_files),
                total_additions=sum(f["additions"] for f in normalized_files),
                total_deletions=sum(f["deletions"] for f in normalized_files),
            )
            return normalized_files

        except Exception as e:
            logger.warning(
                "Method 2 (from commits) failed",
                owner=self.owner,
                repo=self.repo_name,
                pr_number=pr_number,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def _get_pr_files_method_3_from_compare(self, pr_number: int) -> list[dict[str, Any]] | None:
        """Method 3: Get PR files using compare API between base and head.

        This method uses the compare API to get the diff between the PR's
        base and head branches. Useful when both standard API and commit
        aggregation fail.

        Args:
            pr_number: Pull request number

        Returns:
            List of normalized file dictionaries if successful, None if this method fails
        """
        try:
            logger.debug("Method 3: Trying compare API between base and head", owner=self.owner, repo=self.repo_name, pr_number=pr_number)

            # Get the PR details to find base and head
            pr = await self.get_pull_request(pr_number)

            if not pr.base or not pr.head:
                logger.debug("Method 3: PR missing base or head reference", owner=self.owner, repo=self.repo_name, pr_number=pr_number)
                return None

            base_sha = pr.base.sha
            head_sha = pr.head.sha

            # Use compare API
            compare_response = await self.client.rest.repos.async_compare_commits(owner=self.owner, repo=self.repo_name, base=base_sha, head=head_sha)
            compare_data = compare_response.json()

            if not isinstance(compare_data, dict):
                return None

            files = compare_data.get("files", [])
            if not isinstance(files, list) or not files:
                logger.debug("Method 3: No files in compare result", owner=self.owner, repo=self.repo_name, pr_number=pr_number)
                return None

            # Normalize all files
            normalized_files = [self._normalize_pr_file_data(file_data) for file_data in files]

            logger.debug(
                "Method 3 (compare API) SUCCESS",
                owner=self.owner,
                repo=self.repo_name,
                pr_number=pr_number,
                file_count=len(normalized_files),
                total_additions=sum(f["additions"] for f in normalized_files),
                total_deletions=sum(f["deletions"] for f in normalized_files),
            )
            return normalized_files

        except Exception as e:
            logger.warning(
                "Method 3 (compare API) failed",
                owner=self.owner,
                repo=self.repo_name,
                pr_number=pr_number,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    @retry_on_rate_limit()
    @handle_github_422
    async def get_pull_request_files_with_stats(self, pr_number: int) -> list[dict[str, Any]]:
        """Get PR files with detailed statistics using multi-path resilient approach.

        This method tries multiple API approaches to ensure maximum compatibility
        across different GitHub instances (GitHub.com vs Enterprise) and edge cases.

        Methods tried in order:
        1. Standard PR files API (pulls.list_files) - Primary method, works most of time
        2. Aggregate from PR commits - Alternative when standard API fails
        3. Compare API between base and head - Fallback for specific scenarios

        Args:
            pr_number: Pull request number

        Returns:
            List of dictionaries with consistent file statistics:
            - filename: Name of the changed file
            - additions: Number of lines added (guaranteed integer)
            - deletions: Number of lines deleted (guaranteed integer)
            - changes: Total changes (additions + deletions)
            - status: File change status (added, modified, deleted, etc.)
            - patch: Optional diff patch content

        Example:
            files = await adapter.get_pull_request_files_with_stats(123)
            for file in files:
                print(f"{file['filename']}: +{file['additions']} -{file['deletions']}")
        """
        logger.debug("Fetching PR files using multi-path approach", owner=self.owner, repo=self.repo_name, pr_number=pr_number)

        # Method 1: Standard PR files API (primary path)
        result = await self._get_pr_files_method_1_standard_api(pr_number)
        if result is not None:
            return result

        # Method 2: Aggregate from PR commits
        result = await self._get_pr_files_method_2_from_commits(pr_number)
        if result is not None:
            return result

        # Method 3: Compare API between base and head
        result = await self._get_pr_files_method_3_from_compare(pr_number)
        if result is not None:
            return result

        # All methods exhausted - return empty list
        logger.error(
            "All methods failed to get PR files, returning empty result",
            owner=self.owner,
            repo=self.repo_name,
            pr_number=pr_number,
        )
        return []

    @retry_on_rate_limit()
    async def get_file_content_from_pull_request(self, file_path: str, branch: str) -> str:
        """Get the content of a file from a specific branch (typically the PR's head branch)."""
        response = await self.client.rest.repos.async_get_content(
            owner=self.owner,
            repo=self.repo_name,
            path=file_path,
            ref=branch,
        )
        return base64.b64decode(response.parsed_data.content).decode("utf-8")

    # Release/Tag Operations
    @handle_github_422
    @retry_on_rate_limit()
    async def list_releases(self, per_page: int = 100, **kwargs: Any) -> list[Release]:
        """List all releases for a repository, handling pagination."""
        logger.debug("Fetching releases", owner=self.owner, repo=self.repo_name, per_page=per_page)
        all_releases: list[Release] = []
        page: int = 1
        while True:
            logger.debug(f"Fetching releases page {page}")
            response: Response[list[Release]] = await self.client.rest.repos.async_list_releases(
                owner=self.owner,
                repo=self.repo_name,
                per_page=per_page,
                page=page,
                **kwargs,
            )
            releases: list[Release] = response.parsed_data
            logger.debug(f"Got {len(releases)} releases on page {page}")

            for release in releases:
                # Format dates as ISO strings for human readability
                created_at_str = release.created_at.isoformat() if release.created_at else "N/A"
                published_at_str = release.published_at.isoformat() if release.published_at else "N/A"

                logger.debug(
                    "Release found",
                    tag_name=release.tag_name,
                    name=release.name,
                    draft=release.draft,
                    prerelease=release.prerelease,
                    created_at=created_at_str,
                    published_at=published_at_str,
                )

            if not releases:
                break
            all_releases.extend(releases)
            if len(releases) < per_page:
                break
            page += 1

        logger.info(f"Total releases found: {len(all_releases)}")
        return all_releases

    @handle_github_422
    @retry_on_rate_limit()
    async def get_release(self, tag_name: str) -> Release:
        """Get a specific release by tag name."""
        response: Response[Release] = await self.client.rest.repos.async_get_release_by_tag(
            owner=self.owner,
            repo=self.repo_name,
            tag=tag_name,
        )
        return response.parsed_data

    @handle_github_422
    @retry_on_rate_limit()
    async def get_latest_release(self) -> Release:
        """Get the latest release for the repository."""
        response: Response[Release] = await self.client.rest.repos.async_get_latest_release(
            owner=self.owner,
            repo=self.repo_name,
        )
        return response.parsed_data

    # Commit Operations
    @handle_github_422
    @retry_on_rate_limit()
    async def get_commit(self, commit_sha: str) -> dict[str, Any]:
        """Get a commit by SHA.

        Returns the raw commit data as a dictionary instead of a Commit model
        due to githubkit's Pydantic model not matching GitHub's API response
        for the verification field.

        Args:
            commit_sha: The commit SHA (can be abbreviated)

        Returns:
            Dictionary containing the raw commit data from GitHub API
        """
        # IMPORTANT: githubkit Bug Workaround (as of v0.12.14)
        #
        # We return raw dict instead of parsed Commit model due to a Pydantic validation error
        # in githubkit's model definition. The issue occurs because:
        #
        # 1. GitHub's API returns this structure for commit verification:
        #    {
        #      "verified": false,
        #      "reason": "unsigned",
        #      "signature": null,
        #      "payload": null
        #    }
        #
        # 2. But githubkit's Commit model expects either:
        #    - The literal string "<UNSET>" (not a dict)
        #    - OR a Verification object with a required "verified_at" field
        #
        # 3. GitHub's API doesn't include "verified_at", causing validation to fail with:
        #    "commit.verification.Verification.verified_at Field required"
        #
        # This bug only surfaces when fetching full commit details (this endpoint), not when
        # getting commits through other endpoints like PR listings, because:
        # - Simple commit objects from PR listings don't include the verification field
        # - Only the full commit details endpoint (/repos/{owner}/{repo}/commits/{ref})
        #   returns the problematic verification structure
        #
        # Our release notes feature needs full commit messages (including extended body text),
        # which is why we must use this endpoint and encountered this issue.
        #
        # Alternative approaches considered and rejected:
        # - Catching ValidationError: Would hide real problems and create silent failures
        # - Downgrading githubkit: Could introduce other compatibility issues
        # - Using a different GitHub library: Too much refactoring for a single issue
        #
        # When githubkit fixes their model, we can revert to returning typed Commit objects
        # by simply changing this to: return response.parsed_data

        response = await self.client.rest.repos.async_get_commit(owner=self.owner, repo=self.repo_name, ref=commit_sha)
        # Return raw JSON response instead of parsed_data due to githubkit bug
        return response.json()

    def _extract_stats_from_commit_data(self, commit_data: Any) -> dict[str, Any] | None:
        """Extract statistics from commit data response (helper for DRY).

        Args:
            commit_data: Response data from GitHub API

        Returns:
            Dictionary with stats if valid, None if data is malformed
        """
        # Validate response structure
        if not isinstance(commit_data, dict):
            logger.warning(
                "Commit data is not a dictionary",
                owner=self.owner,
                repo=self.repo_name,
                data_type=type(commit_data).__name__,
            )
            return None

        stats = commit_data.get("stats", {})
        files = commit_data.get("files", [])

        # Validate stats and files structure
        if not isinstance(stats, dict):
            logger.warning("Stats field is not a dictionary", owner=self.owner, repo=self.repo_name, stats_type=type(stats).__name__)
            return None

        if not isinstance(files, list):
            logger.warning("Files field is not a list", owner=self.owner, repo=self.repo_name, files_type=type(files).__name__)
            files = []

        return {
            "additions": stats.get("additions", 0),
            "deletions": stats.get("deletions", 0),
            "total": stats.get("total", 0),
            "files": files,
        }

    async def _get_commit_stats_method_1_rest_api(self, commit_sha: str) -> dict[str, Any] | None:
        """Method 1: Get commit stats using standard REST API (primary method).

        This is the primary method that has worked reliably for weeks.
        It uses the standard GitHub repos.get_commit endpoint.

        Args:
            commit_sha: The SHA of the commit

        Returns:
            Stats dictionary if successful, None if this method fails
        """
        try:
            logger.debug("Method 1: Trying REST API get_commit", owner=self.owner, repo=self.repo_name, commit_sha=commit_sha)

            response = await self.client.rest.repos.async_get_commit(owner=self.owner, repo=self.repo_name, ref=commit_sha)
            commit_data = response.json()

            result = self._extract_stats_from_commit_data(commit_data)
            if result:
                logger.debug(
                    "Method 1 (REST API) SUCCESS",
                    owner=self.owner,
                    repo=self.repo_name,
                    commit_sha=commit_sha,
                    additions=result["additions"],
                    deletions=result["deletions"],
                    files_changed=len(result["files"]),
                )
                return result

            logger.warning("Method 1 (REST API) returned malformed data", owner=self.owner, repo=self.repo_name, commit_sha=commit_sha)
            return None

        except Exception as e:
            logger.warning(
                "Method 1 (REST API) failed, will try fallback methods",
                owner=self.owner,
                repo=self.repo_name,
                commit_sha=commit_sha,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def _get_commit_stats_method_2_compare_api(self, commit_sha: str) -> dict[str, Any] | None:
        """Method 2: Get commit stats using compare API with parent commit.

        This method compares the commit with its parent to calculate stats.
        Useful when direct commit fetch returns unexpected format.

        Args:
            commit_sha: The SHA of the commit

        Returns:
            Stats dictionary if successful, None if this method fails
        """
        try:
            logger.debug("Method 2: Trying compare API", owner=self.owner, repo=self.repo_name, commit_sha=commit_sha)

            # First, get the commit to find its parent
            commit_response = await self.client.rest.repos.async_get_commit(owner=self.owner, repo=self.repo_name, ref=commit_sha)
            commit_data = commit_response.json()

            if not isinstance(commit_data, dict):
                return None

            parents = commit_data.get("parents", [])
            if not parents or not isinstance(parents, list):
                logger.debug("Method 2: No parent commit found", owner=self.owner, repo=self.repo_name, commit_sha=commit_sha)
                return None

            parent_sha = parents[0].get("sha") if isinstance(parents[0], dict) else None
            if not parent_sha:
                return None

            # Use compare API
            compare_response = await self.client.rest.repos.async_compare_commits(
                owner=self.owner, repo=self.repo_name, base=parent_sha, head=commit_sha
            )
            compare_data = compare_response.json()

            if not isinstance(compare_data, dict):
                return None

            files = compare_data.get("files", [])
            if not isinstance(files, list):
                return None

            # Calculate stats from files
            additions = sum(f.get("additions", 0) for f in files if isinstance(f, dict))
            deletions = sum(f.get("deletions", 0) for f in files if isinstance(f, dict))

            result = {"additions": additions, "deletions": deletions, "total": additions + deletions, "files": files}

            logger.debug(
                "Method 2 (compare API) SUCCESS",
                owner=self.owner,
                repo=self.repo_name,
                commit_sha=commit_sha,
                additions=result["additions"],
                deletions=result["deletions"],
                files_changed=len(result["files"]),
            )
            return result

        except Exception as e:
            logger.warning(
                "Method 2 (compare API) failed",
                owner=self.owner,
                repo=self.repo_name,
                commit_sha=commit_sha,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def _get_commit_stats_method_3_single_commit_compare(self, commit_sha: str) -> dict[str, Any] | None:
        """Method 3: Get commit stats using single commit comparison format.

        This method uses GitHub's single-commit compare format which sometimes
        works when standard endpoints fail. Uses format: commit_sha~1...commit_sha

        Args:
            commit_sha: The SHA of the commit

        Returns:
            Stats dictionary if successful, None if this method fails
        """
        try:
            logger.debug("Method 3: Trying single-commit compare format", owner=self.owner, repo=self.repo_name, commit_sha=commit_sha)

            # Use the ~1 notation to compare with parent
            compare_response = await self.client.rest.repos.async_compare_commits(
                owner=self.owner, repo=self.repo_name, base=f"{commit_sha}~1", head=commit_sha
            )
            compare_data = compare_response.json()

            if not isinstance(compare_data, dict):
                return None

            files = compare_data.get("files", [])
            if not isinstance(files, list):
                return None

            # Calculate stats from files
            additions = sum(f.get("additions", 0) for f in files if isinstance(f, dict))
            deletions = sum(f.get("deletions", 0) for f in files if isinstance(f, dict))

            result = {"additions": additions, "deletions": deletions, "total": additions + deletions, "files": files}

            logger.debug(
                "Method 3 (single-commit compare) SUCCESS",
                owner=self.owner,
                repo=self.repo_name,
                commit_sha=commit_sha,
                additions=result["additions"],
                deletions=result["deletions"],
                files_changed=len(result["files"]),
            )
            return result

        except Exception as e:
            logger.warning(
                "Method 3 (single-commit compare) failed",
                owner=self.owner,
                repo=self.repo_name,
                commit_sha=commit_sha,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    @retry_on_rate_limit()
    @handle_github_422
    async def get_commit_stats(self, commit_sha: str) -> dict[str, Any]:
        """Get detailed statistics for a specific commit using multi-path resilient approach.

        This method tries multiple API approaches to ensure maximum compatibility
        across different GitHub instances (GitHub.com vs Enterprise) and edge cases.

        Methods tried in order:
        1. Standard REST API (repos.get_commit) - Primary method, works 95% of time
        2. Compare API with parent commit - Alternative when REST fails
        3. Single-commit compare format - Fallback for specific GitHub variants

        Args:
            commit_sha: The SHA of the commit to get statistics for

        Returns:
            Dictionary containing commit statistics with keys:
            - additions: Number of lines added
            - deletions: Number of lines deleted
            - total: Total lines changed (additions + deletions)
            - files: List of file objects that were changed

        Example:
            stats = await client.get_commit_stats("abc123...")
            print(f"Lines added: {stats['additions']}")
            print(f"Lines deleted: {stats['deletions']}")
            print(f"Files changed: {len(stats['files'])}")
        """
        logger.debug("Fetching commit statistics using multi-path approach", owner=self.owner, repo=self.repo_name, commit_sha=commit_sha)

        # Method 1: Standard REST API (primary path that's worked for weeks)
        result = await self._get_commit_stats_method_1_rest_api(commit_sha)
        if result:
            return result

        # Method 2: Compare API with explicit parent
        result = await self._get_commit_stats_method_2_compare_api(commit_sha)
        if result:
            return result

        # Method 3: Single-commit compare format
        result = await self._get_commit_stats_method_3_single_commit_compare(commit_sha)
        if result:
            return result

        # All methods exhausted - return empty stats
        logger.error(
            "All methods failed to get commit stats, returning empty result",
            owner=self.owner,
            repo=self.repo_name,
            commit_sha=commit_sha,
        )
        return {"additions": 0, "deletions": 0, "total": 0, "files": []}

    # Organization Operations
    @retry_on_rate_limit()
    async def list_organization_repositories(self, org_name: str, per_page: int = 100, **kwargs: Any) -> list[FullRepository]:
        """List all repositories for an organization, handling pagination.

        Args:
            org_name: Name of the GitHub organization
            per_page: Number of repositories per page (default: 100, max: 100)
            **kwargs: Additional parameters to pass to the API
                - type: Filter by repository type ('all', 'public', 'private', 'forks', 'sources', 'member')
                - sort: Sort repositories ('created', 'updated', 'pushed', 'full_name')
                - direction: Sort direction ('asc' or 'desc')

        Returns:
            List of all repositories in the organization

        Example:
            repos = await client.list_organization_repositories(
                "my-org",
                type="sources",  # Exclude forks
                sort="updated",
                direction="desc"
            )
        """
        from github_ops_manager.utils.retry import retry_on_rate_limit

        @retry_on_rate_limit()
        async def _fetch_page(page: int) -> list[FullRepository]:
            response: Response[list[FullRepository]] = await self.client.rest.repos.async_list_for_org(
                org=org_name, per_page=per_page, page=page, **kwargs
            )
            return response.parsed_data

        all_repos: list[FullRepository] = []
        page: int = 1

        logger.info("Fetching repositories for organization", org=org_name, per_page=per_page, filters=kwargs)

        while True:
            logger.debug(f"Fetching organization repositories page {page}")
            repos: list[FullRepository] = await _fetch_page(page)

            if not repos:
                break

            all_repos.extend(repos)

            if len(repos) < per_page:
                break

            page += 1

        logger.info("Fetched all repositories for organization", org=org_name, total_repos=len(all_repos))

        return all_repos

    @retry_on_rate_limit()
    async def list_branches(self, protected: bool | None = None, per_page: int = 100, **kwargs: Any) -> list[dict[str, Any]]:
        """List branches for the repository.

        Args:
            protected: If True, only protected branches. If False, only unprotected.
            per_page: Number of branches per page (max 100)
            **kwargs: Additional parameters for the API

        Returns:
            List of branch dictionaries with name, commit SHA, and protection status
        """
        logger.debug(
            "Listing branches",
            owner=self.owner,
            repo=self.repo_name,
            protected=protected,
        )

        all_branches = []
        page = 1

        while True:
            response = self.client.rest.repos.list_branches(
                owner=self.owner, repo=self.repo_name, protected=protected, per_page=per_page, page=page, **kwargs
            )

            branches = response.parsed_data
            if not branches:
                break

            for branch in branches:
                all_branches.append(
                    {
                        "name": branch.name,
                        "commit": {"sha": branch.commit.sha} if branch.commit else None,
                        "protected": branch.protected if hasattr(branch, "protected") else None,
                    }
                )

            # GitHub returns less than per_page when no more results
            if len(branches) < per_page:
                break

            page += 1

        logger.debug(
            "Retrieved branches",
            owner=self.owner,
            repo=self.repo_name,
            branch_count=len(all_branches),
        )

        return all_branches

    @retry_on_rate_limit()
    async def list_commits(
        self,
        sha: str | None = None,
        path: str | None = None,
        author: str | None = None,
        committer: str | None = None,
        since: str | None = None,
        until: str | None = None,
        per_page: int = 100,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """List commits for the repository with optional filters, handling pagination.

        Args:
            sha: SHA or branch to start listing commits from (default: default branch)
            path: Only commits containing this file path will be returned
            author: GitHub username or email address to filter by commit author
            committer: GitHub username or email address to filter by committer
            since: ISO 8601 date string - only commits after this date
            until: ISO 8601 date string - only commits before this date
            per_page: Number of commits per page (default: 100, max: 100)
            **kwargs: Additional parameters to pass to the API

        Returns:
            List of commit dictionaries with full statistics

        Example:
            # Get all commits by a specific author in the last week
            from datetime import datetime, timedelta
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            commits = await client.list_commits(
                author="username",
                since=week_ago
            )
        """
        from github_ops_manager.utils.retry import retry_on_rate_limit

        @retry_on_rate_limit()
        async def _fetch_page(page: int) -> list[dict[str, Any]]:
            params = self._omit_null_parameters(
                sha=sha, path=path, author=author, committer=committer, since=since, until=until, per_page=per_page, page=page, **kwargs
            )
            response = await self.client.rest.repos.async_list_commits(owner=self.owner, repo=self.repo_name, **params)
            # Return raw JSON to include stats
            return response.json()

        all_commits: list[dict[str, Any]] = []
        page: int = 1

        logger.info(
            "Fetching commits for repository",
            owner=self.owner,
            repo=self.repo_name,
            filters={
                "sha": sha,
                "path": path,
                "author": author,
                "since": since,
                "until": until,
            },
        )

        while True:
            logger.debug(f"Fetching commits page {page}")
            commits: list[dict[str, Any]] = await _fetch_page(page)

            if not commits:
                break

            all_commits.extend(commits)

            if len(commits) < per_page:
                break

            page += 1

        logger.info("Fetched all commits", owner=self.owner, repo=self.repo_name, total_commits=len(all_commits))

        return all_commits

    @retry_on_rate_limit()
    async def list_pull_request_reviews(self, pull_number: int, per_page: int = 100, **kwargs: Any) -> list[Any]:
        """List all reviews for a pull request, handling pagination.

        Args:
            pull_number: The pull request number
            per_page: Number of reviews per page (default: 100, max: 100)
            **kwargs: Additional parameters to pass to the API

        Returns:
            List of review objects

        Example:
            reviews = await client.list_pull_request_reviews(123)
            for review in reviews:
                print(f"{review.user.login}: {review.state}")
        """
        from github_ops_manager.utils.retry import retry_on_rate_limit

        @retry_on_rate_limit()
        async def _fetch_page(page: int) -> list[Any]:
            response = await self.client.rest.pulls.async_list_reviews(
                owner=self.owner, repo=self.repo_name, pull_number=pull_number, per_page=per_page, page=page, **kwargs
            )
            return response.parsed_data

        all_reviews: list[Any] = []
        page: int = 1

        logger.info("Fetching reviews for pull request", owner=self.owner, repo=self.repo_name, pull_number=pull_number)

        while True:
            logger.debug(f"Fetching PR reviews page {page}")
            reviews: list[Any] = await _fetch_page(page)

            if not reviews:
                break

            all_reviews.extend(reviews)

            if len(reviews) < per_page:
                break

            page += 1

        logger.info(
            "Fetched all reviews for pull request", owner=self.owner, repo=self.repo_name, pull_number=pull_number, total_reviews=len(all_reviews)
        )

        return all_reviews
