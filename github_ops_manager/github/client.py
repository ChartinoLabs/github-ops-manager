# This file is intended to hold the setup for the authenticated githubkit client.

"""Sets up the authenticated githubkit client."""

from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias

import structlog
from githubkit import GitHub
from githubkit.auth import (
    AppAuthStrategy,
    AppInstallationAuthStrategy,
    TokenAuthStrategy,
)
from githubkit.retry import RETRY_RATE_LIMIT, RETRY_SERVER_ERROR, RetryChainDecision
from githubkit.versions.latest.models import Installation

from github_ops_manager.configuration.models import GitHubAuthenticationType
from github_ops_manager.utils.github import split_repository_in_configuration

logger = structlog.get_logger(__name__)

GitHubClient: TypeAlias = GitHub[AppInstallationAuthStrategy] | GitHub[TokenAuthStrategy]

# Retry configuration: retry on rate limits and server errors
# Rate limit retry waits for the reset time before retrying
# Server error retry attempts up to 3 times with backoff
AUTO_RETRY_CONFIG = RetryChainDecision(RETRY_RATE_LIMIT, RETRY_SERVER_ERROR)


async def _log_rate_limit_status(client: GitHubClient) -> None:
    """Fetch and log the current GitHub API rate limit status.

    This does not count against the rate limit quota.
    Failures are logged as warnings but do not raise exceptions.
    """
    try:
        response = await client.rest.rate_limit.async_get()
        rate = response.parsed_data.rate

        # Calculate human-readable time until reset
        reset_time = datetime.fromtimestamp(rate.reset, tz=UTC)
        now = datetime.now(tz=UTC)
        seconds_until_reset = max(0, int((reset_time - now).total_seconds()))
        minutes, seconds = divmod(seconds_until_reset, 60)

        if minutes > 0:
            reset_str = f"{minutes}m {seconds}s"
        else:
            reset_str = f"{seconds}s"

        logger.info(
            "GitHub API rate limit status",
            limit=rate.limit,
            used=rate.used,
            remaining=rate.remaining,
            resets_in=reset_str,
        )

        # Warn if rate limit is running low (less than 10% remaining)
        if rate.limit > 0 and rate.remaining < rate.limit * 0.1:
            logger.warning(
                "GitHub API rate limit is running low",
                remaining=rate.remaining,
                limit=rate.limit,
                resets_in=reset_str,
            )
    except Exception as e:
        logger.warning("Failed to fetch GitHub API rate limit status", error=str(e))


async def get_github_app_client(
    repo: str,
    github_app_id: int,
    github_app_private_key_path: Path,
    github_app_installation_id: int,
    github_api_url: str,
) -> GitHub[AppInstallationAuthStrategy]:
    """Returns an authenticated GitHub client using GitHub App credentials."""
    if not (github_app_id and github_app_private_key_path and github_app_installation_id):
        raise RuntimeError("GitHub App authentication requires app_id, private_key_path, and installation_id in config.")
    try:
        with open(github_app_private_key_path) as f:
            private_key = f.read()
        auth = AppAuthStrategy(
            app_id=github_app_id,
            private_key=private_key,
        )
        # Disable HTTP caching to always get fresh data
        # Enable auto_retry for rate limits and server errors
        app_client = GitHub(auth=auth, base_url=github_api_url, http_cache=False, auto_retry=AUTO_RETRY_CONFIG)

        owner, repository = await split_repository_in_configuration(repo=repo)

        resp = app_client.rest.apps.get_repo_installation(
            owner=owner,
            repo=repository,
        )
        repo_installation: Installation = resp.parsed_data
        installation_github = app_client.with_auth(app_client.auth.as_installation(repo_installation.id))
        await _log_rate_limit_status(installation_github)
        return installation_github
    except Exception as e:
        raise ValueError(f"Failed to get GitHub App installation: {e}") from e


async def get_github_pat_client(github_pat_token: str, github_api_url: str) -> GitHub[TokenAuthStrategy]:
    """Returns an authenticated GitHub client using GitHub PAT credentials."""
    if not github_pat_token:
        raise RuntimeError("GitHub PAT authentication requires github_pat_token in config.")
    # Disable HTTP caching to always get fresh data
    # Enable auto_retry for rate limits and server errors
    client = GitHub(auth=TokenAuthStrategy(github_pat_token), base_url=github_api_url, http_cache=False, auto_retry=AUTO_RETRY_CONFIG)
    await _log_rate_limit_status(client)
    return client


async def get_github_client(
    repo: str,
    github_auth_type: GitHubAuthenticationType,
    github_pat_token: str | None,
    github_app_id: int | None,
    github_app_private_key_path: Path | None,
    github_app_installation_id: int | None,
    github_api_url: str,
) -> GitHubClient:
    """Returns an authenticated GitHub client using either GitHub App or PAT credentials.

    Prefers GitHub App authentication if all required configuration fields are set.
    Supports custom base URL for GitHub Enterprise Server (GHES).
    Raises RuntimeError if no valid credentials are found.
    """
    if github_auth_type == GitHubAuthenticationType.APP:
        if not (github_app_id and github_app_private_key_path and github_app_installation_id):
            raise RuntimeError("GitHub App authentication requires app_id, private_key_path, and installation_id in config.")
        return await get_github_app_client(repo, github_app_id, github_app_private_key_path, github_app_installation_id, github_api_url)
    elif github_auth_type == GitHubAuthenticationType.PAT:
        if not github_pat_token:
            raise RuntimeError("GitHub PAT authentication requires github_pat_token in config.")
        return await get_github_pat_client(github_pat_token, github_api_url)
