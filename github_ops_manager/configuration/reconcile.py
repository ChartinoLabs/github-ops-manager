"""Reconciles configuration between CLI arguments and environment variables.

CLI arguments are considered more explicit and take precedence over environment
variables.
"""

from pathlib import Path

from github_ops_manager.configuration.env import settings
from github_ops_manager.configuration.exceptions import GitHubAuthenticationConfigurationUndefinedError, RequiredConfigurationElementError
from github_ops_manager.configuration.models import (
    BaseConfig,
    ExportIssuesConfig,
    GitHubAuthenticationType,
    ProcessIssuesConfig,
)


async def validate_github_authentication_configuration(
    github_pat_token: str | None,
    github_app_id: str | None,
    github_app_private_key_path: Path | None,
    github_app_installation_id: str | None,
) -> GitHubAuthenticationType:
    """Validates the GitHub authentication configuration.

    Args:
        github_pat_token (str | None): The GitHub PAT token.
        github_app_id (str | None): The GitHub App ID.
        github_app_private_key_path (str | None): The path to the GitHub App private key.
        github_app_installation_id (str | None): The GitHub App installation ID.

    Raises:
        GitHubAuthenticationConfigurationUndefinedError: If both PAT and App configurations are undefined.

    Returns:
        GitHubAuthenticationType: The type of GitHub authentication used.
    """
    if github_pat_token and (github_app_id or github_app_private_key_path or github_app_installation_id):
        raise GitHubAuthenticationConfigurationUndefinedError("Both PAT and GitHub App configurations are defined. Please use one or the other.")

    if github_pat_token:
        return GitHubAuthenticationType.PAT

    if github_app_id and github_app_private_key_path and github_app_installation_id:
        return GitHubAuthenticationType.APP
    elif github_app_id or github_app_private_key_path or github_app_installation_id:
        missing_settings: list[dict[str, str]] = []
        if not github_app_id:
            missing_settings.append(
                {
                    "name": "GitHub App ID",
                    "cli_name": "github_app_id",
                    "env_name": "GITHUB_APP_ID",
                }
            )
        if not github_app_private_key_path:
            missing_settings.append(
                {
                    "name": "GitHub App private key path",
                    "cli_name": "github_app_private_key_path",
                    "env_name": "GITHUB_APP_PRIVATE_KEY_PATH",
                }
            )
        if not github_app_installation_id:
            missing_settings.append(
                {
                    "name": "GitHub App installation ID",
                    "cli_name": "github_app_installation_id",
                    "env_name": "GITHUB_APP_INSTALLATION_ID",
                }
            )
        msg = "Incomplete GitHub App configuration - missing settings include "
        for setting in missing_settings:
            msg += f"{setting['name']} (command line option {setting['cli_name']}, environment variable {setting['env_name']}), "
        raise GitHubAuthenticationConfigurationUndefinedError(msg[:-2])
    else:
        raise GitHubAuthenticationConfigurationUndefinedError(
            "No GitHub authentication configuration provided. Please provide either a PAT or a GitHub App configuration."
        )


async def reconcile_base_configuration(
    cli_debug: bool,
    cli_github_api_url: str,
    cli_github_pat_token: str | None,
    cli_github_app_id: str | None,
    cli_github_app_private_key_path: Path | None,
    cli_github_app_installation_id: str | None,
    cli_repo: str | None,
) -> BaseConfig:
    """Reconciles the base configuration for the GitHub Operations Manager CLI.

    Returns:
        BaseConfig: The reconciled base configuration.
    """
    reconciled_debug = cli_debug or settings.DEBUG
    reconciled_github_api_url = cli_github_api_url or settings.GITHUB_API_URL
    reconciled_github_pat_token = cli_github_pat_token or settings.GITHUB_PAT_TOKEN
    reconciled_github_app_id = cli_github_app_id or settings.GITHUB_APP_ID
    reconciled_github_app_private_key_path = cli_github_app_private_key_path or settings.GITHUB_APP_PRIVATE_KEY_PATH
    reconciled_github_app_installation_id = cli_github_app_installation_id or settings.GITHUB_APP_INSTALLATION_ID
    reconciled_repo = cli_repo or settings.REPO

    github_authentication_type = await validate_github_authentication_configuration(
        github_pat_token=reconciled_github_pat_token,
        github_app_id=reconciled_github_app_id,
        github_app_private_key_path=reconciled_github_app_private_key_path,
        github_app_installation_id=reconciled_github_app_installation_id,
    )

    if reconciled_repo is None:
        raise RequiredConfigurationElementError(
            name="Repository",
            cli_name="repo",
            env_name="REPO",
        )

    return BaseConfig(
        debug=reconciled_debug,
        github_api_url=reconciled_github_api_url,
        github_authentication_type=github_authentication_type,
        github_pat_token=reconciled_github_pat_token,
        github_app_id=reconciled_github_app_id,
        github_app_private_key_path=reconciled_github_app_private_key_path,
        github_app_installation_id=reconciled_github_app_installation_id,
        repo=reconciled_repo,
    )
