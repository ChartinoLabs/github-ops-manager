"""Integration tests for the GitHub sync."""

import asyncio
import os
import subprocess
import tempfile
import time
import uuid
from typing import Callable

import pytest
import yaml
from githubkit import GitHub
from githubkit.versions.latest.models import Issue

from github_ops_manager.github.adapter import GitHubKitAdapter

from .utils import generate_unique_issue_title, get_cli_with_starting_args


def _write_yaml_issues_file(issues: list[dict], suffix: str = ".yaml") -> str:
    """Write issues to a temporary YAML file and return the file path."""
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as tmp_yaml:
        yaml.dump({"issues": issues}, tmp_yaml)
        return tmp_yaml.name


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_github_issue_sync_cli_single_issue() -> None:
    """Test the GitHub Ops Manager ability to process a single issue via the CLI."""
    token: str | None = os.environ.get("GITHUB_PAT_TOKEN")
    if not token:
        pytest.fail("GITHUB_PAT_TOKEN not set in environment")
    repo_slug = os.environ["REPO"]
    owner, repo = repo_slug.split("/")
    client = GitHub(token)
    adapter = GitHubKitAdapter(client, owner, repo)
    unique_title = generate_unique_issue_title()
    yaml_issues = [
        {
            "title": unique_title,
            "body": "Integration test body",
            "labels": ["bug"],
            "assignees": [],
            "milestone": None,
        }
    ]
    # Assert that the issue does not exist
    existing = await adapter.list_issues(state="all")
    assert not any(issue.title == unique_title for issue in existing)
    tmp_yaml_path = _write_yaml_issues_file(yaml_issues)
    try:
        cli_with_starting_args = get_cli_with_starting_args()
        cli_command = cli_with_starting_args + ["process-issues", tmp_yaml_path]
        result = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )
        assert result.returncode == 0
        assert "Issue not found in GitHub" in result.stdout
        # Wait for the issue to appear
        issues = await _wait_for_issues_on_github(adapter, [unique_title])
        assert any(issue.title == unique_title for issue in issues), f"Issue {unique_title} not found in GitHub"
        # Run the CLI again (should be NOOP)
        result2 = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )
        assert result2.returncode == 0
        assert "No changes needed" in result2.stdout or "up to date" in result2.stdout.lower()
        # Clean up: close the created issue
        await _close_issues_by_title(adapter, [unique_title])
    except subprocess.CalledProcessError as e:
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        raise
    finally:
        os.remove(tmp_yaml_path)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_github_issue_sync_cli_multiple_issues() -> None:
    """Test the GitHub Ops Manager ability to process multiple issues via the CLI."""
    token: str | None = os.environ.get("GITHUB_PAT_TOKEN")
    if not token:
        pytest.fail("GITHUB_PAT_TOKEN not set in environment")
    repo_slug = os.environ["REPO"]
    owner, repo = repo_slug.split("/")
    client = GitHub(token)
    adapter = GitHubKitAdapter(client, owner, repo)
    unique_titles = [generate_unique_issue_title(f"IntegrationTestMulti{i + 1}") for i in range(3)]
    yaml_issues = [
        {
            "title": title,
            "body": f"Integration test body for {title}",
            "labels": ["bug"],
            "assignees": [],
            "milestone": None,
        }
        for title in unique_titles
    ]
    # Assert that the issues do not exist
    existing = await adapter.list_issues(state="all")
    for title in unique_titles:
        assert not any(issue.title == title for issue in existing)
    tmp_yaml_path = _write_yaml_issues_file(yaml_issues)
    try:
        cli_with_starting_args = get_cli_with_starting_args()
        cli_command = cli_with_starting_args + ["process-issues", tmp_yaml_path]
        result = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )
        assert result.returncode == 0
        for title in unique_titles:
            assert "Issue not found in GitHub" in result.stdout or title in result.stdout
        # Wait for all issues to appear
        issues = await _wait_for_issues_on_github(adapter, unique_titles)
        for title in unique_titles:
            assert any(issue.title == title for issue in issues), f"Issue {title} not found in GitHub"
        # Run the CLI again (should be NOOP)
        result2 = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )
        assert result2.returncode == 0
        assert "No changes needed" in result2.stdout or "up to date" in result2.stdout.lower()
        # Clean up: close the created issues
        await _close_issues_by_title(adapter, unique_titles)
    except subprocess.CalledProcessError as e:
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        raise
    finally:
        os.remove(tmp_yaml_path)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_github_issue_update_body() -> None:
    """Test creating a single issue, then updating its body."""
    token: str | None = os.environ.get("GITHUB_PAT_TOKEN")
    if not token:
        pytest.fail("GITHUB_PAT_TOKEN not set in environment")
    repo_slug = os.environ["REPO"]
    owner, repo = repo_slug.split("/")
    client = GitHub(token)
    adapter = GitHubKitAdapter(client, owner, repo)
    unique_title = generate_unique_issue_title("IntegrationTestUpdate")
    initial_body = "Initial body for update test"
    updated_body = "Updated body for update test"
    yaml_issues = [
        {
            "title": unique_title,
            "body": initial_body,
            "labels": ["bug"],
            "assignees": [],
            "milestone": None,
        }
    ]
    # Assert that the issue does not exist
    existing = await adapter.list_issues(state="all")
    assert not any(issue.title == unique_title for issue in existing)
    tmp_yaml_path = _write_yaml_issues_file(yaml_issues)
    try:
        cli_with_starting_args = get_cli_with_starting_args()
        cli_command = cli_with_starting_args + ["process-issues", tmp_yaml_path]
        # 1. Create the issue via CLI
        result = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )
        assert result.returncode == 0
        assert "Issue not found in GitHub" in result.stdout
        # Wait for the issue to appear
        issues = await _wait_for_issues_on_github(adapter, [unique_title])
        created_issue = next((issue for issue in issues if issue.title == unique_title), None)
        assert created_issue is not None, f"Issue {unique_title} not found in GitHub"
        assert created_issue.body == initial_body

        # 2. Update the YAML file with the new body
        yaml_issues[0]["body"] = updated_body
        with open(tmp_yaml_path, "w") as f:
            yaml.dump({"issues": yaml_issues}, f)

        # 3. Run the CLI again to update the issue
        result_update = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )
        assert result_update.returncode == 0
        assert "Updated issue" in result_update.stdout or "updated" in result_update.stdout.lower() or "No changes needed" not in result_update.stdout

        # 4. Wait for the update to be reflected on GitHub
        def updated_issue_predicate(issues: list[Issue]) -> bool:
            return any(issue.title == unique_title and issue.body == updated_body for issue in issues)

        updated_issues = await _wait_for_issues_on_github(adapter, [unique_title], predicate=updated_issue_predicate)
        updated_issue_fetched = next((issue for issue in updated_issues if issue.title == unique_title), None)
        assert updated_issue_fetched is not None
        assert updated_issue_fetched.body == updated_body

        # Clean up: close the created issue
        await _close_issues_by_title(adapter, [unique_title])
    except subprocess.CalledProcessError as e:
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        raise
    finally:
        os.remove(tmp_yaml_path)
