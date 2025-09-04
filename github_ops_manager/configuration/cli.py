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

from github_ops_manager.configuration.models import GitHubAuthenticationType
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
    template = construct_jinja2_template_from_file(Path("github_ops_manager/templates/tac_issues_body.j2"))

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
) -> None:
    """Processes issues in a GitHub repository."""
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
        )
    )
    if result.errors:
        typer.echo("Error(s) encountered while processing YAML:", err=True)
        for err in result.errors:
            typer.echo(str(err), err=True)
        sys.exit(1)


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


# --- Team Management Command ---
@typer_app.command(name="add-users-to-team")
def add_users_to_team_cli(
    usernames_file: Annotated[Path, Argument(help="Path to text file containing GitHub usernames (one per line).")],
    org_name: Annotated[str, Option("--org-name", help="GitHub organization name.")],
    team_name: Annotated[str, Option("--team-name", help="GitHub team name (slug).")],
    github_api_url: Annotated[str, Option(envvar="GITHUB_API_URL", help="GitHub API URL.")] = "https://api.github.com",
    github_pat_token: Annotated[str | None, Option(envvar="GITHUB_PAT_TOKEN", help="GitHub Personal Access Token.")] = None,
    github_app_id: Annotated[int | None, Option(envvar="GITHUB_APP_ID", help="GitHub App ID.")] = None,
    github_app_private_key_path: Annotated[Path | None, Option(envvar="GITHUB_APP_PRIVATE_KEY_PATH", help="Path to GitHub App private key.")] = None,
    github_app_installation_id: Annotated[int | None, Option(envvar="GITHUB_APP_INSTALLATION_ID", help="GitHub App Installation ID.")] = None,
    missing_users_file: Annotated[Path, Option("--missing-users-file", help="Path to save missing users file.")] = Path("missing_users.txt"),
    debug: Annotated[bool, Option(envvar="DEBUG", help="Enable debug mode.")] = False,
) -> None:
    """Add users to a GitHub team by reading usernames from a file.

    Reads GitHub usernames from a text file (one per line) and attempts to add each
    user to the specified team. Users that cannot be found on GitHub will be saved
    to a missing_users.txt file in the current directory.
    """
    if not usernames_file.exists():
        typer.echo(f"Error: Usernames file not found: {usernames_file}", err=True)
        raise typer.Exit(1)

    # Validate GitHub authentication configuration
    github_auth_type = asyncio.run(
        validate_github_authentication_configuration(
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
        )
    )

    # Run the team management workflow
    result = asyncio.run(
        run_add_users_to_team_workflow(
            usernames_file=usernames_file,
            org_name=org_name,
            team_name=team_name,
            github_auth_type=github_auth_type,
            github_pat_token=github_pat_token,
            github_app_id=github_app_id,
            github_app_private_key_path=github_app_private_key_path,
            github_app_installation_id=github_app_installation_id,
            github_api_url=github_api_url,
            missing_users_file=missing_users_file,
            debug=debug,
        )
    )

    typer.echo("Team management completed!")
    typer.echo(f"✅ Successfully added {result['added_count']} users to team {org_name}/{team_name}")
    if result["missing_count"] > 0:
        typer.echo(f"⚠️  {result['missing_count']} users could not be found and were saved to {missing_users_file}")
    if result["already_member_count"] > 0:
        typer.echo(f"ℹ️  {result['already_member_count']} users were already team members")
    if result["error_count"] > 0:
        typer.echo(f"❌ {result['error_count']} errors occurred during processing")


async def run_add_users_to_team_workflow(
    usernames_file: Path,
    org_name: str,
    team_name: str,
    github_auth_type: GitHubAuthenticationType,
    github_pat_token: str | None,
    github_app_id: int | None,
    github_app_private_key_path: Path | None,
    github_app_installation_id: int | None,
    github_api_url: str,
    missing_users_file: Path,
    debug: bool = False,
) -> dict[str, int]:
    """Core workflow for adding users to a GitHub team.

    Returns:
        Dictionary with counts of added, missing, already_member, and error users
    """
    # Create GitHub adapter (we'll use a dummy repo since we need auth)
    adapter = await GitHubKitAdapter.create(
        repo=f"{org_name}/dummy-repo",  # This is a hack since we need auth but not repo-specific
        github_auth_type=github_auth_type,
        github_pat_token=github_pat_token,
        github_app_id=github_app_id,
        github_app_private_key_path=github_app_private_key_path,
        github_app_installation_id=github_app_installation_id,
        github_api_url=github_api_url,
    )

    # Verify team exists
    team = await adapter.get_team(org_name, team_name)
    if not team:
        typer.echo(f"Error: Team '{team_name}' not found in organization '{org_name}'", err=True)
        raise typer.Exit(1)

    typer.echo(f"Found team: {team.name} (ID: {team.id}) in {org_name}")

    # Read usernames from file
    try:
        with open(usernames_file) as f:
            usernames = [line.strip() for line in f if line.strip()]
    except Exception as e:
        typer.echo(f"Error reading usernames file: {e}", err=True)
        raise typer.Exit(1) from e

    typer.echo(f"Found {len(usernames)} usernames to process")

    # Process each username
    added_count = 0
    missing_count = 0
    already_member_count = 0
    error_count = 0
    missing_users: list[str] = []

    for username in usernames:
        try:
            typer.echo(f"Processing: {username}")

            # Check if user exists
            user = await adapter.get_user_by_username(username)

            if not user:
                typer.echo(f"  ❌ GitHub user not found: {username}")
                missing_users.append(username)
                missing_count += 1
                continue

            typer.echo(f"  ✅ Found GitHub user: {username}")

            # Check if already a team member
            is_member = await adapter.check_team_membership(org_name, team_name, username)
            if is_member:
                typer.echo(f"  ℹ️  User {username} is already a team member")
                already_member_count += 1
                continue

            # Add user to team
            success = await adapter.add_user_to_team(org_name, team_name, username)
            if success:
                typer.echo(f"  ✅ Successfully added {username} to team")
                added_count += 1
            else:
                typer.echo(f"  ❌ Failed to add {username} to team")
                error_count += 1

        except Exception as e:
            typer.echo(f"  ❌ Error processing {username}: {e}")
            error_count += 1
            if debug:
                traceback.print_exc()

    # Write missing users to file
    if missing_users:
        try:
            with open(missing_users_file, "w") as f:
                for username in missing_users:
                    f.write(f"{username}\n")
            typer.echo(f"Missing users saved to: {missing_users_file}")
        except Exception as e:
            typer.echo(f"Error writing missing users file: {e}", err=True)

    return {
        "added_count": added_count,
        "missing_count": missing_count,
        "already_member_count": already_member_count,
        "error_count": error_count,
    }


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


if __name__ == "__main__":
    typer_app()
