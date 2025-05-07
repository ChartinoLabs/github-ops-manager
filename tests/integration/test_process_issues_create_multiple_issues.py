"""Integration test for the GitHub Ops Manager CLI to create multiple issues."""

import os
import subprocess

import pytest
from githubkit import GitHub

from github_ops_manager.github.adapter import GitHubKitAdapter
from tests.integration.utils import (
    _close_issues_by_title,
    _wait_for_issues_on_github,
    _write_yaml_issues_file,
    generate_unique_issue_title,
    get_cli_with_starting_args,
)


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
