"""Integration tests for the GitHub sync."""

import os
import subprocess
import tempfile
import time
import uuid

import pytest
import yaml
from githubkit import GitHub

from github_ops_manager.github.adapter import GitHubKitAdapter

from .utils import get_cli_with_starting_args


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_github_issue_sync_cli() -> None:
    """Test the GitHub Ops Manager ability to process issues via the CLI."""
    # Load credentials and repo from environment variables (set via .env)
    token = os.environ.get("GITHUB_PAT_TOKEN")
    if not token:
        # Fail the test if the token is not set
        pytest.fail("GITHUB_PAT_TOKEN not set in environment")

    repo_slug = os.environ["REPO"]
    owner, repo = repo_slug.split("/")

    # Create a githubkit client with PAT for cleanup
    client = GitHub(token)
    adapter = GitHubKitAdapter(client, owner, repo)

    # Use a unique title for this test run
    unique_title = f"IntegrationTest-{uuid.uuid4()}"
    yaml_issue = {
        "issues": [
            {
                "title": unique_title,
                "body": "Integration test body",
                "labels": ["bug"],
                "assignees": [],
                "milestone": None,
            }
        ]
    }

    # Assert that the issue does not exist
    existing = await adapter.list_issues(state="all")
    print("\nInitial check - existing issues:")
    for issue in existing:
        print(f"  - {issue.number}: {issue.title}")
    assert not any(issue.title == unique_title for issue in existing)

    # Write the YAML to a temporary file
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp_yaml:
        yaml.dump(yaml_issue, tmp_yaml)
        tmp_yaml_path = tmp_yaml.name

    try:
        # Get the CLI command with starting args
        cli_with_starting_args = get_cli_with_starting_args()

        # Construct the complete CLI command
        cli_command = cli_with_starting_args + [
            "process-issues",
            tmp_yaml_path,
        ]

        print(f"\nRunning command: {' '.join(cli_command)}")

        # Run the CLI to process issues (create)
        result = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )

        print(f"\nCommand result: {result.returncode}")
        print(f"Command stdout: {result.stdout}")
        print(f"Command stderr: {result.stderr}")

        assert result.returncode == 0
        assert "Issue not found in GitHub" in result.stdout

        # Check the GitHub API out-of-band to verify the issue was created.
        # Check for this three times, as GitHub API may take a moment to
        # update.
        max_attempts = 10
        for attempt in range(max_attempts):
            print(f"\n[{attempt + 1}/{max_attempts}] Fetching issues from GitHub...")
            issues = await adapter.list_issues(state="all")
            print(f"[{attempt + 1}/{max_attempts}] Looking for issue titled {unique_title} amongst {len(issues)} open issues in repository:")
            for issue in issues:
                print(f"  - {issue.number}: {issue.title} (created_at: {getattr(issue, 'created_at', 'N/A')})")
            if any(issue.title == unique_title for issue in issues):
                print(f"Found issue with title {unique_title}!")
                break
            print(f"[{attempt + 1}/{max_attempts}] Issue not found, waiting 15 seconds and trying again...")
            time.sleep(15)
        assert any(issue.title == unique_title for issue in issues), f"Issue {unique_title} not found in GitHub"

        # Run the CLI again (should be NOOP)
        result2 = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )

        print(f"\nSecond run result: {result2.returncode}")
        print(f"Second run stdout: {result2.stdout}")
        print(f"Second run stderr: {result2.stderr}")

        assert result2.returncode == 0
        assert "No changes needed" in result2.stdout or "up to date" in result2.stdout.lower()

        # Clean up: close the created issue
        existing = await adapter.list_issues(state="all")
        for issue in existing:
            if issue.title == unique_title:
                print(f"\nClosing issue {issue.number}: {issue.title}")
                await adapter.close_issue(issue.number)
    except subprocess.CalledProcessError as e:
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        raise
    finally:
        os.remove(tmp_yaml_path)
