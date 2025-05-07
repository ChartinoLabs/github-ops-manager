"""Integration tests for the GitHub sync."""

import os
import subprocess

import pytest
import yaml
from githubkit import GitHub
from githubkit.versions.latest.models import Issue

from github_ops_manager.github.adapter import GitHubKitAdapter

from .utils import (
    _close_issues_by_title,
    _extract_label_names,
    _wait_for_issues_on_github,
    _write_yaml_issues_file,
    generate_unique_issue_title,
    get_cli_with_starting_args,
)


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_github_issue_update_one_of_multiple() -> None:
    """Test creating multiple issues, then updating the body of one via the CLI."""
    token: str | None = os.environ.get("GITHUB_PAT_TOKEN")
    if not token:
        pytest.fail("GITHUB_PAT_TOKEN not set in environment")
    repo_slug = os.environ["REPO"]
    owner, repo = repo_slug.split("/")
    client = GitHub(token)
    adapter = GitHubKitAdapter(client, owner, repo)
    unique_titles = [generate_unique_issue_title(f"IntegrationTestMultiUpdate{i + 1}") for i in range(3)]
    initial_bodies = [f"Initial body {i + 1}" for i in range(3)]
    updated_body = "Updated body for issue 2"
    yaml_issues = [
        {
            "title": title,
            "body": body,
            "labels": ["bug"],
            "assignees": [],
            "milestone": None,
        }
        for title, body in zip(unique_titles, initial_bodies, strict=False)
    ]
    # Assert that the issues do not exist
    existing = await adapter.list_issues(state="all")
    for title in unique_titles:
        assert not any(issue.title == title for issue in existing)
    tmp_yaml_path = _write_yaml_issues_file(yaml_issues)
    try:
        cli_with_starting_args = get_cli_with_starting_args()
        cli_command = cli_with_starting_args + ["process-issues", tmp_yaml_path]
        # 1. Create the issues via CLI
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
        for i, title in enumerate(unique_titles):
            issue = next((iss for iss in issues if iss.title == title), None)
            assert issue is not None
            assert issue.body == initial_bodies[i]
        # 2. Update the body of the second issue in the YAML
        yaml_issues[1]["body"] = updated_body
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
            return any(issue.title == unique_titles[1] and issue.body == updated_body for issue in issues)

        updated_issues = await _wait_for_issues_on_github(adapter, unique_titles, predicate=updated_issue_predicate)
        # Validate only the targeted issue is updated
        for i, title in enumerate(unique_titles):
            issue = next((iss for iss in updated_issues if iss.title == title), None)
            assert issue is not None
            if i == 1:
                assert issue.body == updated_body
            else:
                assert issue.body == initial_bodies[i]
        # Clean up: close all created issues
        await _close_issues_by_title(adapter, unique_titles)
    except subprocess.CalledProcessError as e:
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        raise
    finally:
        os.remove(tmp_yaml_path)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_github_issue_update_labels_single() -> None:
    """Test creating one issue, then updating its labels by adding a new label via the CLI."""
    token: str | None = os.environ.get("GITHUB_PAT_TOKEN")
    if not token:
        pytest.fail("GITHUB_PAT_TOKEN not set in environment")
    repo_slug = os.environ["REPO"]
    owner, repo = repo_slug.split("/")
    client = GitHub(token)
    adapter = GitHubKitAdapter(client, owner, repo)
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
        assert created_issue is not None
        assert _extract_label_names(created_issue) == set(initial_labels)
        # 2. Update the YAML file to add a new label
        yaml_issues[0]["labels"].append(new_label)
        with open(tmp_yaml_path, "w") as f:
            yaml.dump({"issues": yaml_issues}, f)
        # 3. Run the CLI again to update the labels
        result_update = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )
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
    except subprocess.CalledProcessError as e:
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        raise
    finally:
        os.remove(tmp_yaml_path)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_github_issue_update_labels_one_of_multiple() -> None:
    """Test creating three issues, then updating one issue's labels by adding a new label via the CLI."""
    token: str | None = os.environ.get("GITHUB_PAT_TOKEN")
    if not token:
        pytest.fail("GITHUB_PAT_TOKEN not set in environment")
    repo_slug = os.environ["REPO"]
    owner, repo = repo_slug.split("/")
    client = GitHub(token)
    adapter = GitHubKitAdapter(client, owner, repo)
    unique_titles = [generate_unique_issue_title(f"IntegrationTestLabelMulti{i + 1}") for i in range(3)]
    initial_labels = ["bug"]
    new_label = "enhancement"
    yaml_issues = [
        {
            "title": title,
            "body": f"Initial body for {title}",
            "labels": initial_labels.copy(),
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
        # 1. Create the issues via CLI
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
            issue = next((iss for iss in issues if iss.title == title), None)
            assert issue is not None
            assert _extract_label_names(issue) == set(initial_labels)
        # 2. Update the labels of the second issue in the YAML
        yaml_issues[1]["labels"].append(new_label)
        with open(tmp_yaml_path, "w") as f:
            yaml.dump({"issues": yaml_issues}, f)
        # 3. Run the CLI again to update the labels
        result_update = subprocess.run(
            cli_command,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )
        assert result_update.returncode == 0

        # 4. Wait for the update to be reflected on GitHub
        def updated_labels_predicate(issues: list[Issue]) -> bool:
            return any(issue.title == unique_titles[1] and _extract_label_names(issue) == set(initial_labels + [new_label]) for issue in issues)

        updated_issues = await _wait_for_issues_on_github(adapter, unique_titles, predicate=updated_labels_predicate)
        # Validate only the targeted issue is updated
        for i, title in enumerate(unique_titles):
            issue = next((iss for iss in updated_issues if iss.title == title), None)
            assert issue is not None
            if i == 1:
                assert _extract_label_names(issue) == set(initial_labels + [new_label])
            else:
                assert _extract_label_names(issue) == set(initial_labels)
        # Clean up: close all created issues
        await _close_issues_by_title(adapter, unique_titles)
    except subprocess.CalledProcessError as e:
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        raise
    finally:
        os.remove(tmp_yaml_path)
