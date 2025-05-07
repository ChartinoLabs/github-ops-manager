"""Integration tests for the GitHub sync."""

import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv
from githubkit import GitHub

from github_ops_manager.github.adapter import GitHubKitAdapter


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_github_issue_sync_cli() -> None:
    """Test the GitHub Ops Manager ability to process issues via the CLI."""
    load_dotenv(dotenv_path=".env.integration")

    # Load credentials and repo from environment variables (set via .env)
    token = os.environ["GITHUB_PAT_TOKEN"]
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
    assert not any(issue.title == unique_title for issue in existing)

    # Write the YAML to a temporary file
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp_yaml:
        yaml.dump(yaml_issue, tmp_yaml)
        tmp_yaml_path = tmp_yaml.name

    # Path to the CLI script
    cli_script = str(Path(__file__).parent.parent.parent / "github-ops-manager")
    assert os.path.exists(cli_script), f"CLI script not found at {cli_script}"
    os.chmod(cli_script, 0o755)  # Ensure it's executable

    try:
        # Construct the CLI command (global options before subcommand)
        cli_command = [cli_script, "--repo", repo_slug, "process-issues", "--yaml-path", tmp_yaml_path]
        env = os.environ.copy()
        # Run the CLI to process issues (create)
        result = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        assert result.returncode == 0
        assert "Created issue" in result.stdout or "created issue" in result.stdout.lower()

        # Check the GitHub API out-of-band to verify the issue was created
        issues = await adapter.list_issues(state="all")
        assert any(issue.title == unique_title for issue in issues)

        # Run the CLI again (should be NOOP)
        result2 = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        assert result2.returncode == 0
        assert "No changes needed" in result2.stdout or "up to date" in result2.stdout.lower()

        # Clean up: close the created issue
        existing = await adapter.list_issues(state="all")
        for issue in existing:
            if issue.title == unique_title:
                await adapter.close_issue(issue.number)
    except subprocess.CalledProcessError as e:
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        raise
    finally:
        os.remove(tmp_yaml_path)
