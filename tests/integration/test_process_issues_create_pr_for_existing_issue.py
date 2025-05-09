"""Integration test for process-issues: create PR for an existing issue."""

import os
import shutil
import subprocess
import tempfile
import uuid

import pytest
from githubkit.versions.latest.models import PullRequest

from tests.integration.utils import (
    _close_issues_by_title,
    _wait_for_issues_on_github,
    _write_yaml_issues_file,
    get_cli_with_starting_args,
    get_github_adapter,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_process_issues_create_pr_for_existing_issue() -> None:
    """Test creating a PR for an existing issue via the CLI."""
    adapter = get_github_adapter()
    unique_id = str(uuid.uuid4())
    issue_title = f"IntegrationTestPR-ExistingIssue-{unique_id}"
    pr_title = f"IntegrationTestPR-PR-{unique_id}"
    pr_body = "This PR is created for an existing issue."
    pr_labels = ["integration-test", "pr-label"]
    test_file_content = f"Random content: {uuid.uuid4()}"

    # Step 1: Create the issue first
    yaml_issues = [
        {
            "title": issue_title,
            "body": "This is a test issue for PR creation.",
        }
    ]
    tmp_yaml_path = _write_yaml_issues_file(yaml_issues)
    cli_with_starting_args = get_cli_with_starting_args()
    cli_command = cli_with_starting_args + ["process-issues", tmp_yaml_path]
    subprocess.run(
        cli_command,
        capture_output=True,
        text=True,
        check=True,
        env=os.environ.copy(),
    )
    # Wait for the issue to appear
    issues = await _wait_for_issues_on_github(adapter, [issue_title])
    assert any(issue.title == issue_title for issue in issues)

    # Step 2: Add PR to the YAML for the existing issue
    with tempfile.NamedTemporaryFile("w", suffix=f"_{unique_id}.txt", delete=False) as tmp_file:
        test_filename = tmp_file.name
        tmp_file.write(test_file_content)
    yaml_issues[0]["pull_request"] = {
        "title": pr_title,
        "body": pr_body,
        "files": [os.path.basename(test_filename)],
        "labels": pr_labels,
    }
    tmp_yaml_path2 = _write_yaml_issues_file(yaml_issues)
    try:
        local_test_filename = os.path.basename(test_filename)
        shutil.copy(test_filename, local_test_filename)
        cli_command2 = cli_with_starting_args + ["process-issues", tmp_yaml_path2]
        result = subprocess.run(
            cli_command2,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )
        print("\nCLI STDOUT:\n", result.stdout)
        print("\nCLI STDERR:\n", result.stderr)
        assert result.returncode == 0
        # Wait for the PR to appear
        pr: PullRequest | None = None
        for _ in range(25):
            prs = await adapter.list_pull_requests(state="open")
            pr = next((p for p in prs if p.title == pr_title), None)
            if pr:
                break
            import time

            time.sleep(10)
        assert pr is not None, f"PR with title {pr_title} not found in GitHub"
        # Ensure only one issue exists with the title
        issues = await _wait_for_issues_on_github(adapter, [issue_title])
        assert sum(1 for issue in issues if issue.title == issue_title) == 1
        # Cleanup: close PR, delete branch, remove file from repo if possible
        await adapter.close_pull_request(pr.number)
        try:
            await adapter.client.rest.git.async_delete_ref(
                owner=adapter.owner,
                repo=adapter.repo_name,
                ref=f"heads/{pr.head.ref}",
            )
        except Exception:
            pass
        await _close_issues_by_title(adapter, [issue_title])
    finally:
        if os.path.exists(test_filename):
            os.remove(test_filename)
        local_test_filename = os.path.basename(test_filename)
        if os.path.exists(local_test_filename):
            os.remove(local_test_filename)
        if os.path.exists(tmp_yaml_path):
            os.remove(tmp_yaml_path)
        if os.path.exists(tmp_yaml_path2):
            os.remove(tmp_yaml_path2)
