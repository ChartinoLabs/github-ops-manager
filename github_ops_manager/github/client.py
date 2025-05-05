# This file is intended to hold the setup for the authenticated githubkit client.

"""Sets up the authenticated githubkit client."""

from typing import TypeAlias

from githubkit import GitHub
from githubkit.auth import (
    AppAuthStrategy,
    AppInstallationAuthStrategy,
    TokenAuthStrategy,
)
from githubkit.versions.latest.models import Installation

from github_ops_manager.configuration.config import config
from github_ops_manager.configuration.models import GitHubAuthenticationType
from github_ops_manager.utils.github import split_repository_in_configuration

GitHubClient: TypeAlias = GitHub[AppInstallationAuthStrategy] | GitHub[TokenAuthStrategy]


async def get_github_app_client() -> GitHub[AppInstallationAuthStrategy]:
    """Returns an authenticated GitHub client using GitHub App credentials."""
    app_id = config.github_app_id
    private_key_path = config.github_app_private_key_path
    installation_id = config.github_app_installation_id
    if not (app_id and private_key_path and installation_id):
        raise RuntimeError("GitHub App authentication requires app_id, private_key_path, and installation_id in config.")
    try:
        with open(private_key_path) as f:
            private_key = f.read()
        auth = AppAuthStrategy(
            app_id=app_id,
            private_key=private_key,
        )
        app_client = GitHub(auth=auth, base_url=config.github_api_url)

        owner, repository = await split_repository_in_configuration()

        resp = app_client.rest.apps.get_repo_installation(
            owner=owner,
            repo=repository,
        )
        repo_installation: Installation = resp.parsed_data
        installation_github = app_client.with_auth(app_client.auth.as_installation(repo_installation.id))
        return installation_github
    except Exception as e:
        raise ValueError(f"Failed to get GitHub App installation: {e}") from e


async def get_github_pat_client() -> GitHub[TokenAuthStrategy]:
    """Returns an authenticated GitHub client using GitHub PAT credentials."""
    token = config.github_pat_token
    if not token:
        raise RuntimeError("GitHub PAT authentication requires github_pat_token in config.")
    return GitHub(auth=TokenAuthStrategy(token), base_url=config.github_api_url)


async def get_github_client() -> GitHubClient:
    """Returns an authenticated GitHub client using either GitHub App or PAT credentials.

    Prefers GitHub App authentication if all required configuration fields are set.
    Supports custom base URL for GitHub Enterprise Server (GHES).
    Raises RuntimeError if no valid credentials are found.
    """
    if config.github_authentication_type == GitHubAuthenticationType.APP:
        return await get_github_app_client()
    elif config.github_authentication_type == GitHubAuthenticationType.PAT:
        return await get_github_pat_client()
    else:
        raise RuntimeError("No valid GitHub credentials found in configuration. Please set GitHub App or PAT fields.")
