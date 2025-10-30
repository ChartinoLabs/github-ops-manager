"""Defines the Command Line Interface (CLI) using Typer."""

import asyncio
import os
import subprocess
import sys
import traceback
from pathlib import Path

import typer
from dotenv import load_dotenv
from typer import Argument, Option
from typing_extensions import Annotated

from github_ops_manager.configuration.reconcile import validate_github_authentication_configuration
from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.yaml_processor import YAMLProcessor
from github_ops_manager.schemas.default_issue import IssueModel, IssuesYAMLModel, PullRequestModel
from github_ops_manager.synchronize.driver import run_process_issues_workflow
from github_ops_manager.utils.tac import find_issue_with_title
from github_ops_manager.utils.templates import construct_jinja2_template_from_file, render_template_with_model
from github_ops_manager.utils.yaml import dump_yaml_to_file, load_test_case_definitions_from_directory, load_yaml_file

load_dotenv()

typer_app = typer.Typer(pretty_exceptions_show_locals=False)


# Command(s) that are specific to the Testing as Code methodology
@typer_app.command(name="tac-sync-issues")
def tac_sync_issues_cli(
    ctx: typer.Context,
    yaml_path: Annotated[Path, Argument(envvar="YAML_PATH", help="Path to YAML file for issues.")],
    testing_as_code_test_case_definitions: Annotated[
        Path,
        Argument(
            envvar="TESTING_AS_CODE_TEST_CASE_DEFINITIONS", help="Path to directory containing Testing as Code test case definitions YAML files."
        ),
    ],
    test_automation_scripts_directory: Annotated[
        Path, Argument(envvar="TEST_AUTOMATION_SCRIPTS_DIRECTORY", help="Path to directory containing test automation scripts.")
    ],
) -> None:
    """Sync issues in a GitHub repository using the Testing as Code methodology."""
    # Load TAC test case definition data model from directory and
    # validate all files are syntactically correct.
    if not testing_as_code_test_case_definitions.exists():
        error = f"Testing as Code test case definitions directory not found: {testing_as_code_test_case_definitions.absolute()}"
        typer.echo(error, err=True)
        raise FileNotFoundError(error)

    if not testing_as_code_test_case_definitions.is_dir():
        error = f"Testing as Code test case definitions path is not a directory: {testing_as_code_test_case_definitions.absolute()}"
        typer.echo(error, err=True)
        raise ValueError(error)

    typer.echo(f"Loading Testing as Code test case definitions from directory {testing_as_code_test_case_definitions.absolute()}")

    try:
        testing_as_code_test_case_definitions_model = load_test_case_definitions_from_directory(testing_as_code_test_case_definitions)
        typer.echo(f"Loaded {len(testing_as_code_test_case_definitions_model.test_cases)} test case definitions from directory")
    except ValueError as e:
        typer.echo(f"Error loading test case definitions: {str(e)}", err=True)
        raise e

    # Load the YAML file and validate it.
    if not yaml_path.exists():
        error = f"YAML file not found: {yaml_path.absolute()}"
        typer.echo(error, err=True)
        raise FileNotFoundError(error)
    typer.echo(f"Loading issues from {yaml_path.absolute()}")
    desired_issues_yaml_content = load_yaml_file(yaml_path)
    desired_issues_yaml_model = IssuesYAMLModel.model_validate(desired_issues_yaml_content)
    typer.echo(f"Loaded {len(desired_issues_yaml_model.issues)} issues")

    # Ensure that the issue body Jinja2 template for Testing as Code issues
    # can be constructed.
    template = construct_jinja2_template_from_file(Path(__file__).parent.parent / "templates" / "tac_issues_body.j2")

    # Iterate through the test case definitions and ensure matching issues
    # exist in the YAML file.
    for test_case_definition in testing_as_code_test_case_definitions_model.test_cases:
        typer.echo(f"Processing test case definition with a title of '{test_case_definition.title}'")
        existing_issue = find_issue_with_title(desired_issues_yaml_model, test_case_definition.title)
        if existing_issue is None:
            typer.echo(f"No existing issue found for test case definition with a title of '{test_case_definition.title}' - adding one now")
            # Create a new issue based upon the test case definition. The test
            # case definition could be in one of two states that our issue
            # creation logic needs to handle:
            #
            # 1. The test case definition has not yet resulted in a new test
            #    automation script (which means no Pull Request is needed).
            # 2. The test case definition has already been reviewed and has
            #    resulted in the creation of a new test automation script
            #    (which means a Pull Request is needed).
            #
            # The way we differentiate between the two states is through the
            # control labels associated with the test case definition. A test
            # case definition that has resulted in a created test automation
            # script will have a control label called "script-already-created".
            # Additionally, a field named "generated_script_path" will be
            # populated with the path to the created test automation script.
            new_issue = IssueModel(
                title=test_case_definition.title,
                body=render_template_with_model(
                    model=test_case_definition,
                    template=template,
                ),
                labels=test_case_definition.labels,
            )
            # Check if we need to create a Pull Request for this issue.
            if test_case_definition.generated_script_path is not None:
                typer.echo(
                    "Test case definition with a title of "
                    f"'{test_case_definition.title}' has a generated script "
                    f"path of '{test_case_definition.generated_script_path}' - "
                    "creating a Pull Request"
                )
                new_issue.pull_request = PullRequestModel(
                    title=f"GenAI, Review: {test_case_definition.title}",
                    files=[test_case_definition.generated_script_path],
                )
            desired_issues_yaml_model.issues.append(new_issue)
        else:
            # Update the existing issue based upon the test case definition.
            existing_issue.body = render_template_with_model(
                model=test_case_definition,
                template=template,
            )
            existing_issue.labels = test_case_definition.labels
            if test_case_definition.generated_script_path is not None:
                if existing_issue.pull_request is None:
                    typer.echo(
                        f"Test case definition with a title of '{test_case_definition.title}' "
                        "has a generated script path of "
                        f"'{test_case_definition.generated_script_path}' - "
                        "but no Pull Request exists - creating one now"
                    )
                else:
                    typer.echo(
                        f"Test case definition with a title of '{test_case_definition.title}' "
                        "has a generated script path of "
                        f"'{test_case_definition.generated_script_path}' - "
                        "but a Pull Request already exists - updating the Pull Request"
                    )
                # generated_script_path is a relative path from the relative
                # path of the test automation scripts directory.
                script_path = test_automation_scripts_directory / test_case_definition.generated_script_path
                existing_issue.pull_request = PullRequestModel(
                    title=f"GenAI, Review: {test_case_definition.title}",
                    files=[str(script_path)],
                )
            else:
                existing_issue.pull_request = None

    typer.echo(f"Updated desired issues YAML model to have a total of {len(desired_issues_yaml_model.issues)} issues")

    # Write the updated YAML file to disk.
    dump_yaml_to_file(desired_issues_yaml_model.model_dump(mode="python", exclude_none=True, exclude_defaults=True), yaml_path)
    typer.echo(f"Successfully updated issues YAML model and saved to {yaml_path}")


