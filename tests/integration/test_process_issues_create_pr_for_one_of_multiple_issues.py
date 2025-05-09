"""Integration test for process-issues: multiple issues, only one with a PR."""

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
async def test_process_issues_create_pr_for_one_of_multiple_issues() -> None:
    """Test multiple issues, only one with a PR, via the CLI."""
    adapter = get_github_adapter()
    unique_id = str(uuid.uuid4())
    issue_titles = [
        f"IntegrationTestPR-MultiIssue-{unique_id}-1",
        f"IntegrationTestPR-MultiIssue-{unique_id}-2",
        f"IntegrationTestPR-MultiIssue-{unique_id}-3",
    ]
    pr_title = f"IntegrationTestPR-PR-{unique_id}"
    pr_body = "This PR is created by the integration test (one of multiple)."
    pr_labels = ["integration-test", "pr-label"]
    test_file_content = f"Random content: {uuid.uuid4()}"

    # Write the random file to a temporary file
    with tempfile.NamedTemporaryFile("w", suffix=f"_{unique_id}.txt", delete=False) as tmp_file:
        test_filename = tmp_file.name
        tmp_file.write(test_file_content)

    # Compose YAML: only the first issue has a PR
    yaml_issues = [
        {
            "title": issue_titles[0],
            "body": "This is a test issue for PR creation.",
            "pull_request": {
                "title": pr_title,
                "body": pr_body,
                "files": [os.path.basename(test_filename)],
                "labels": pr_labels,
            },
        },
        {
            "title": issue_titles[1],
            "body": "This is a test issue without PR 2.",
        },
        {
            "title": issue_titles[2],
            "body": "This is a test issue without PR 3.",
        },
    ]
    tmp_yaml_path = _write_yaml_issues_file(yaml_issues)

    # Pre-check: Assert PR does not exist
    prs = await adapter.list_pull_requests(state="open")
    assert not any(pr.title == pr_title for pr in prs)

    cli_with_starting_args = get_cli_with_starting_args()
    cli_command = cli_with_starting_args + ["process-issues", tmp_yaml_path]

    try:
        # Copy the temp file to the current directory for the CLI
        local_test_filename = os.path.basename(test_filename)
        shutil.copy(test_filename, local_test_filename)
        result = subprocess.run(
            cli_command,
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
        assert pr.body == pr_body
        pr_label_names = {label.name if hasattr(label, "name") else label for label in getattr(pr, "labels", [])}
        for label in pr_labels:
            assert label in pr_label_names
        # Check the file exists in the PR branch
        branch_name = pr.head.ref
        file_resp = await adapter.client.rest.repos.async_get_content(
            owner=adapter.owner,
            repo=adapter.repo_name,
            path=local_test_filename,
            ref=branch_name,
        )
        import base64

        file_content = base64.b64decode(file_resp.parsed_data.content).decode("utf-8")
        assert file_content == test_file_content
        # Check all issues exist
        issues = await _wait_for_issues_on_github(adapter, issue_titles)
        for title in issue_titles:
            assert any(issue.title == title for issue in issues)
        # Cleanup: close PR, delete branch, remove file from repo if possible
        await adapter.close_pull_request(pr.number)
        try:
            await adapter.client.rest.git.async_delete_ref(
                owner=adapter.owner,
                repo=adapter.repo_name,
                ref=f"heads/{branch_name}",
            )
        except Exception:
            pass
        # Close all created issues
        await _close_issues_by_title(adapter, issue_titles)
    except subprocess.CalledProcessError as e:
        print("\nCLI STDOUT (on error):\n", e.stdout)
        print("\nCLI STDERR (on error):\n", e.stderr)
        raise
    finally:
        if os.path.exists(test_filename):
            os.remove(test_filename)
        local_test_filename = os.path.basename(test_filename)
        if os.path.exists(local_test_filename):
            os.remove(local_test_filename)
        if os.path.exists(tmp_yaml_path):
            os.remove(tmp_yaml_path)
