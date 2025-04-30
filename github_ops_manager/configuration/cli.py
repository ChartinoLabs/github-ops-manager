"""Defines the Command Line Interface (CLI) using Typer."""

from pathlib import Path

import typer

typer_app = typer.Typer()


@typer_app.callback()
def base_cli_arguments(
    debug: bool = False,
    github_api_url: str = "https://api.github.com",
    github_pat_token: str | None = None,
    github_app_id: str | None = None,
    github_app_private_key_path: Path | None = None,
    github_app_installation_id: str | None = None,
    repo: str | None = None,
) -> None:
    """Base CLI arguments for the GitHub Operations Manager.

    This function sets up the base arguments for the CLI, including debug mode
    and GitHub API settings. It does not actually perform any actions itself.
    """
    pass


@typer_app.command(name="process-issues")
def process_issues_cli(yaml_path: Path | None = None, create_prs: bool = False) -> None:
    """Processes issues in a GitHub repository."""
    pass


@typer_app.command(name="export-issues")
def export_issues_cli(output_file: Path | None = None, state: str | None = None, label: str | None = None) -> None:
    """Exports issues from a GitHub repository."""
    pass
