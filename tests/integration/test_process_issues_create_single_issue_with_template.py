"""Test issue creation with body rendered from a Jinja2 template using 'issue_template' and 'data'."""

import os
import subprocess
import tempfile

import pytest

from tests.integration.utils import (
    _close_issues_by_title,
    _wait_for_issues_on_github,
    generate_unique_issue_title,
    get_cli_with_starting_args,
    get_github_adapter,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_github_issue_sync_cli_single_issue_with_template() -> None:
    """Test issue creation with body rendered from a Jinja2 template using 'issue_template' and 'data'."""
    adapter = get_github_adapter()
    unique_title = generate_unique_issue_title()
    template_content = """# {{ title }}\n\n**Component:** {{ data.component }}\n**Severity:** {{ data.severity }}\n"""
    yaml_issues = [
        {
            "title": unique_title,
            "data": {"component": "Login", "severity": "critical"},
            "labels": ["bug"],
            "assignees": [],
            "milestone": None,
        }
    ]
    # Write template to a temp file
    with tempfile.NamedTemporaryFile("w", suffix=".md.j2", delete=False) as tmp_template:
        tmp_template.write(template_content)
        tmp_template_path = tmp_template.name
    # Write YAML to a temp file
    yaml_dict = {"issue_template": tmp_template_path, "issues": yaml_issues}
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp_yaml:
        import yaml as pyyaml

        pyyaml.safe_dump(yaml_dict, tmp_yaml)
        tmp_yaml_path = tmp_yaml.name
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
        # Check that the body matches the rendered template
        created_issue = next(issue for issue in issues if issue.title == unique_title)
        expected_body = f"# {unique_title}\n\n**Component:** Login\n**Severity:** critical\n"
        assert created_issue.body.strip() == expected_body.strip()
        # Clean up: close the created issue
        await _close_issues_by_title(adapter, [unique_title])
    except subprocess.CalledProcessError as e:
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        raise
    finally:
        os.remove(tmp_yaml_path)
        os.remove(tmp_template_path)
