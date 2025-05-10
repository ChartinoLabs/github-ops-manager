"""Defines the Command Line Interface (CLI) using Typer."""

import asyncio
import subprocess
import sys
import traceback
from pathlib import Path

import typer
from dotenv import load_dotenv
from ruamel.yaml import YAML

from github_ops_manager.configuration.reconcile import validate_github_authentication_configuration
from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.yaml_processor import YAMLProcessor
from github_ops_manager.schemas.default_issue import IssueModel, IssuesYAMLModel, PullRequestModel
from github_ops_manager.synchronize.driver import run_process_issues_workflow

load_dotenv()

typer_app = typer.Typer(pretty_exceptions_show_locals=False)

# --- Add a new Typer group for repo commands ---
repo_app = typer.Typer(help="Repository-related commands")


def repo_callback(ctx: typer.Context, repo: str = typer.Argument(..., help="Repository name (owner/repo).")) -> None:
    """Set the repository for the current context."""
    ctx.ensure_object(dict)
    ctx.obj["repo"] = repo


repo_app.callback()(repo_callback)


# --- Move process-issues under repo_app ---
@repo_app.command(name="process-issues")
def process_issues_cli(
    ctx: typer.Context,
    yaml_path: Path = typer.Argument(envvar="YAML_PATH", help="Path to YAML file for issues."),
    create_prs: bool = typer.Option(False, envvar="CREATE_PRS", help="Create PRs for issues."),
    debug: bool = typer.Option(False, envvar="DEBUG", help="Enable debug mode."),
    github_api_url: str = typer.Option("https://api.github.com", envvar="GITHUB_API_URL", help="GitHub API URL."),
    github_pat_token: str = typer.Option(None, envvar="GITHUB_PAT_TOKEN", help="GitHub Personal Access Token."),
    github_app_id: int = typer.Option(None, envvar="GITHUB_APP_ID", help="GitHub App ID."),
    github_app_private_key_path: Path | None = typer.Option(None, envvar="GITHUB_APP_PRIVATE_KEY_PATH", help="Path to GitHub App private key."),
    github_app_installation_id: int = typer.Option(None, envvar="GITHUB_APP_INSTALLATION_ID", help="GitHub App Installation ID."),
) -> None:
    """Processes issues in a GitHub repository."""
    repo: str = ctx.obj["repo"]
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


# --- Move export-issues under repo_app ---
@repo_app.command(name="export-issues")
def export_issues_cli(
    ctx: typer.Context,
    output_file: Path | None = typer.Option(None, envvar="OUTPUT_FILE", help="Path to save exported issues."),
    state: str = typer.Option(None, envvar="STATE", help="Filter issues by state (open, closed, all)."),
    label: str = typer.Option(None, envvar="LABEL", help="Filter issues by label."),
    debug: bool = typer.Option(False, envvar="DEBUG", help="Enable debug mode."),
    github_api_url: str = typer.Option("https://api.github.com", envvar="GITHUB_API_URL", help="GitHub API URL."),
    github_pat_token: str = typer.Option(None, envvar="GITHUB_PAT_TOKEN", help="GitHub Personal Access Token."),
    github_app_id: int = typer.Option(None, envvar="GITHUB_APP_ID", help="GitHub App ID."),
    github_app_private_key_path: Path | None = typer.Option(None, envvar="GITHUB_APP_PRIVATE_KEY_PATH", help="Path to GitHub App private key."),
    github_app_installation_id: int = typer.Option(None, envvar="GITHUB_APP_INSTALLATION_ID", help="GitHub App Installation ID."),
) -> None:
    """Exports issues from a GitHub repository."""
    repo: str = ctx.obj["repo"]
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


# --- Move fetch-files under repo_app ---
@repo_app.command(name="fetch-files")
def fetch_files_cli(
    ctx: typer.Context,
    file_paths: list[str] = typer.Argument(..., help="One or more file paths to fetch from the repository (relative to repo root)."),
    branch: str | None = typer.Option(None, "--branch", help="Branch, tag, or commit SHA to fetch from. Defaults to the default branch."),
    debug: bool = typer.Option(False, envvar="DEBUG", help="Enable debug mode."),
    github_api_url: str = typer.Option("https://api.github.com", envvar="GITHUB_API_URL", help="GitHub API URL."),
    github_pat_token: str = typer.Option(None, envvar="GITHUB_PAT_TOKEN", help="GitHub Personal Access Token."),
    github_app_id: int = typer.Option(None, envvar="GITHUB_APP_ID", help="GitHub App ID."),
    github_app_private_key_path: Path | None = typer.Option(None, envvar="GITHUB_APP_PRIVATE_KEY_PATH", help="Path to GitHub App private key."),
    github_app_installation_id: int = typer.Option(None, envvar="GITHUB_APP_INSTALLATION_ID", help="GitHub App Installation ID."),
) -> None:
    """Fetch one or more files from the repository and download them locally at the same relative path."""
    repo: str = ctx.obj["repo"]
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


# --- Register the repo_app as a sub-app of the main Typer app ---
typer_app.add_typer(repo_app, name="repo")


# Restore sync-new-files as a top-level command
@typer_app.command(name="sync-new-files")
def sync_new_files_cli(
    issues_file: Path = typer.Argument(..., help="Path to the issues YAML file."),
    labels: str = typer.Option("", "--labels", help="Comma-separated labels to assign to each created issue and pull request."),
) -> None:
    """Detect new files in the current git repo and add issues/PRs for each to the issues file."""
    # 1. Find new (untracked) files
    try:
        result = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], capture_output=True, text=True, check=True)
        new_files: list[str] = [f for f in result.stdout.splitlines() if f.strip()]
    except Exception as exc:
        typer.echo(f"Error running git to find new files: {exc}", err=True)
        raise typer.Exit(1) from exc

    if not new_files:
        typer.echo("No new (untracked) files found.")
        return

    # 2. Load and validate the issues file
    processor = YAMLProcessor()
    try:
        issues_model: IssuesYAMLModel = processor.load_issues_model([str(issues_file)])
    except Exception as exc:
        typer.echo(f"Error loading or validating issues file: {exc}", err=True)
        raise typer.Exit(1) from exc

    # Parse labels string into a list
    label_list: list[str] = [label.strip() for label in labels.split(",") if label.strip()] if labels else []

    # 3. Add an issue for each new file
    added_issues: list[IssueModel] = []
    for file_path in new_files:
        pr_title = f"Add file: {file_path}"
        issue_title = f"Track new file: {file_path}"
        pr_model = PullRequestModel(
            title=pr_title,
            files=[file_path],
            labels=label_list if label_list else None,
        )
        issue_model = IssueModel(
            title=issue_title,
            body=f"This issue tracks the addition of `{file_path}`.",
            labels=label_list if label_list else None,
            pull_request=pr_model,
        )
        issues_model.issues.append(issue_model)
        added_issues.append(issue_model)

    # 4. Write the updated issues file
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.explicit_start = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    try:
        with open(issues_file, "w", encoding="utf-8") as f:
            yaml.dump(issues_model.model_dump(mode="python", exclude_none=True, exclude_defaults=True), f)
    except Exception as exc:
        typer.echo(f"Error writing updated issues file: {exc}", err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"Added {len(added_issues)} issues (with PRs) to {issues_file}.")
    if added_issues:
        typer.echo("First added issue:")
        typer.echo(str(added_issues[0].model_dump()))


if __name__ == "__main__":
    typer_app()
