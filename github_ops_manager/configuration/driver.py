"""Synchronous driver for configuration reconciliation for the CLI entry point."""

import asyncio
from pathlib import Path

from github_ops_manager.configuration import reconcile
from github_ops_manager.configuration.models import (
    ExportIssuesConfig,
    ProcessIssuesConfig,
)


def get_process_issues_config(
    debug: bool = False,
    github_api_url: str = "https://api.github.com",
    github_pat_token: str | None = None,
    github_app_id: str | None = None,
    github_app_private_key_path: Path | None = None,
    github_app_installation_id: str | None = None,
    repo: str | None = None,
    yaml_path: Path | None = None,
    create_prs: bool = False,
) -> ProcessIssuesConfig:
    """Synchronously get the reconciled process-issues configuration."""
    return asyncio.run(
        reconcile.reconcile_process_issues_configuration(
            cli_debug=debug,
            cli_github_api_url=github_api_url,
            cli_github_pat_token=github_pat_token,
            cli_github_app_id=github_app_id,
            cli_github_app_private_key_path=github_app_private_key_path,
            cli_github_app_installation_id=github_app_installation_id,
            cli_repo=repo,
            cli_yaml_path=yaml_path,
            cli_create_prs=create_prs,
        )
    )


def get_export_issues_config(
    debug: bool = False,
    github_api_url: str = "https://api.github.com",
    github_pat_token: str | None = None,
    github_app_id: str | None = None,
    github_app_private_key_path: Path | None = None,
    github_app_installation_id: str | None = None,
    repo: str | None = None,
    output_file: Path | None = None,
    state: str | None = None,
    label: str | None = None,
) -> ExportIssuesConfig:
    """Synchronously get the reconciled export-issues configuration."""
    return asyncio.run(
        reconcile.reconcile_export_issues_configuration(
            cli_debug=debug,
            cli_github_api_url=github_api_url,
            cli_github_pat_token=github_pat_token,
            cli_github_app_id=github_app_id,
            cli_github_app_private_key_path=github_app_private_key_path,
            cli_github_app_installation_id=github_app_installation_id,
            cli_repo=repo,
            cli_output_file=output_file,
            cli_state=state,
            cli_label=label,
        )
    )
