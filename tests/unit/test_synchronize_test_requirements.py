"""Unit tests for the test_requirements module."""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jinja2
import pytest

from github_ops_manager.synchronize.test_requirements import (
    create_catalog_pr_for_test_case,
    create_issue_for_test_case,
    create_project_pr_for_test_case,
    process_test_requirements,
    render_issue_body_for_test_case,
)


class TestRenderIssueBodyForTestCase:
    """Tests for render_issue_body_for_test_case function."""

    def test_renders_basic_template(self) -> None:
        """Should render template with test case data."""
        template = jinja2.Template("Purpose: {{ purpose }}\nCommands: {{ commands|length }}")
        test_case: dict[str, Any] = {
            "title": "Test Case 1",
            "purpose": "Verify interface status",
            "commands": [{"command": "show interfaces"}],
        }

        result = render_issue_body_for_test_case(test_case, template)

        assert "Purpose: Verify interface status" in result
        assert "Commands: 1" in result

    def test_handles_empty_commands(self) -> None:
        """Should handle test case with no commands."""
        template = jinja2.Template("Purpose: {{ purpose }}\nCommands: {{ commands|length }}")
        test_case: dict[str, Any] = {
            "title": "Test Case 1",
            "purpose": "Test purpose",
            "commands": [],
        }

        result = render_issue_body_for_test_case(test_case, template)

        assert "Commands: 0" in result

    def test_handles_missing_optional_fields(self) -> None:
        """Should handle missing optional fields with defaults."""
        template = jinja2.Template("Purpose: {{ purpose }}\nPass Criteria: {{ pass_criteria }}\nParams: {{ jobfile_parameters }}")
        test_case: dict[str, Any] = {
            "title": "Test Case 1",
            "commands": [],
        }

        result = render_issue_body_for_test_case(test_case, template)

        assert "Purpose: " in result

    def test_raises_on_undefined_required_variable(self) -> None:
        """Should raise when required variable is undefined."""
        template = jinja2.Template("{{ required_var }}", undefined=jinja2.StrictUndefined)
        test_case: dict[str, Any] = {"title": "Test Case 1"}

        with pytest.raises(jinja2.UndefinedError):
            render_issue_body_for_test_case(test_case, template)


class TestCreateIssueForTestCase:
    """Tests for create_issue_for_test_case function."""

    @pytest.mark.asyncio
    async def test_creates_issue_successfully(self) -> None:
        """Should create issue and return metadata."""
        mock_adapter = AsyncMock()
        mock_issue = MagicMock()
        mock_issue.number = 123
        mock_issue.html_url = "https://github.com/org/repo/issues/123"
        mock_adapter.create_issue.return_value = mock_issue

        test_case: dict[str, Any] = {"title": "Test Case 1"}

        result = await create_issue_for_test_case(
            test_case,
            mock_adapter,
            "Issue body content",
            labels=["test-automation"],
        )

        assert result is not None
        assert result["issue_number"] == 123
        assert result["issue_url"] == "https://github.com/org/repo/issues/123"
        mock_adapter.create_issue.assert_called_once_with(
            title="Test Case 1",
            body="Issue body content",
            labels=["test-automation"],
        )

    @pytest.mark.asyncio
    async def test_updates_test_case_with_metadata(self) -> None:
        """Should update test case dict with issue metadata."""
        mock_adapter = AsyncMock()
        mock_issue = MagicMock()
        mock_issue.number = 456
        mock_issue.html_url = "https://github.com/org/repo/issues/456"
        mock_adapter.create_issue.return_value = mock_issue

        test_case: dict[str, Any] = {"title": "Test Case 1"}

        await create_issue_for_test_case(test_case, mock_adapter, "Body")

        assert test_case["project_issue_number"] == 456
        assert test_case["project_issue_url"] == "https://github.com/org/repo/issues/456"

    @pytest.mark.asyncio
    async def test_returns_none_on_missing_title(self) -> None:
        """Should return None if test case has no title."""
        mock_adapter = AsyncMock()
        test_case: dict[str, Any] = {}

        result = await create_issue_for_test_case(test_case, mock_adapter, "Body")

        assert result is None
        mock_adapter.create_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_on_api_error(self) -> None:
        """Should return None if API call fails."""
        mock_adapter = AsyncMock()
        mock_adapter.create_issue.side_effect = Exception("API Error")

        test_case: dict[str, Any] = {"title": "Test Case 1"}

        result = await create_issue_for_test_case(test_case, mock_adapter, "Body")

        assert result is None


