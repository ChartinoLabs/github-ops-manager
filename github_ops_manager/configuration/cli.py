"""Defines the Command Line Interface (CLI) using Typer."""

import asyncio
import sys
import traceback
from pathlib import Path

import typer
from dotenv import load_dotenv

from github_ops_manager.configuration.reconcile import validate_github_authentication_configuration
from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.synchronize.driver import run_process_issues_workflow

load_dotenv()

typer_app = typer.Typer()


def get_context() -> str:
    """Get the context directory for the GitHub Operations Manager."""
    return typer.get_app_dir("github_ops_manager")


@typer_app.command(name="process-issues")
def process_issues_cli(
    ctx: typer.Context,
    yaml_path: Path = typer.Argument(envvar="YAML_PATH", help="Path to YAML file for issues."),
    create_prs: bool = typer.Option(False, envvar="CREATE_PRS", help="Create PRs for issues."),
    repo: str = typer.Argument(envvar="REPO", help="Repository name (owner/repo)."),
    debug: bool = typer.Option(False, envvar="DEBUG", help="Enable debug mode."),
    github_api_url: str = typer.Option("https://api.github.com", envvar="GITHUB_API_URL", help="GitHub API URL."),
    github_pat_token: str = typer.Option(None, envvar="GITHUB_PAT_TOKEN", help="GitHub Personal Access Token."),
    github_app_id: int = typer.Option(None, envvar="GITHUB_APP_ID", help="GitHub App ID."),
    github_app_private_key_path: Path | None = typer.Option(None, envvar="GITHUB_APP_PRIVATE_KEY_PATH", help="Path to GitHub App private key."),
    github_app_installation_id: int = typer.Option(None, envvar="GITHUB_APP_INSTALLATION_ID", help="GitHub App Installation ID."),
) -> None:
    """Processes issues in a GitHub repository."""
    # Validate GitHub authentication configuration
    github_auth_type = asyncio.run(
        validate_github_authentication_configuration(
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
        )
    )
    # Run the workflow
    result = asyncio.run(
        run_process_issues_workflow(
            repo=repo,
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
            github_auth_type=github_auth_type,
            github_api_url=github_api_url,
            yaml_path=yaml_path,
        )
    )
    if result.errors:
        typer.echo("Error(s) encountered while processing YAML:", err=True)
        for err in result.errors:
            typer.echo(str(err), err=True)
        sys.exit(1)

    typer.echo(f"Loaded {len(result.issue_synchronization_results.results)} issues from {yaml_path}")
    if result.issue_synchronization_results.results:
        typer.echo(f"First issue: {result.issue_synchronization_results.results[0].desired_issue.model_dump()}")


@typer_app.command(name="export-issues")
def export_issues_cli(
    ctx: typer.Context,
    output_file: Path | None = typer.Option(None, envvar="OUTPUT_FILE", help="Path to save exported issues."),
    state: str = typer.Option(None, envvar="STATE", help="Filter issues by state (open, closed, all)."),
    label: str = typer.Option(None, envvar="LABEL", help="Filter issues by label."),
    repo: str = typer.Argument(envvar="REPO", help="Repository name (owner/repo)."),
    debug: bool = typer.Option(False, envvar="DEBUG", help="Enable debug mode."),
    github_api_url: str = typer.Option("https://api.github.com", envvar="GITHUB_API_URL", help="GitHub API URL."),
    github_pat_token: str = typer.Option(None, envvar="GITHUB_PAT_TOKEN", help="GitHub Personal Access Token."),
    github_app_id: int = typer.Option(None, envvar="GITHUB_APP_ID", help="GitHub App ID."),
    github_app_private_key_path: Path | None = typer.Option(None, envvar="GITHUB_APP_PRIVATE_KEY_PATH", help="Path to GitHub App private key."),
    github_app_installation_id: int = typer.Option(None, envvar="GITHUB_APP_INSTALLATION_ID", help="GitHub App Installation ID."),
) -> None:
    """Exports issues from a GitHub repository."""
    # Validate GitHub authentication configuration
    asyncio.run(
        validate_github_authentication_configuration(
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
        )
    )
    if not repo:
        typer.echo("Repository must be provided via --repo or REPO env var.", err=True)
        sys.exit(1)
    if not (github_pat_token or (github_app_id and github_app_private_key_path is not None and github_app_installation_id)):
        typer.echo("You must provide either a GitHub PAT token or all GitHub App credentials.", err=True)
        sys.exit(1)
    # Here you would call your export logic, e.g. run_export_issues_workflow()
    typer.echo(f"Exporting issues for repo {repo} to {output_file or 'stdout'}")
    # Placeholder for actual export logic


@typer_app.command(name="fetch-files")
def fetch_files_cli(
    ctx: typer.Context,
    file_paths: list[str] = typer.Argument(..., help="One or more file paths to fetch from the repository (relative to repo root)."),
    branch: str | None = typer.Option(None, "--branch", help="Branch, tag, or commit SHA to fetch from. Defaults to the default branch."),
    repo: str = typer.Argument(envvar="REPO", help="Repository name (owner/repo)."),
    debug: bool = typer.Option(False, envvar="DEBUG", help="Enable debug mode."),
    github_api_url: str = typer.Option("https://api.github.com", envvar="GITHUB_API_URL", help="GitHub API URL."),
    github_pat_token: str = typer.Option(None, envvar="GITHUB_PAT_TOKEN", help="GitHub Personal Access Token."),
    github_app_id: int = typer.Option(None, envvar="GITHUB_APP_ID", help="GitHub App ID."),
    github_app_private_key_path: Path | None = typer.Option(None, envvar="GITHUB_APP_PRIVATE_KEY_PATH", help="Path to GitHub App private key."),
    github_app_installation_id: int = typer.Option(None, envvar="GITHUB_APP_INSTALLATION_ID", help="GitHub App Installation ID."),
) -> None:
    """Fetch one or more files from the repository and download them locally at the same relative path."""
    # Validate GitHub authentication configuration
    github_auth_type = asyncio.run(
        validate_github_authentication_configuration(
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
        )
    )

    async def fetch_files() -> None:
        adapter = await GitHubKitAdapter.create(
            repo=repo,
            github_auth_type=github_auth_type,
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
            github_api_url=github_api_url,
        )
        # Determine branch
        if branch:
            use_branch = branch
        else:
            repo_info = await adapter.get_repository()
            default_branch = getattr(repo_info, "default_branch", None)
            if not isinstance(default_branch, str) or not default_branch:
                typer.echo("Could not determine default branch.", err=True)
                raise typer.Exit(1)
            use_branch = default_branch
        downloaded: list[str] = []
        for file_path in file_paths:
            try:
                content: str = await adapter.get_file_content_from_pull_request(file_path, use_branch)
            except Exception as exc:
                typer.echo(f"Error fetching '{file_path}' from branch '{use_branch}': {exc}", err=True)
                traceback.print_exc()
                raise typer.Exit(1) from exc
            # Write to local file, creating directories as needed
            local_path = Path(file_path)
            if local_path.parent != Path(""):
                local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(content, encoding="utf-8")
            downloaded.append(str(local_path))
        typer.echo(f"Successfully downloaded {len(downloaded)} file(s) from branch '{use_branch}':")
        for path in downloaded:
            typer.echo(f"  - {path}")

    asyncio.run(fetch_files())


if __name__ == "__main__":
    typer_app()
