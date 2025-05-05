"""Defines the Command Line Interface (CLI) using Typer."""

import asyncio
import sys
from pathlib import Path
from typing import Any

import typer

from github_ops_manager.configuration import driver
from github_ops_manager.processing.workflow_runner import (
    run_process_issues_workflow,
)

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
    github_app_id: int | None = None,
    github_app_private_key_path: Path | None = None,
    github_app_installation_id: int | None = None,
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
def process_issues_cli(ctx: typer.Context, yaml_path: Path | None = None, create_prs: bool = False) -> None:
    """Processes issues in a GitHub repository."""
    base_args: dict[str, Any] = ctx.obj or {}
    config = asyncio.run(
        driver.get_process_issues_config(
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
    )

    result = asyncio.run(run_process_issues_workflow(config, raise_on_yaml_error=True))
    if result.errors:
        typer.echo("Error(s) encountered while processing YAML:", err=True)
        for err in result.errors:
            typer.echo(str(err), err=True)
        sys.exit(1)
    if config.yaml_path is not None:
        typer.echo(f"Loaded {len(result.issues)} issues from {config.yaml_path}")
        if result.issues:
            typer.echo(f"First issue: {result.issues[0].model_dump()}")
    else:
        typer.echo("No YAML path provided. Skipping YAML processing.")


@typer_app.command(name="export-issues")
def export_issues_cli(
    ctx: typer.Context,
    output_file: Path | None = None,
    state: str | None = None,
    label: str | None = None,
) -> None:
    """Exports issues from a GitHub repository."""
    base_args: dict[str, Any] = ctx.obj or {}
    asyncio.run(
        driver.get_export_issues_config(
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
    )


if __name__ == "__main__":
    typer_app()