class TestCreateProjectPrForTestCase:
    """Tests for create_project_pr_for_test_case function."""

    @pytest.mark.asyncio
    async def test_creates_pr_successfully(self) -> None:
        """Should create PR and return metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            script_path = "scripts/test.robot"
            (base_dir / "scripts").mkdir()
            (base_dir / script_path).write_text("*** Test Cases ***\nTest\n    Log    Hello")

            mock_adapter = AsyncMock()
            mock_adapter.branch_exists.return_value = False
            mock_pr = MagicMock()
            mock_pr.number = 789
            mock_pr.html_url = "https://github.com/org/repo/pull/789"
            mock_adapter.create_pull_request.return_value = mock_pr

            test_case: dict[str, Any] = {
                "title": "Test Case 1",
                "generated_script_path": script_path,
            }

            result = await create_project_pr_for_test_case(
                test_case,
                mock_adapter,
                base_dir,
                "main",
                "https://github.com/org/repo",
            )

            assert result is not None
            assert result["pr_number"] == 789
            assert result["pr_url"] == "https://github.com/org/repo/pull/789"
            mock_adapter.create_branch.assert_called_once()
            mock_adapter.commit_files_to_branch.assert_called_once()
            mock_adapter.create_pull_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_pr_body_includes_issue_reference(self) -> None:
        """Should include issue reference in PR body when issue metadata exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            script_path = "test.robot"
            (base_dir / script_path).write_text("*** Test Cases ***\nTest\n    Log    Hello")

            mock_adapter = AsyncMock()
            mock_adapter.branch_exists.return_value = False
            mock_pr = MagicMock()
            mock_pr.number = 100
            mock_pr.html_url = "https://github.com/org/repo/pull/100"
            mock_adapter.create_pull_request.return_value = mock_pr

            test_case: dict[str, Any] = {
                "title": "Test Case 1",
                "generated_script_path": script_path,
                "project_issue_number": 42,
                "project_issue_url": "https://github.com/org/repo/issues/42",
            }

            await create_project_pr_for_test_case(
                test_case,
                mock_adapter,
                base_dir,
                "main",
                "https://github.com/org/repo",
            )

            # Verify PR body includes issue reference
            call_kwargs = mock_adapter.create_pull_request.call_args[1]
            pr_body = call_kwargs["body"]
            assert "Closes #42" in pr_body
            assert "#42" in pr_body
            assert "https://github.com/org/repo/issues/42" in pr_body

    @pytest.mark.asyncio
    async def test_pr_body_without_issue_reference(self) -> None:
        """Should create PR without issue reference when no issue metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            script_path = "test.robot"
            (base_dir / script_path).write_text("*** Test Cases ***\nTest\n    Log    Hello")

            mock_adapter = AsyncMock()
            mock_adapter.branch_exists.return_value = False
            mock_pr = MagicMock()
            mock_pr.number = 100
            mock_pr.html_url = "https://github.com/org/repo/pull/100"
            mock_adapter.create_pull_request.return_value = mock_pr

            test_case: dict[str, Any] = {
                "title": "Test Case 1",
                "generated_script_path": script_path,
                # No project_issue_number
            }

            await create_project_pr_for_test_case(
                test_case,
                mock_adapter,
                base_dir,
                "main",
                "https://github.com/org/repo",
            )

            # Verify PR body does not have closing keyword
            call_kwargs = mock_adapter.create_pull_request.call_args[1]
            pr_body = call_kwargs["body"]
            assert "Closes #" not in pr_body
            assert "Quicksilver" in pr_body

    @pytest.mark.asyncio
    async def test_skips_when_branch_exists(self) -> None:
        """Should skip PR creation if branch already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            script_path = "test.robot"
            (base_dir / script_path).write_text("*** Test Cases ***")

            mock_adapter = AsyncMock()
            mock_adapter.branch_exists.return_value = True

            test_case: dict[str, Any] = {
                "title": "Test Case 1",
                "generated_script_path": script_path,
            }

            result = await create_project_pr_for_test_case(
                test_case,
                mock_adapter,
                base_dir,
                "main",
                "https://github.com/org/repo",
            )

            assert result is None
            mock_adapter.create_pull_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_file_not_found(self) -> None:
        """Should return None if robot file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_adapter = AsyncMock()

            test_case: dict[str, Any] = {
                "title": "Test Case 1",
                "generated_script_path": "nonexistent.robot",
            }

            result = await create_project_pr_for_test_case(
                test_case,
                mock_adapter,
                Path(tmpdir),
                "main",
                "https://github.com/org/repo",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_missing_title(self) -> None:
        """Should return None if test case has no title."""
        mock_adapter = AsyncMock()
        test_case: dict[str, Any] = {"generated_script_path": "test.robot"}

        result = await create_project_pr_for_test_case(
            test_case,
            mock_adapter,
            Path("/tmp"),
            "main",
            "https://github.com/org/repo",
        )

        assert result is None


class TestCreateCatalogPrForTestCase:
    """Tests for create_catalog_pr_for_test_case function."""

    @pytest.mark.asyncio
    async def test_creates_catalog_pr_with_correct_path(self) -> None:
        """Should create PR with correct catalog directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            script_path = "verify_nxos_interfaces.robot"
            robot_content = """*** Settings ***
Test Tags    os:nxos    category:foundations

*** Test Cases ***
Test
    Log    Hello
"""
            (base_dir / script_path).write_text(robot_content)

            mock_adapter = AsyncMock()
            mock_adapter.branch_exists.return_value = False
            mock_pr = MagicMock()
            mock_pr.number = 101
            mock_pr.html_url = "https://github.com/catalog/repo/pull/101"
            mock_pr.head.ref = "feat/nxos/add-verify-nxos-interfaces"
            mock_adapter.create_pull_request.return_value = mock_pr

            test_case: dict[str, Any] = {
                "title": "Test Case 1",
                "generated_script_path": script_path,
                "catalog_destined": True,
            }

            result = await create_catalog_pr_for_test_case(
                test_case,
                mock_adapter,
                base_dir,
                "main",
                "https://github.com/catalog/repo",
            )

            assert result is not None
            assert result["pr_number"] == 101
            assert result["catalog_path"] == "catalog/NX-OS/verify_nxos_interfaces.robot"
            assert result["os_name"] == "nxos"

            # Verify file was committed with correct path
            commit_call = mock_adapter.commit_files_to_branch.call_args
            files_to_commit = commit_call[0][1]
            assert files_to_commit[0][0] == "catalog/NX-OS/verify_nxos_interfaces.robot"

    @pytest.mark.asyncio
    async def test_extracts_os_from_filename_fallback(self) -> None:
        """Should extract OS from filename if not in Test Tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            script_path = "verify_ios_xe_interfaces.robot"
            robot_content = """*** Test Cases ***
