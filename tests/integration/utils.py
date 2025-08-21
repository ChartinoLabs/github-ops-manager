"""Utility functions for integration tests."""

import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable

from githubkit.versions.latest.models import Issue

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.utils.yaml import dump_yaml_to_file


def get_cli_script_path() -> str:
    """Get the path to the github-ops-manager CLI script.

    Returns:
        str: The absolute path to the CLI script.

    Raises:
        FileNotFoundError: If the CLI script cannot be found.
    """
    # Start from the current file's location and go up to the project root
    cli_script = str(Path(__file__).parent.parent.parent / "github-ops-manager")
    if not os.path.exists(cli_script):
        raise FileNotFoundError(f"CLI script not found at {cli_script}")

    # Ensure the script is executable
    os.chmod(cli_script, 0o755)

    return cli_script


def get_cli_with_starting_args() -> list[str]:
    """Get the CLI script path with the starting arguments for the new CLI structure."""
    repo: str | None = os.getenv("REPO")
    if repo is None:
        raise ValueError("REPO environment variable not set")
    base_cli: str = get_cli_script_path()
    return [base_cli, "repo", repo]


def generate_unique_issue_title(prefix: str = "IntegrationTest") -> str:
    """Generate a unique issue title for integration tests."""
    return f"{prefix}-{uuid.uuid4()}"


def _extract_label_names(issue: Issue) -> set[str]:
    """Extract label names from a GitHub Issue object, handling different possible models."""
    labels = getattr(issue, "labels", [])
    names = set()
    for label in labels:
        # If label is a string
        if isinstance(label, str):
            names.add(label)
        # If label is a dict or has a 'name' attribute
        elif hasattr(label, "name"):
            names.add(label.name)
        elif isinstance(label, dict) and "name" in label:
            names.add(label["name"])
    return names


def _write_yaml_issues_file(issues: list[dict], suffix: str = ".yaml") -> str:
    """Write issues to a temporary YAML file and return the file path."""
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as tmp_yaml:
        temp_path = Path(tmp_yaml.name)

    dump_yaml_to_file({"issues": issues}, temp_path)
    return str(temp_path)


async def _wait_for_issues_on_github(
    adapter: GitHubKitAdapter,
    titles: list[str],
    max_attempts: int = 25,
    sleep_seconds: int = 15,
    predicate: Callable[[list[Issue]], bool] | None = None,
) -> list[Issue]:
    """Wait for all issues with the given titles to appear on GitHub."""
    for attempt in range(max_attempts):
        print(f"\n[{attempt + 1}/{max_attempts}] Fetching issues from GitHub...")
        issues = await adapter.list_issues(state="all")
        found_titles = [issue.title for issue in issues]
        print(f"[{attempt + 1}/{max_attempts}] Looking for issues titled {titles} amongst {len(issues)} issues in repository:")
        for issue in issues:
            print(f"  - {issue.number}: {issue.title} (created_at: {getattr(issue, 'created_at', 'N/A')})")
        if all(title in found_titles for title in titles):
            print(f"Found all issues with titles {titles}!")
            found_issues = [issue for issue in issues if issue.title in titles]
            if predicate is None:
                return found_issues
            if predicate(found_issues):
                return found_issues
            else:
                print("All issues found, but predicate returned False")
        print(f"[{attempt + 1}/{max_attempts}] Not all issues found or passing predicate, waiting {sleep_seconds} seconds and trying again...")
        time.sleep(sleep_seconds)
    return await adapter.list_issues(state="all")


async def _close_issues_by_title(adapter: GitHubKitAdapter, titles: list[str]) -> None:
    """Close all issues with the given titles."""
    existing = await adapter.list_issues(state="all")
    for issue in existing:
        if issue.title in titles:
            print(f"\nClosing issue {issue.number}: {issue.title}")
            await adapter.close_issue(issue.number)


def get_github_adapter() -> GitHubKitAdapter:
    """Initialize and return a GitHubKitAdapter using environment variables for token and repo."""
    import pytest  # Local import to avoid unnecessary dependency for non-test usage
    from githubkit import GitHub

    token: str | None = os.environ.get("GITHUB_PAT_TOKEN")
    if not token:
        pytest.fail("GITHUB_PAT_TOKEN not set in environment")
    repo_slug: str = os.environ["REPO"]
    owner, repo = repo_slug.split("/")
    client = GitHub(token)
    return GitHubKitAdapter(client, owner, repo)


def run_process_issues_cli(yaml_path: str) -> subprocess.CompletedProcess[str]:
    """Run the process-issues CLI command with the given YAML file."""
    cli_with_starting_args: list[str] = get_cli_with_starting_args()
    cli_command: list[str] = cli_with_starting_args + ["process-issues", yaml_path]
    result: subprocess.CompletedProcess[str] = subprocess.run(
        cli_command,
        capture_output=True,
        text=True,
        check=True,
        env=os.environ.copy(),
    )
    print("\nCLI STDOUT:\n", result.stdout)
    print("\nCLI STDERR:\n", result.stderr)
    return result
