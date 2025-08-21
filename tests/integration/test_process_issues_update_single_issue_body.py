"""Integration test for the GitHub Ops Manager CLI to update a single issue body."""

import os
import subprocess
from pathlib import Path

import pytest
from githubkit.versions.latest.models import Issue

from github_ops_manager.utils.yaml import dump_yaml_to_file
from tests.integration.utils import (
    _close_issues_by_title,
    _wait_for_issues_on_github,
    _write_yaml_issues_file,
    generate_unique_issue_title,
    get_github_adapter,
    run_process_issues_cli,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_github_issue_update_body() -> None:
    """Test creating a single issue, then updating its body."""
    token: str | None = os.environ.get("GITHUB_PAT_TOKEN")
    if not token:
        pytest.fail("GITHUB_PAT_TOKEN not set in environment")
    repo_slug = os.environ["REPO"]
    owner, repo = repo_slug.split("/")
    adapter = get_github_adapter()
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
        # 1. Create the issue via CLI
        result = run_process_issues_cli(tmp_yaml_path)
        assert result.returncode == 0
        assert "Issue not found in GitHub" in result.stdout
        # Wait for the issue to appear
        issues = await _wait_for_issues_on_github(adapter, [unique_title])
        created_issue = next((issue for issue in issues if issue.title == unique_title), None)
        assert created_issue is not None, f"Issue {unique_title} not found in GitHub"
        assert created_issue.body == initial_body

        # 2. Update the YAML file with the new body
        yaml_issues[0]["body"] = updated_body

        dump_yaml_to_file({"issues": yaml_issues}, Path(tmp_yaml_path))

        # 3. Run the CLI again to update the issue
        result_update = run_process_issues_cli(tmp_yaml_path)
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
    except subprocess.CalledProcessError:
        raise
    finally:
        os.remove(tmp_yaml_path)