Test
    Log    Hello
"""
            (base_dir / script_path).write_text(robot_content)

            mock_adapter = AsyncMock()
            mock_adapter.branch_exists.return_value = False
            mock_pr = MagicMock()
            mock_pr.number = 102
            mock_pr.html_url = "https://github.com/catalog/repo/pull/102"
            mock_pr.head.ref = "feat/ios-xe/add-test"
            mock_adapter.create_pull_request.return_value = mock_pr

            test_case: dict[str, Any] = {
                "title": "Test Case 1",
                "generated_script_path": script_path,
                "catalog_destined": True,
            }

            result = await create_catalog_pr_for_test_case(
                test_case,
                mock_adapter,
                base_dir,
                "main",
                "https://github.com/catalog/repo",
            )

            assert result is not None
            assert result["catalog_path"] == "catalog/IOS-XE/verify_ios_xe_interfaces.robot"

    @pytest.mark.asyncio
    async def test_returns_none_when_os_not_detected(self) -> None:
        """Should return None if OS cannot be extracted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            script_path = "unknown_test.robot"
            robot_content = """*** Test Cases ***
Test
    Log    Hello
"""
            (base_dir / script_path).write_text(robot_content)

            mock_adapter = AsyncMock()

            test_case: dict[str, Any] = {
                "title": "Test Case 1",
                "generated_script_path": script_path,
                "catalog_destined": True,
            }

            result = await create_catalog_pr_for_test_case(
                test_case,
                mock_adapter,
                base_dir,
                "main",
                "https://github.com/catalog/repo",
            )

            assert result is None


