"""Defines the Command Line Interface (CLI) using Typer."""

from pathlib import Path
from typing import Any

import typer

from github_ops_manager.configuration import driver

typer_app = typer.Typer()


def get_context() -> str:
    """Get the context directory for the GitHub Operations Manager."""
    return typer.get_app_dir("github_ops_manager")


@typer_app.callback()
def base_cli_arguments(
    ctx: typer.Context,
    debug: bool = False,
    github_api_url: str = "https://api.github.com",
    github_pat_token: str | None = None,
    github_app_id: str | None = None,
    github_app_private_key_path: Path | None = None,
    github_app_installation_id: str | None = None,
    repo: str | None = None,
) -> None:
    """Base CLI arguments for the GitHub Operations Manager."""
    ctx.ensure_object(dict)
    ctx.obj.update(
        debug=debug,
        github_api_url=github_api_url,
        github_pat_token=github_pat_token,
        github_app_id=github_app_id,
        github_app_private_key_path=github_app_private_key_path,
        github_app_installation_id=github_app_installation_id,
        repo=repo,
    )


@typer_app.command(name="process-issues")
def process_issues_cli(
    ctx: typer.Context, yaml_path: Path | None = None, create_prs: bool = False
) -> None:
    """Processes issues in a GitHub repository."""
    base_args: dict[str, Any] = ctx.obj or {}
    config = driver.get_process_issues_config(
        debug=base_args.get("debug", False),
        github_api_url=base_args.get("github_api_url", "https://api.github.com"),
        github_pat_token=base_args.get("github_pat_token"),
        github_app_id=base_args.get("github_app_id"),
        github_app_private_key_path=base_args.get("github_app_private_key_path"),
        github_app_installation_id=base_args.get("github_app_installation_id"),
        repo=base_args.get("repo"),
        yaml_path=yaml_path,
        create_prs=create_prs,
    )
    print(config)


@typer_app.command(name="export-issues")
def export_issues_cli(
    ctx: typer.Context,
    output_file: Path | None = None,
    state: str | None = None,
    label: str | None = None,
) -> None:
    """Exports issues from a GitHub repository."""
    base_args: dict[str, Any] = ctx.obj or {}
    config = driver.get_export_issues_config(
        debug=base_args.get("debug", False),
        github_api_url=base_args.get("github_api_url", "https://api.github.com"),
        github_pat_token=base_args.get("github_pat_token"),
        github_app_id=base_args.get("github_app_id"),
        github_app_private_key_path=base_args.get("github_app_private_key_path"),
        github_app_installation_id=base_args.get("github_app_installation_id"),
        repo=base_args.get("repo"),
        output_file=output_file,
        state=state,
        label=label,
    )
    print(config)
