"""Reconcile GitHub authentication configuration."""

from pathlib import Path

from github_ops_manager.configuration.exceptions import GitHubAuthenticationConfigurationUndefinedError
from github_ops_manager.configuration.models import GitHubAuthenticationType


async def validate_github_authentication_configuration(
    github_pat_token: str | None,
    github_app_id: int | None,
    github_app_private_key_path: Path | None,
    github_app_installation_id: int | None,
) -> GitHubAuthenticationType:
    """Validates the GitHub authentication configuration.

    Args:
        github_pat_token (str | None): The GitHub PAT token.
        github_app_id (int | None): The GitHub App ID.
        github_app_private_key_path (str | None): The path to the GitHub App private key.
        github_app_installation_id (int | None): The GitHub App installation ID.

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
        msg = "Incomplete GitHub App configuration - missing settings include " + ", ".join(
            f"{setting['name']} (command line option {setting['cli_name']}, environment variable {setting['env_name']})"
            for setting in missing_settings
        )
        raise GitHubAuthenticationConfigurationUndefinedError(msg)
    else:
        raise GitHubAuthenticationConfigurationUndefinedError(
            "No GitHub authentication configuration provided. Please provide either a PAT or a GitHub App configuration."
        )