class TestProcessTestRequirements:
    """Tests for process_test_requirements function."""

    @pytest.mark.asyncio
    async def test_processes_test_cases_creates_issues(self) -> None:
        """Should process test cases and create issues when needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cases_dir = Path(tmpdir)
            # Create test case file
            (test_cases_dir / "my_test_cases.yaml").write_text(
                """test_cases:
  - title: Test Case 1
    purpose: Test purpose
    commands:
      - command: show version
"""
            )

            mock_project_adapter = AsyncMock()
            mock_issue = MagicMock()
            mock_issue.number = 1
            mock_issue.html_url = "https://github.com/org/repo/issues/1"
            mock_project_adapter.create_issue.return_value = mock_issue

            with patch(
                "github_ops_manager.synchronize.test_requirements.save_test_case_metadata",
                return_value=True,
            ):
                results = await process_test_requirements(
                    test_cases_dir=test_cases_dir,
                    base_directory=test_cases_dir,
                    project_adapter=mock_project_adapter,
                    project_default_branch="main",
                    project_repo_url="https://github.com/org/repo",
                )

            assert results["total_test_cases"] == 1
            assert results["issues_created"] == 1
            assert results["errors"] == []

    @pytest.mark.asyncio
    async def test_skips_test_cases_with_existing_metadata(self) -> None:
        """Should skip test cases that already have issue metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cases_dir = Path(tmpdir)
            # Create test case file with existing metadata
            (test_cases_dir / "my_test_cases.yaml").write_text(
                """test_cases:
  - title: Test Case 1
    purpose: Test purpose
    project_issue_number: 123
    project_issue_url: https://existing-url
    commands:
      - command: show version
"""
            )

            mock_project_adapter = AsyncMock()

            results = await process_test_requirements(
                test_cases_dir=test_cases_dir,
                base_directory=test_cases_dir,
                project_adapter=mock_project_adapter,
                project_default_branch="main",
                project_repo_url="https://github.com/org/repo",
            )

            assert results["total_test_cases"] == 1
            assert results["issues_created"] == 0
            mock_project_adapter.create_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_project_prs_for_non_catalog(self) -> None:
        """Should create project PRs for non-catalog test cases with scripts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cases_dir = Path(tmpdir)
            script_path = "scripts/test.robot"
            (test_cases_dir / "scripts").mkdir()
            (test_cases_dir / script_path).write_text("*** Test Cases ***\nTest\n    Log    Hello")

            (test_cases_dir / "my_test_cases.yaml").write_text(
                f"""test_cases:
  - title: Test Case 1
    purpose: Test purpose
    project_issue_number: 1
    project_issue_url: https://url
    generated_script_path: {script_path}
    commands:
      - command: show version
