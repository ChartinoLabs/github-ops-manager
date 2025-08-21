"""Integration test for the GitHub Ops Manager CLI to update a single issue labels."""

import os
import subprocess
from pathlib import Path

import pytest
from githubkit.versions.latest.models import Issue

from github_ops_manager.utils.yaml import dump_yaml_to_file
from tests.integration.utils import (
    _close_issues_by_title,
    _extract_label_names,
    _wait_for_issues_on_github,
    _write_yaml_issues_file,
    generate_unique_issue_title,
    get_github_adapter,
    run_process_issues_cli,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_github_issue_update_labels_single() -> None:
    """Test creating one issue, then updating its labels by adding a new label via the CLI."""
    token: str | None = os.environ.get("GITHUB_PAT_TOKEN")
    if not token:
        pytest.fail("GITHUB_PAT_TOKEN not set in environment")
    repo_slug = os.environ["REPO"]
    owner, repo = repo_slug.split("/")
    adapter = get_github_adapter()
    unique_title = generate_unique_issue_title("IntegrationTestLabelSingle")
    initial_labels = ["bug"]
    new_label = "enhancement"
    yaml_issues = [
        {
            "title": unique_title,
            "body": "Initial body for label test",
            "labels": initial_labels.copy(),
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
        assert created_issue is not None
        assert _extract_label_names(created_issue) == set(initial_labels)
        # 2. Update the YAML file to add a new label
        yaml_issues[0]["labels"].append(new_label)

        dump_yaml_to_file({"issues": yaml_issues}, Path(tmp_yaml_path))
        # 3. Run the CLI again to update the labels
        result_update = run_process_issues_cli(tmp_yaml_path)
        assert result_update.returncode == 0

        # 4. Wait for the update to be reflected on GitHub
        def updated_labels_predicate(issues: list[Issue]) -> bool:
            return any(issue.title == unique_title and _extract_label_names(issue) == set(initial_labels + [new_label]) for issue in issues)

        updated_issues = await _wait_for_issues_on_github(adapter, [unique_title], predicate=updated_labels_predicate)
        updated_issue = next((issue for issue in updated_issues if issue.title == unique_title), None)
        assert updated_issue is not None
        assert _extract_label_names(updated_issue) == set(initial_labels + [new_label])
        # Clean up: close the created issue
        await _close_issues_by_title(adapter, [unique_title])
    except subprocess.CalledProcessError:
        raise
    finally:
        os.remove(tmp_yaml_path)