# --- Add a new Typer group for repo commands ---
repo_app = typer.Typer(help="Repository-related commands")


def repo_callback(
    ctx: typer.Context,
    repo: Annotated[str, Argument(help="Repository name (owner/repo).")],
    github_api_url: Annotated[str, Option(envvar="GITHUB_API_URL", help="GitHub API URL.")] = "https://api.github.com",
    github_pat_token: Annotated[str | None, Option(envvar="GITHUB_PAT_TOKEN", help="GitHub Personal Access Token.")] = None,
    github_app_id: Annotated[int | None, Option(envvar="GITHUB_APP_ID", help="GitHub App ID.")] = None,
    github_app_private_key_path: Annotated[Path | None, Option(envvar="GITHUB_APP_PRIVATE_KEY_PATH", help="Path to GitHub App private key.")] = None,
    github_app_installation_id: Annotated[int | None, Option(envvar="GITHUB_APP_INSTALLATION_ID", help="GitHub App Installation ID.")] = None,
) -> None:
    """Set the repository for the current context."""
    ctx.ensure_object(dict)
    ctx.obj["repo"] = repo
    ctx.obj["github_api_url"] = github_api_url
    ctx.obj["github_pat_token"] = github_pat_token
    ctx.obj["github_app_id"] = github_app_id
    ctx.obj["github_app_private_key_path"] = github_app_private_key_path
    ctx.obj["github_app_installation_id"] = github_app_installation_id
    # Validate GitHub authentication configuration
    github_auth_type = asyncio.run(
        validate_github_authentication_configuration(
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
        )
    )
    ctx.obj["github_auth_type"] = github_auth_type


repo_app.callback()(repo_callback)