"""
            )

            mock_project_adapter = AsyncMock()
            mock_project_adapter.branch_exists.return_value = False
            mock_pr = MagicMock()
            mock_pr.number = 10
            mock_pr.html_url = "https://github.com/org/repo/pull/10"
            mock_project_adapter.create_pull_request.return_value = mock_pr

            with patch(
                "github_ops_manager.synchronize.test_requirements.save_test_case_metadata",
                return_value=True,
            ):
                results = await process_test_requirements(
                    test_cases_dir=test_cases_dir,
                    base_directory=test_cases_dir,
                    project_adapter=mock_project_adapter,
                    project_default_branch="main",
                    project_repo_url="https://github.com/org/repo",
                )

            assert results["project_prs_created"] == 1

    @pytest.mark.asyncio
    async def test_creates_catalog_prs_for_catalog_destined(self) -> None:
        """Should create catalog PRs for catalog-destined test cases."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cases_dir = Path(tmpdir)
            script_path = "verify_nxos_test.robot"
            robot_content = """*** Settings ***
Test Tags    os:nxos

*** Test Cases ***
Test
    Log    Hello
"""
            (test_cases_dir / script_path).write_text(robot_content)

            (test_cases_dir / "my_test_cases.yaml").write_text(
                f"""test_cases:
  - title: Test Case 1
    purpose: Test purpose
    project_issue_number: 1
    project_issue_url: https://url
    generated_script_path: {script_path}
    catalog_destined: true
    commands:
      - command: show version
"""
            )

            mock_project_adapter = AsyncMock()
            mock_catalog_adapter = AsyncMock()
            mock_catalog_adapter.branch_exists.return_value = False
            mock_pr = MagicMock()
            mock_pr.number = 20
            mock_pr.html_url = "https://github.com/catalog/repo/pull/20"
            mock_pr.head.ref = "feat/nxos/add-test"
            mock_catalog_adapter.create_pull_request.return_value = mock_pr

            with patch(
                "github_ops_manager.synchronize.test_requirements.save_test_case_metadata",
                return_value=True,
            ):
                results = await process_test_requirements(
                    test_cases_dir=test_cases_dir,
                    base_directory=test_cases_dir,
                    project_adapter=mock_project_adapter,
                    project_default_branch="main",
                    project_repo_url="https://github.com/org/repo",
                    catalog_adapter=mock_catalog_adapter,
                    catalog_default_branch="main",
                    catalog_repo_url="https://github.com/catalog/repo",
                )

            assert results["catalog_prs_created"] == 1
            mock_catalog_adapter.create_pull_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_reports_error_when_catalog_not_configured(self) -> None:
        """Should report error when catalog PR needed but not configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cases_dir = Path(tmpdir)
            script_path = "verify_nxos_test.robot"
            robot_content = """*** Settings ***
Test Tags    os:nxos

*** Test Cases ***
Test
    Log    Hello
"""
            (test_cases_dir / script_path).write_text(robot_content)

            (test_cases_dir / "my_test_cases.yaml").write_text(
                f"""test_cases:
  - title: Test Case 1
    purpose: Test purpose
    project_issue_number: 1
    project_issue_url: https://url
    generated_script_path: {script_path}
    catalog_destined: true
    commands:
      - command: show version
"""
            )

            mock_project_adapter = AsyncMock()

            results = await process_test_requirements(
                test_cases_dir=test_cases_dir,
                base_directory=test_cases_dir,
                project_adapter=mock_project_adapter,
                project_default_branch="main",
                project_repo_url="https://github.com/org/repo",
                # No catalog adapter provided
            )

            assert results["catalog_prs_created"] == 0
            assert len(results["errors"]) == 1
            assert "catalog not configured" in results["errors"][0].lower()

    @pytest.mark.asyncio
    async def test_returns_empty_results_for_empty_directory(self) -> None:
        """Should return empty results for directory with no test cases."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_project_adapter = AsyncMock()

            results = await process_test_requirements(
                test_cases_dir=Path(tmpdir),
                base_directory=Path(tmpdir),
                project_adapter=mock_project_adapter,
                project_default_branch="main",
                project_repo_url="https://github.com/org/repo",
            )

            assert results["total_test_cases"] == 0
            assert results["issues_created"] == 0
            assert results["project_prs_created"] == 0
            assert results["catalog_prs_created"] == 0
            assert results["errors"] == []
