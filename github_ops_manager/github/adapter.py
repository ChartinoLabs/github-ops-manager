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
    SimpleUser,
    Team,
)

from github_ops_manager.configuration.models import GitHubAuthenticationType
from github_ops_manager.utils.github import split_repository_in_configuration

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
    async def get_repository(self) -> FullRepository:
        """Get the repository for the current client."""
        response: Response[FullRepository] = await self.client.rest.repos.async_get(owner=self.owner, repo=self.repo_name)
        return response.parsed_data

    # Issue CRUD
    @handle_github_422
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

    async def delete_label(self, name: str) -> None:
        """Delete a label for a repository."""
        await self.client.rest.issues.async_delete_label(owner=self.owner, repo=self.repo_name, name=name)
        return None

    async def list_labels(self, **kwargs: Any) -> list[Label]:
        """List labels for a repository."""
        response: Response[list[Label]] = await self.client.rest.issues.async_list_labels_for_repo(owner=self.owner, repo=self.repo_name, **kwargs)
        return response.parsed_data

    @handle_github_422
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
    async def get_pull_request(self, pull_request_number: int) -> PullRequest:
        """Get a pull request from the repository."""
        response: Response[PullRequest] = await self.client.rest.pulls.async_get(
            owner=self.owner, repo=self.repo_name, pull_number=pull_request_number
        )
        return response.parsed_data

    @handle_github_422
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

    async def list_files_in_pull_request(self, pull_number: int) -> list[Any]:
        """List files changed in a pull request."""
        response = await self.client.rest.pulls.async_list_files(
            owner=self.owner,
            repo=self.repo_name,
            pull_number=pull_number,
        )
        return response.parsed_data

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
    async def get_release(self, tag_name: str) -> Release:
        """Get a specific release by tag name."""
        response: Response[Release] = await self.client.rest.repos.async_get_release_by_tag(
            owner=self.owner,
            repo=self.repo_name,
            tag=tag_name,
        )
        return response.parsed_data

    @handle_github_422
    async def get_latest_release(self) -> Release:
        """Get the latest release for the repository."""
        response: Response[Release] = await self.client.rest.repos.async_get_latest_release(
            owner=self.owner,
            repo=self.repo_name,
        )
        return response.parsed_data

    # Commit Operations
    @handle_github_422
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

    # Team Management Operations
    @handle_github_422
    async def get_user_by_username(self, username: str) -> SimpleUser | None:
        """Get a GitHub user by username.

        Args:
            username: The GitHub username to look up

        Returns:
            SimpleUser object if found, None if not found

        Raises:
            ValueError: If there's an error other than user not found
        """
        try:
            response: Response[SimpleUser] = await self.client.rest.users.async_get_by_username(username=username)
            return response.parsed_data
        except RequestFailed as exc:
            if exc.response.status_code == 404:
                return None
            raise ValueError(f"Error getting user {username}: {exc}") from exc

    @handle_github_422
    async def search_users_by_email(self, email: str) -> list[SimpleUser]:
        """Search for GitHub users by email address.

        Args:
            email: The email address to search for

        Returns:
            List of SimpleUser objects matching the email

        Note:
            This uses GitHub's user search API which may have limitations
            based on the user's privacy settings.
        """
        try:
            response = await self.client.rest.search.async_users(q=f"{email} in:email")
            return response.parsed_data.items
        except RequestFailed as exc:
            logger.error("Error searching users by email", email=email, error=str(exc))
            return []

    @handle_github_422
    async def get_team(self, org: str, team_slug: str) -> Team | None:
        """Get team information by organization and team slug.

        Args:
            org: The organization name
            team_slug: The team slug (name)

        Returns:
            Team object if found, None if not found

        Raises:
            ValueError: If there's an error other than team not found
        """
        try:
            response: Response[Team] = await self.client.rest.teams.async_get_by_name(org=org, team_slug=team_slug)
            return response.parsed_data
        except RequestFailed as exc:
            if exc.response.status_code == 404:
                return None
            raise ValueError(f"Error getting team {org}/{team_slug}: {exc}") from exc

    @handle_github_422
    async def add_user_to_team(self, org: str, team_slug: str, username: str) -> bool:
        """Add a user to a GitHub team.

        Args:
            org: The organization name
            team_slug: The team slug (name)
            username: The GitHub username to add

        Returns:
            True if user was added successfully, False otherwise

        Raises:
            ValueError: If there's an error adding the user to the team
        """
        try:
            await self.client.rest.teams.async_add_or_update_membership_for_user_in_org(org=org, team_slug=team_slug, username=username)
            logger.info("Successfully added user to team", username=username, org=org, team=team_slug)
            return True
        except RequestFailed as exc:
            if exc.response.status_code == 404:
                logger.error("Team or user not found", username=username, org=org, team=team_slug)
                return False
            elif exc.response.status_code == 403:
                # Get detailed error message from GitHub API response
                try:
                    error_data = exc.response.json()
                    error_message = error_data.get("message", "Forbidden")
                    detailed_errors = error_data.get("errors", [])

                    # Common 403 reasons for team membership
                    if "must be an organization owner or team maintainer" in error_message.lower():
                        detailed_message = (
                            "Permission denied: You must be an organization owner or team maintainer "
                            "to add users to this team. Current permissions are insufficient."
                        )
                    elif "not a member" in error_message.lower():
                        detailed_message = (
                            f"Permission denied: User '{username}' is not a member of the '{org}' organization. "
                            "Users must be organization members before being added to teams."
                        )
                    elif "private" in error_message.lower() or "visibility" in error_message.lower():
                        detailed_message = (
                            "Permission denied: Team visibility settings prevent adding this user. "
                            "The team may be private or have restricted membership policies."
                        )
                    else:
                        detailed_message = f"Permission denied (403 Forbidden): {error_message}"
                        if detailed_errors:
                            detailed_message += f" Details: {'; '.join([str(err) for err in detailed_errors])}"

                    logger.error(
                        "Team membership permission denied", username=username, org=org, team=team_slug, message=error_message, errors=detailed_errors
                    )

                except Exception:
                    detailed_message = (
                        f"Permission denied (403 Forbidden): You don't have permission to add users to team "
                        f"'{org}/{team_slug}'. You must be an organization owner or team maintainer."
                    )

                raise ValueError(detailed_message) from exc

            raise ValueError(f"Error adding user {username} to team {org}/{team_slug}: {exc}") from exc

    @handle_github_422
    async def check_team_membership(self, org: str, team_slug: str, username: str) -> bool:
        """Check if a user is already a member of a team.

        Args:
            org: The organization name
            team_slug: The team slug (name)
            username: The GitHub username to check

        Returns:
            True if user is a team member, False otherwise
        """
        try:
            await self.client.rest.teams.async_get_membership_for_user_in_org(org=org, team_slug=team_slug, username=username)
            return True
        except RequestFailed as exc:
            if exc.response.status_code == 404:
                return False
            raise ValueError(f"Error checking team membership for {username} in {org}/{team_slug}: {exc}") from exc