# --- Move process-issues under repo_app ---
@repo_app.command(name="process-issues")
def process_issues_cli(
    ctx: typer.Context,
    yaml_path: Annotated[Path, Argument(envvar="YAML_PATH", help="Path to YAML file for issues.")],
    create_prs: Annotated[bool, Option(envvar="CREATE_PRS", help="Create PRs for issues.")] = False,
    debug: Annotated[bool, Option(envvar="DEBUG", help="Enable debug mode.")] = False,
    testing_as_code_workflow: Annotated[bool, Option(envvar="TESTING_AS_CODE_WORKFLOW", help="Enable Testing as Code workflow.")] = False,
    catalog_repo: Annotated[
        str,
        Option(
            envvar="CATALOG_REPO",
            help="Catalog repository name (owner/repo) for catalog-destined test cases. Used when test cases have catalog_destined=true.",
        ),
    ] = "Testing-as-Code/tac-catalog",
    test_cases_dir: Annotated[
        Path,
        Option(
            envvar="TEST_CASES_DIR",
            help="Directory containing test_cases.yaml files for catalog PR metadata writeback. Used when test cases have catalog_destined=true.",
        ),
    ] = Path("workspace/test_cases/"),
) -> None:
    """Processes issues in a GitHub repository.

    Automatically detects catalog-destined test cases (catalog_destined=true) and creates
    PRs against the catalog repository with proper directory structure and metadata writeback.
    Non-catalog test cases are processed normally against the project repository.
    """
    repo: str = ctx.obj["repo"]
    github_api_url: str = ctx.obj["github_api_url"]
    github_pat_token: str = ctx.obj["github_pat_token"]
    github_app_id: int = ctx.obj["github_app_id"]
    github_app_private_key_path: Path | None = ctx.obj["github_app_private_key_path"]
    github_app_installation_id: int = ctx.obj["github_app_installation_id"]
    github_auth_type = ctx.obj["github_auth_type"]

    if testing_as_code_workflow is True:
        typer.echo("Testing as Code workflow is enabled - any Pull Requests created will have an augmented body")

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
            testing_as_code_workflow=testing_as_code_workflow,
            catalog_repo=catalog_repo,
            test_cases_dir=test_cases_dir,
        )
    )
    if result.errors:
        typer.echo("Error(s) encountered while processing YAML:", err=True)
        for err in result.errors:
            typer.echo(str(err), err=True)
        sys.exit(1)


@repo_app.command(name="process-test-cases")
def process_test_cases_cli(
    ctx: typer.Context,
    test_cases_dir: Annotated[Path, Argument(help="Directory containing test_cases.yaml files.")],
    catalog_repo: Annotated[
        str,
        Option(
            envvar="CATALOG_REPO",
            help="Catalog repository name (owner/repo) for catalog-destined test cases.",
        ),
    ] = "Testing-as-Code/tac-catalog",
) -> None:
    """Process test cases using embedded metadata (no issues.yaml required).

    This command reads test_cases.yaml files directly and uses embedded metadata
    (project_issue_number, project_pr_number, etc.) to sync issues and PRs with GitHub.

    Benefits over process-issues:
    - No separate issues.yaml file needed
    - Fast direct ID lookups instead of title matching
    - Automatic metadata writeback to test_cases.yaml
    - Single source of truth for all test case information

    For test cases with catalog_destined=true, PRs are created against the catalog repository.
    """
    from github_ops_manager.synchronize.driver import run_process_test_cases_workflow

    repo: str = ctx.obj["repo"]
    github_api_url: str = ctx.obj["github_api_url"]
    github_pat_token: str = ctx.obj["github_pat_token"]
    github_app_id: int = ctx.obj["github_app_id"]
    github_app_private_key_path: Path | None = ctx.obj["github_app_private_key_path"]
    github_app_installation_id: int = ctx.obj["github_app_installation_id"]
    github_auth_type = ctx.obj["github_auth_type"]

    if not test_cases_dir.exists():
        typer.echo(f"Error: test_cases directory not found at {test_cases_dir}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Processing test cases from {test_cases_dir}")
    typer.echo(f"Repository: {repo}")
    typer.echo(f"Catalog repository: {catalog_repo}")
    typer.echo("")

    # Run the workflow
    stats = asyncio.run(
        run_process_test_cases_workflow(
            repo=repo,
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
            github_auth_type=github_auth_type,
            github_api_url=github_api_url,
            test_cases_dir=test_cases_dir,
            catalog_repo=catalog_repo,
        )
    )

    # Display results
    typer.echo("")
    typer.echo("=" * 70)
    typer.echo("WORKFLOW SUMMARY")
    typer.echo("=" * 70)

    if "issues" in stats:
        issue_stats = stats["issues"]
        typer.echo("Issues:")
        typer.echo(f"  Test cases processed: {issue_stats['test_cases_processed']}")
        typer.echo(f"  Issues created: {issue_stats['issues_created']}")
        typer.echo(f"  Issues updated: {issue_stats['issues_updated']}")
        typer.echo(f"  Issues unchanged: {issue_stats['issues_unchanged']}")
        if issue_stats["errors"]:
            typer.echo(f"  Errors: {len(issue_stats['errors'])}")
        typer.echo("")

    if "pull_requests" in stats:
        pr_stats = stats["pull_requests"]
        typer.echo("Pull Requests:")
        typer.echo(f"  Test cases processed: {pr_stats['test_cases_processed']}")
        typer.echo(f"  PRs created: {pr_stats['prs_created']}")
        typer.echo(f"  PRs updated: {pr_stats['prs_updated']}")
        typer.echo(f"  PRs unchanged: {pr_stats['prs_unchanged']}")
        typer.echo(f"  PRs skipped: {pr_stats['prs_skipped']}")
        if pr_stats["errors"]:
            typer.echo(f"  Errors: {len(pr_stats['errors'])}")
        typer.echo("")

    typer.echo("=" * 70)
    typer.echo("")
    typer.echo("✅ Workflow completed successfully!")


