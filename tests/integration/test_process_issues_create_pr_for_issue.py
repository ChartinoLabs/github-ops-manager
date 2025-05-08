"""Integration test for the process-issues command to create a PR for an issue."""

import os
import subprocess
import tempfile
import uuid

import pytest
from githubkit.versions.latest.models import PullRequest

from tests.integration.utils import (
    _write_yaml_issues_file,
    get_github_adapter,
    run_process_issues_cli,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_process_issues_create_pr_for_issue() -> None:
    """Test creating a PR for an issue with a new file via the CLI."""
    adapter = get_github_adapter()
    unique_id: str = str(uuid.uuid4())
    issue_title: str = f"IntegrationTestPR-Issue-{unique_id}"
    pr_title: str = f"IntegrationTestPR-PR-{unique_id}"
    pr_body: str = "This PR is created by the integration test."
    pr_labels: list[str] = ["integration-test", "pr-label"]
    test_file_content: str = f"Random content: {uuid.uuid4()}"

    # 1. Write the random file to a temporary file
    with tempfile.NamedTemporaryFile("w", suffix=f"_{unique_id}.txt", delete=False) as tmp_file:
        test_filename = tmp_file.name
        tmp_file.write(test_file_content)

    # 2. Write the YAML file
    yaml_issues = [
        {
            "title": issue_title,
            "body": "This is a test issue for PR creation.",
            "pull_request": {
                "title": pr_title,
                "body": pr_body,
                "files": [os.path.basename(test_filename)],
                "labels": pr_labels,
            },
        }
    ]
    tmp_yaml_path: str = _write_yaml_issues_file(yaml_issues)

    # 3. Pre-check: Assert PR does not exist
    prs = await adapter.list_pull_requests(state="open")
    assert not any(pr.title == pr_title for pr in prs)

    try:
        # 4. Run the CLI
        # Copy the temp file to the current directory with the correct name for the CLI to find it
        import shutil

        local_test_filename = os.path.basename(test_filename)
        shutil.copy(test_filename, local_test_filename)
        result = run_process_issues_cli(tmp_yaml_path)
        assert result.returncode == 0
        # 5. Wait for the PR to appear
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
        # 6. Check the file exists in the PR branch
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

        # Fetch open issues and close the issue we've created
        issues = await adapter.list_issues(state="open")
        issue = next((i for i in issues if i.title == issue_title), None)
        if issue:
            await adapter.close_issue(issue.number)
    except subprocess.CalledProcessError:
        raise
    finally:
        # Remove local files
        if os.path.exists(test_filename):
            os.remove(test_filename)
        local_test_filename = os.path.basename(test_filename)
        if os.path.exists(local_test_filename):
            os.remove(local_test_filename)
        if os.path.exists(tmp_yaml_path):
            os.remove(tmp_yaml_path)
