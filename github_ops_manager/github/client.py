# This file is intended to hold the setup for the authenticated githubkit client.

"""Sets up the authenticated githubkit client."""

from pathlib import Path
from typing import TypeAlias

from githubkit import GitHub
from githubkit.auth import (
    AppAuthStrategy,
    AppInstallationAuthStrategy,
    TokenAuthStrategy,
)
from githubkit.versions.latest.models import Installation

from github_ops_manager.configuration.models import GitHubAuthenticationType
from github_ops_manager.utils.github import split_repository_in_configuration

GitHubClient: TypeAlias = GitHub[AppInstallationAuthStrategy] | GitHub[TokenAuthStrategy]


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
        app_client = GitHub(auth=auth, base_url=github_api_url, http_cache=False)

        owner, repository = await split_repository_in_configuration(repo=repo)

        resp = app_client.rest.apps.get_repo_installation(
            owner=owner,
            repo=repository,
        )
        repo_installation: Installation = resp.parsed_data
        installation_github = app_client.with_auth(app_client.auth.as_installation(repo_installation.id))
        return installation_github
    except Exception as e:
        raise ValueError(f"Failed to get GitHub App installation: {e}") from e


async def get_github_pat_client(github_pat_token: str, github_api_url: str) -> GitHub[TokenAuthStrategy]:
    """Returns an authenticated GitHub client using GitHub PAT credentials."""
    if not github_pat_token:
        raise RuntimeError("GitHub PAT authentication requires github_pat_token in config.")
    # Disable HTTP caching to always get fresh data
    return GitHub(auth=TokenAuthStrategy(github_pat_token), base_url=github_api_url, http_cache=False)


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
