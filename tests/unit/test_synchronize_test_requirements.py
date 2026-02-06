"""Unit tests for the test_requirements module."""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jinja2
import pytest

from github_ops_manager.synchronize.test_requirements import (
    _extract_os_from_catalog_branch,
    create_catalog_pr_for_test_case,
    create_issue_for_test_case,
    create_project_pr_for_test_case,
    create_tracking_issue_for_catalog_test_case,
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
        """Should update test case dict with issue metadata in nested structure."""
        mock_adapter = AsyncMock()
        mock_issue = MagicMock()
        mock_issue.number = 456
        mock_issue.html_url = "https://github.com/org/repo/issues/456"
        mock_adapter.create_issue.return_value = mock_issue

        test_case: dict[str, Any] = {"title": "Test Case 1"}

        await create_issue_for_test_case(test_case, mock_adapter, "Body")

        assert test_case["metadata"]["project_tracking"]["issue_number"] == 456
        assert test_case["metadata"]["project_tracking"]["issue_url"] == "https://github.com/org/repo/issues/456"

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
                "metadata": {
                    "project_tracking": {
                        "issue_number": 42,
                        "issue_url": "https://github.com/org/repo/issues/42",
                    }
                },
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


class TestExtractOsFromCatalogBranch:
    """Tests for _extract_os_from_catalog_branch helper."""

    def test_extracts_os_from_feat_branch(self) -> None:
        """Should extract OS from feat/{os}/add-{stem} pattern."""
        assert _extract_os_from_catalog_branch("feat/nxos/add-verify-nxos-interfaces") == "nxos"

    def test_extracts_os_from_feature_branch(self) -> None:
        """Should extract OS from feature/{os}/add-{stem} pattern."""
        assert _extract_os_from_catalog_branch("feature/ios-xe/add-verify-interfaces") == "ios-xe"

    def test_returns_none_for_no_match(self) -> None:
        """Should return None for branches that don't match the pattern."""
        assert _extract_os_from_catalog_branch("main") is None
        assert _extract_os_from_catalog_branch("fix/something") is None

    def test_handles_deeply_nested_branch(self) -> None:
        """Should extract OS from branches with more than 3 segments."""
        assert _extract_os_from_catalog_branch("feat/ios-xr/add-verify-bgp-neighbors") == "ios-xr"


class TestCreateTrackingIssueForCatalogTestCase:
    """Tests for create_tracking_issue_for_catalog_test_case function."""

    @pytest.mark.asyncio
    async def test_creates_tracking_issue_from_metadata(self) -> None:
        """Should create a tracking issue using catalog_tracking metadata."""
        mock_adapter = AsyncMock()
        mock_issue = MagicMock()
        mock_issue.number = 42
        mock_issue.html_url = "https://github.com/org/repo/issues/42"
        mock_adapter.create_issue.return_value = mock_issue

        test_case: dict[str, Any] = {
            "title": "[NX-OS] Verify Interface Status",
            "purpose": "Check all interfaces are up",
            "commands": [{"command": "show interface status"}],
            "metadata": {
                "catalog": {"destined": True},
                "catalog_tracking": {
                    "pr_number": 101,
                    "pr_url": "https://github.com/catalog/repo/pull/101",
                    "pr_branch": "feat/nxos/add-verify-nxos-interface-status",
                    "git_url": "https://github.com/catalog/repo",
                },
            },
        }

        result = await create_tracking_issue_for_catalog_test_case(
            test_case,
            mock_adapter,
            "https://github.com/catalog/repo",
        )

        assert result is not None
        assert result["issue_number"] == 42
        assert result["issue_url"] == "https://github.com/org/repo/issues/42"

        # Verify issue title uses tracking issue format
        call_kwargs = mock_adapter.create_issue.call_args[1]
        assert call_kwargs["title"] == "Review Catalog PR and Learn Parameters: [NX-OS] Verify Interface Status"

        # Verify body contains tracking issue template elements
        body = call_kwargs["body"]
        assert "Catalog PR" in body
        assert "https://github.com/catalog/repo/pull/101" in body
        assert "feat/nxos/add-verify-nxos-interface-status" in body
        assert "Tasks" in body

    @pytest.mark.asyncio
    async def test_uses_os_from_catalog_pr_result(self) -> None:
        """Should prefer os_name from catalog_pr_result when available."""
        mock_adapter = AsyncMock()
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.html_url = "https://url"
        mock_adapter.create_issue.return_value = mock_issue

        test_case: dict[str, Any] = {
            "title": "Test Case",
            "metadata": {
                "catalog_tracking": {
                    "pr_number": 10,
                    "pr_url": "https://pr-url",
                    "pr_branch": "feat/nxos/add-test",
                },
            },
        }

        catalog_pr_result = {"os_name": "nxos", "pr_number": 10}

        result = await create_tracking_issue_for_catalog_test_case(
            test_case,
            mock_adapter,
            "https://catalog-repo",
            catalog_pr_result=catalog_pr_result,
        )

        assert result is not None
        body = mock_adapter.create_issue.call_args[1]["body"]
        assert "NXOS" in body  # os_name.upper() in template

    @pytest.mark.asyncio
    async def test_updates_test_case_with_issue_metadata(self) -> None:
        """Should update test case dict with issue metadata in nested structure."""
        mock_adapter = AsyncMock()
        mock_issue = MagicMock()
        mock_issue.number = 99
        mock_issue.html_url = "https://github.com/org/repo/issues/99"
        mock_adapter.create_issue.return_value = mock_issue

        test_case: dict[str, Any] = {
            "title": "Test Case",
            "metadata": {
                "catalog_tracking": {
                    "pr_number": 10,
                    "pr_url": "https://pr-url",
                    "pr_branch": "feat/nxos/add-test",
                },
            },
        }

        await create_tracking_issue_for_catalog_test_case(
            test_case,
            mock_adapter,
            "https://catalog-repo",
        )

        assert test_case["metadata"]["project_tracking"]["issue_number"] == 99
        assert test_case["metadata"]["project_tracking"]["issue_url"] == "https://github.com/org/repo/issues/99"

    @pytest.mark.asyncio
    async def test_returns_none_on_missing_title(self) -> None:
        """Should return None if test case has no title."""
        mock_adapter = AsyncMock()
        test_case: dict[str, Any] = {"metadata": {"catalog_tracking": {"pr_number": 1}}}

        result = await create_tracking_issue_for_catalog_test_case(test_case, mock_adapter, "https://url")

        assert result is None
        mock_adapter.create_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_on_missing_catalog_metadata(self) -> None:
        """Should return None if catalog_tracking metadata is missing."""
        mock_adapter = AsyncMock()
        test_case: dict[str, Any] = {"title": "Test Case"}

        result = await create_tracking_issue_for_catalog_test_case(test_case, mock_adapter, "https://url")

        assert result is None
        mock_adapter.create_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_on_api_error(self) -> None:
        """Should return None if API call fails."""
        mock_adapter = AsyncMock()
        mock_adapter.create_issue.side_effect = Exception("API Error")

        test_case: dict[str, Any] = {
            "title": "Test Case",
            "metadata": {
                "catalog_tracking": {
                    "pr_number": 10,
                    "pr_url": "https://pr-url",
                    "pr_branch": "feat/nxos/add-test",
                },
            },
        }

        result = await create_tracking_issue_for_catalog_test_case(test_case, mock_adapter, "https://url")

        assert result is None

    @pytest.mark.asyncio
    async def test_applies_labels(self) -> None:
        """Should pass labels to create_issue."""
        mock_adapter = AsyncMock()
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.html_url = "https://url"
        mock_adapter.create_issue.return_value = mock_issue

        test_case: dict[str, Any] = {
            "title": "Test Case",
            "metadata": {
                "catalog_tracking": {
                    "pr_number": 10,
                    "pr_url": "https://pr-url",
                    "pr_branch": "feat/nxos/add-test",
                },
            },
        }

        await create_tracking_issue_for_catalog_test_case(
            test_case,
            mock_adapter,
            "https://url",
            labels=["test-automation", "catalog"],
        )

        call_kwargs = mock_adapter.create_issue.call_args[1]
        assert call_kwargs["labels"] == ["test-automation", "catalog"]

    @pytest.mark.asyncio
    async def test_renders_suggested_branch_name(self) -> None:
        """Should render suggested project branch name from catalog branch."""
        mock_adapter = AsyncMock()
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.html_url = "https://url"
        mock_adapter.create_issue.return_value = mock_issue

        test_case: dict[str, Any] = {
            "title": "Test Case",
            "metadata": {
                "catalog_tracking": {
                    "pr_number": 10,
                    "pr_url": "https://pr-url",
                    "pr_branch": "feat/nxos/add-verify-nxos-interfaces",
                },
            },
        }

        await create_tracking_issue_for_catalog_test_case(test_case, mock_adapter, "https://url")

        body = mock_adapter.create_issue.call_args[1]["body"]
        assert "learn/nxos/add-verify-nxos-interfaces" in body


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
            # Create test case file with existing nested metadata
            (test_cases_dir / "my_test_cases.yaml").write_text(
                """test_cases:
  - title: Test Case 1
    purpose: Test purpose
    metadata:
      project_tracking:
        issue_number: 123
        issue_url: https://existing-url
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
    generated_script_path: {script_path}
    metadata:
      project_tracking:
        issue_number: 1
        issue_url: https://url
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
    generated_script_path: {script_path}
    metadata:
      project_tracking:
        issue_number: 1
        issue_url: https://url
      catalog:
        destined: true
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
    async def test_catalog_destined_creates_tracking_issue_after_catalog_pr(self) -> None:
        """Should create catalog PR and split-style tracking issue in one run."""
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
  - title: "[NX-OS] Test Case 1"
    purpose: Test purpose
    generated_script_path: {script_path}
    metadata:
      catalog:
        destined: true
    commands:
      - command: show version
"""
            )

            mock_project_adapter = AsyncMock()
            mock_issue = MagicMock()
            mock_issue.number = 50
            mock_issue.html_url = "https://github.com/org/repo/issues/50"
            mock_project_adapter.create_issue.return_value = mock_issue

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

            # Catalog PR created first, then tracking issue
            assert results["catalog_prs_created"] == 1
            assert results["issues_created"] == 1
            mock_catalog_adapter.create_pull_request.assert_called_once()
            mock_project_adapter.create_issue.assert_called_once()

            # Verify tracking issue uses split-style template
            call_kwargs = mock_project_adapter.create_issue.call_args[1]
            assert "Review Catalog PR and Learn Parameters" in call_kwargs["title"]
            assert "Catalog PR" in call_kwargs["body"]
            assert "Tasks" in call_kwargs["body"]
            assert "https://github.com/catalog/repo/pull/20" in call_kwargs["body"]

    @pytest.mark.asyncio
    async def test_catalog_destined_uses_tracking_template_from_previous_run(self) -> None:
        """Should create tracking issue for catalog-destined test case with pre-existing catalog PR."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cases_dir = Path(tmpdir)

            # Test case already has catalog_tracking from a previous run but no issue yet
            (test_cases_dir / "my_test_cases.yaml").write_text(
                """test_cases:
  - title: "[IOS-XE] Verify BGP Neighbors"
    purpose: Verify BGP neighbors are up
    metadata:
      catalog:
        destined: true
      catalog_tracking:
        pr_number: 99
        pr_url: https://github.com/catalog/repo/pull/99
        pr_branch: feat/ios-xe/add-verify-iosxe-bgp-neighbors
        git_url: https://github.com/catalog/repo
    commands:
      - command: show bgp summary
"""
            )

            mock_project_adapter = AsyncMock()
            mock_issue = MagicMock()
            mock_issue.number = 200
            mock_issue.html_url = "https://github.com/org/repo/issues/200"
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

            # No catalog PR created (already exists), but issue should be created
            assert results["catalog_prs_created"] == 0
            assert results["issues_created"] == 1

            # Verify tracking issue uses split-style template
            call_kwargs = mock_project_adapter.create_issue.call_args[1]
            assert "Review Catalog PR and Learn Parameters" in call_kwargs["title"]
            assert "https://github.com/catalog/repo/pull/99" in call_kwargs["body"]
            assert "learn/ios-xe/add-verify-iosxe-bgp-neighbors" in call_kwargs["body"]

    @pytest.mark.asyncio
    async def test_non_catalog_uses_collapsed_template(self) -> None:
        """Should use collapsed-style template for non-catalog test cases."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cases_dir = Path(tmpdir)

            (test_cases_dir / "my_test_cases.yaml").write_text(
                """test_cases:
  - title: Non-Catalog Test
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

            assert results["issues_created"] == 1

            # Verify it uses collapsed style (title is test case title, not tracking format)
            call_kwargs = mock_project_adapter.create_issue.call_args[1]
            assert call_kwargs["title"] == "Non-Catalog Test"
            assert "Review Catalog PR" not in call_kwargs["body"]

    @pytest.mark.asyncio
    async def test_catalog_destined_skips_issue_without_catalog_pr(self) -> None:
        """Should NOT create issue for catalog-destined test case without generated script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cases_dir = Path(tmpdir)

            # No generated_script_path, so no catalog PR will be created
            (test_cases_dir / "my_test_cases.yaml").write_text(
                """test_cases:
  - title: Test Case 1
    purpose: Test purpose
    metadata:
      catalog:
        destined: true
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

            assert results["issues_created"] == 0
            assert results["catalog_prs_created"] == 0
            mock_project_adapter.create_issue.assert_not_called()

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
    generated_script_path: {script_path}
    metadata:
      project_tracking:
        issue_number: 1
        issue_url: https://url
      catalog:
        destined: true
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