# --- Move export-issues under repo_app ---
@repo_app.command(name="export-issues")
def export_issues_cli(
    ctx: typer.Context,
    output_file: Annotated[Path | None, Option(envvar="OUTPUT_FILE", help="Path to save exported issues.")] = None,
    state: Annotated[str | None, Option(envvar="STATE", help="Filter issues by state (open, closed, all). ")] = None,
    label: Annotated[str | None, Option(envvar="LABEL", help="Filter issues by label.")] = None,
    debug: Annotated[bool, Option(envvar="DEBUG", help="Enable debug mode.")] = False,
) -> None:
    """Exports issues from a GitHub repository."""
    repo: str = ctx.obj["repo"]
    # github_api_url: str = ctx.obj["github_api_url"]
    github_pat_token: str = ctx.obj["github_pat_token"]
    github_app_id: int = ctx.obj["github_app_id"]
    github_app_private_key_path: Path | None = ctx.obj["github_app_private_key_path"]
    github_app_installation_id: int = ctx.obj["github_app_installation_id"]
    # github_auth_type = ctx.obj["github_auth_type"]
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
    file_paths: Annotated[list[str], Argument(help="One or more file paths to fetch from the repository (relative to repo root).")],
    branch: Annotated[str | None, Option("--branch", help="Branch, tag, or commit SHA to fetch from. Defaults to the default branch.")] = None,
    debug: Annotated[bool, Option(envvar="DEBUG", help="Enable debug mode.")] = False,
) -> None:
    """Fetch one or more files from the repository and download them locally at the same relative path."""
    repo: str = ctx.obj["repo"]
    github_api_url: str = ctx.obj["github_api_url"]
    github_pat_token: str = ctx.obj["github_pat_token"]
    github_app_id: int = ctx.obj["github_app_id"]
    github_app_private_key_path: Path | None = ctx.obj["github_app_private_key_path"]
    github_app_installation_id: int = ctx.obj["github_app_installation_id"]
    github_auth_type = ctx.obj["github_auth_type"]
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
    issues_file: Annotated[Path, Argument(help="Path to the issues YAML file.")],
    labels: Annotated[str, Option("--labels", help="Comma-separated labels to assign to each created issue and pull request.")] = "",
) -> None:
    """Detect new files in the current git repo and add issues/PRs for each to the issues file."""
    # Change to the parent directory of the issues file
    typer.echo(f"Changing directory to {issues_file.parent.absolute()}")
    os.chdir(issues_file.parent)
    # 1. Find new (untracked) .py and .robot files
    cmd = ["git", "ls-files", "--others", "--exclude-standard", "*.py", "*.robot"]
    typer.echo(f"Running command: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        new_files: list[str] = [f for f in result.stdout.splitlines() if f.strip()]
    except Exception as exc:
        typer.echo(f"Error running git to find new files: {exc}", err=True)
        raise typer.Exit(1) from exc

    if not new_files:
        typer.echo("No new (untracked) files found.")
        return

    typer.echo(f"{len(new_files)} new files found")
    for file in new_files:
        typer.echo(f"  - {file}")

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
    try:
        dump_yaml_to_file(issues_model.model_dump(mode="python", exclude_none=True, exclude_defaults=True), issues_file)
    except Exception as exc:
        typer.echo(f"Error writing updated issues file: {exc}", err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"Added {len(added_issues)} issues (with PRs) to {issues_file}.")
    if added_issues:
        typer.echo("First added issue:")
        typer.echo(str(added_issues[0].model_dump()))


@typer_app.command(name="migrate-issues-to-metadata")
def migrate_issues_to_metadata_cli(
    ctx: typer.Context,
    repo: Annotated[str, Argument(help="Repository name (owner/repo).")],
    issues_yaml_path: Annotated[Path, Argument(help="Path to issues.yaml file.")],
    test_cases_dir: Annotated[Path, Argument(help="Directory containing test_cases.yaml files.")],
    github_api_url: Annotated[str, Option(envvar="GITHUB_API_URL", help="GitHub API URL.")] = "https://api.github.com",
    github_pat_token: Annotated[str | None, Option(envvar="GITHUB_PAT_TOKEN", help="GitHub Personal Access Token.")] = None,
    github_app_id: Annotated[int | None, Option(envvar="GITHUB_APP_ID", help="GitHub App ID.")] = None,
    github_app_private_key_path: Annotated[Path | None, Option(envvar="GITHUB_APP_PRIVATE_KEY_PATH", help="Path to GitHub App private key.")] = None,
    github_app_installation_id: Annotated[int | None, Option(envvar="GITHUB_APP_INSTALLATION_ID", help="GitHub App Installation ID.")] = None,
) -> None:
    """Migrate issue/PR metadata from issues.yaml to test_cases.yaml files.

    This command reads an existing issues.yaml file, finds corresponding GitHub issues
    and PRs, locates matching test cases in test_cases.yaml files, and embeds the
    issue/PR metadata directly into the test case definitions.

    After migration, issues.yaml can be safely deleted as all tracking information
    will be embedded in test_cases.yaml files.
    """
    from github_ops_manager.migrate.issues_to_metadata import migrate_issues_to_metadata

    # Validate inputs
    if not issues_yaml_path.exists():
        typer.echo(f"Error: issues.yaml not found at {issues_yaml_path}", err=True)
        raise typer.Exit(1)

    if not test_cases_dir.exists():
        typer.echo(f"Error: test_cases directory not found at {test_cases_dir}", err=True)
        raise typer.Exit(1)

    # Validate GitHub authentication
    github_auth_type = asyncio.run(
        validate_github_authentication_configuration(
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
        )
    )

    typer.echo(f"Migrating issues from {issues_yaml_path} to test_cases.yaml files in {test_cases_dir}")
    typer.echo(f"Repository: {repo}")
    typer.echo("")

    async def run_migration() -> None:
        # Create GitHub adapter
        adapter = await GitHubKitAdapter.create(
            repo=repo,
            github_auth_type=github_auth_type,
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
            github_api_url=github_api_url,
        )

        # Run migration
        stats = await migrate_issues_to_metadata(
            issues_yaml_path=issues_yaml_path,
            test_cases_dir=test_cases_dir,
            github_adapter=adapter,
            github_api_url=github_api_url,
        )

        # Display results
        typer.echo("")
        typer.echo("=" * 70)
        typer.echo("MIGRATION SUMMARY")
        typer.echo("=" * 70)
        typer.echo(f"Issues processed from issues.yaml: {stats['issues_processed']}")
        typer.echo(f"Test cases updated: {stats['test_cases_updated']}")
        typer.echo("")

        if stats["issues_without_github_issue"]:
            typer.echo(f"⚠️  Issues in issues.yaml not found on GitHub: {len(stats['issues_without_github_issue'])}")
            for title in stats["issues_without_github_issue"]:
                typer.echo(f"  - {title}")
            typer.echo("")

        if stats["issues_without_test_case"]:
            typer.echo(f"⚠️  Issues without matching test case: {len(stats['issues_without_test_case'])}")
            for title in stats["issues_without_test_case"]:
                typer.echo(f"  - {title}")
            typer.echo("")

        if stats["orphaned_test_cases"]:
            typer.echo(f"📋 Test cases without project issues/PRs: {len(stats['orphaned_test_cases'])}")
            for title in stats["orphaned_test_cases"]:
                typer.echo(f"  - {title}")
            typer.echo("")

        typer.echo("=" * 70)
        typer.echo("")

        if stats["test_cases_updated"] > 0:
            typer.echo("✅ Migration completed successfully!")
            typer.echo("")
            typer.echo("Next steps:")
            typer.echo("  1. Review the updated test_cases.yaml files")
            typer.echo("  2. Test the 'process-issues' command without issues.yaml")
            typer.echo(f"  3. Once verified, you can safely delete {issues_yaml_path}")
        else:
            typer.echo("⚠️  No test cases were updated. Please review the warnings above.")

    asyncio.run(run_migration())


if __name__ == "__main__":
    typer_app()
