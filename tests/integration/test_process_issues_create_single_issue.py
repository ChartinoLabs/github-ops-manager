"""Integration test for the GitHub Ops Manager CLI to create a single issue."""

import os
import subprocess

import pytest

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
async def test_real_github_issue_sync_cli_single_issue() -> None:
    """Test the GitHub Ops Manager ability to process a single issue via the CLI."""
    adapter = get_github_adapter()
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
        result = run_process_issues_cli(tmp_yaml_path)
        assert result.returncode == 0
        assert "Issue not found in GitHub" in result.stdout
        # Wait for the issue to appear
        issues = await _wait_for_issues_on_github(adapter, [unique_title])
        assert any(issue.title == unique_title for issue in issues), f"Issue {unique_title} not found in GitHub"
        # Run the CLI again (should be NOOP)
        result2 = run_process_issues_cli(tmp_yaml_path)
        assert result2.returncode == 0
        assert "No changes needed" in result2.stdout or "up to date" in result2.stdout.lower()
        # Clean up: close the created issue
        await _close_issues_by_title(adapter, [unique_title])
    except subprocess.CalledProcessError:
        raise
    finally:
        os.remove(tmp_yaml_path)
