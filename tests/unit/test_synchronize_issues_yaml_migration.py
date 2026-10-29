"""Unit tests for issues_yaml_migration module.

⚠️ DEPRECATION NOTICE: These tests are for the issues.yaml migration module
which should be removed post-migration along with the module itself.
"""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from github_ops_manager.synchronize.issues_yaml_migration import (
    find_github_issue_by_title,
    find_github_pr_by_title,
    find_matching_test_case,
    is_issue_migrated,
    load_issues_yaml,
    mark_issue_as_migrated,
    migrate_issue_from_github,
    run_issues_yaml_migration,
)


class TestLoadIssuesYaml:
    """Tests for load_issues_yaml function."""

    def test_returns_none_for_nonexistent_file(self) -> None:
        """Should return None if file doesn't exist."""
        result = load_issues_yaml(Path("/nonexistent/issues.yaml"))
        assert result is None

    def test_loads_valid_issues_yaml(self) -> None:
        """Should load valid issues.yaml file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("issues:\n  - title: Test Issue\n")
            f.flush()
            filepath = Path(f.name)

        try:
            result = load_issues_yaml(filepath)
            assert result is not None
            assert "issues" in result
            assert len(result["issues"]) == 1
            assert result["issues"][0]["title"] == "Test Issue"
        finally:
            filepath.unlink()

    def test_returns_none_for_invalid_yaml(self) -> None:
        """Should return None if YAML is not a dictionary."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("- item1\n- item2\n")
            f.flush()
            filepath = Path(f.name)

        try:
            result = load_issues_yaml(filepath)
            assert result is None
        finally:
            filepath.unlink()

    def test_returns_none_for_missing_issues_key(self) -> None:
        """Should return None if 'issues' key is missing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("other_key: value\n")
            f.flush()
            filepath = Path(f.name)

        try:
            result = load_issues_yaml(filepath)
            assert result is None
        finally:
            filepath.unlink()


class TestIsMigrated:
    """Tests for is_issue_migrated function."""

    def test_returns_false_when_no_migrated_field(self) -> None:
        """Should return False when migrated field is absent."""
        issue: dict[str, Any] = {"title": "Test Issue"}
        assert is_issue_migrated(issue) is False

    def test_returns_false_when_migrated_is_false(self) -> None:
        """Should return False when migrated is explicitly False."""
        issue: dict[str, Any] = {"title": "Test Issue", "migrated": False}
        assert is_issue_migrated(issue) is False

    def test_returns_true_when_migrated_is_true(self) -> None:
        """Should return True when migrated is True."""
        issue: dict[str, Any] = {"title": "Test Issue", "migrated": True}
        assert is_issue_migrated(issue) is True

    def test_returns_false_when_migrated_is_not_boolean(self) -> None:
        """Should return False for non-boolean migrated values."""
        issue: dict[str, Any] = {"title": "Test Issue", "migrated": "yes"}
        assert is_issue_migrated(issue) is False


class TestMarkIssueAsMigrated:
    """Tests for mark_issue_as_migrated function."""

    def test_sets_migrated_to_true(self) -> None:
        """Should set migrated field to True."""
        issue: dict[str, Any] = {"title": "Test Issue"}
        mark_issue_as_migrated(issue)
        assert issue["migrated"] is True

    def test_overwrites_existing_false_value(self) -> None:
        """Should overwrite False value with True."""
        issue: dict[str, Any] = {"title": "Test Issue", "migrated": False}
        mark_issue_as_migrated(issue)
        assert issue["migrated"] is True


class TestFindMatchingTestCase:
    """Tests for find_matching_test_case function."""

    def test_finds_matching_test_case_by_title(self) -> None:
        """Should find test case with matching title."""
        test_cases = [
            {"title": "Test Case 1"},
            {"title": "Test Case 2"},
            {"title": "Test Case 3"},
        ]
        result = find_matching_test_case("Test Case 2", test_cases)
        assert result is not None
        assert result["title"] == "Test Case 2"

    def test_returns_none_when_no_match(self) -> None:
        """Should return None when no test case matches."""
        test_cases = [
            {"title": "Test Case 1"},
            {"title": "Test Case 2"},
        ]
        result = find_matching_test_case("Nonexistent", test_cases)
        assert result is None

    def test_returns_none_for_empty_list(self) -> None:
        """Should return None for empty test cases list."""
        result = find_matching_test_case("Test Case", [])
        assert result is None

    def test_requires_exact_match(self) -> None:
        """Should require exact title match (case-sensitive)."""
        test_cases = [{"title": "Test Case 1"}]
        result = find_matching_test_case("test case 1", test_cases)
        assert result is None


class TestFindGithubIssueByTitle:
    """Tests for find_github_issue_by_title function."""

    def test_finds_matching_issue(self) -> None:
        """Should find GitHub issue with matching title."""
        mock_issue1 = MagicMock()
        mock_issue1.title = "Test Issue 1"
        mock_issue2 = MagicMock()
        mock_issue2.title = "Test Issue 2"

        result = find_github_issue_by_title("Test Issue 2", [mock_issue1, mock_issue2])
        assert result is mock_issue2

    def test_returns_none_when_no_match(self) -> None:
        """Should return None when no issue matches."""
        mock_issue = MagicMock()
        mock_issue.title = "Other Issue"

        result = find_github_issue_by_title("Test Issue", [mock_issue])
        assert result is None

    def test_returns_none_for_empty_list(self) -> None:
        """Should return None for empty issues list."""
        result = find_github_issue_by_title("Test Issue", [])
        assert result is None


class TestFindGithubPrByTitle:
    """Tests for find_github_pr_by_title function."""

    def test_finds_matching_pr_with_legacy_format(self) -> None:
        """Should find PR with legacy title format."""
        mock_pr = MagicMock()
        mock_pr.title = "GenAI, Review: Test Issue"

        result = find_github_pr_by_title("Test Issue", [mock_pr])
        assert result is mock_pr

    def test_returns_none_when_no_match(self) -> None:
        """Should return None when no PR matches."""
        mock_pr = MagicMock()
        mock_pr.title = "Some Other PR"

        result = find_github_pr_by_title("Test Issue", [mock_pr])
        assert result is None

    def test_returns_none_for_exact_title_match(self) -> None:
        """Should not match PR with exact issue title (needs prefix)."""
        mock_pr = MagicMock()
        mock_pr.title = "Test Issue"  # Missing "GenAI, Review: " prefix

        result = find_github_pr_by_title("Test Issue", [mock_pr])
        assert result is None


class TestMigrateIssueFromGithub:
    """Tests for migrate_issue_from_github function."""

    @pytest.mark.asyncio
    async def test_migrates_issue_metadata(self) -> None:
        """Should migrate issue metadata from GitHub to test case in nested structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            test_case_file = tmppath / "my_test_cases.yaml"
            test_case_file.write_text("test_cases:\n  - title: Test Issue\n")

            issue: dict[str, Any] = {"title": "Test Issue"}
            test_case: dict[str, Any] = {
                "title": "Test Issue",
                "_source_file": str(test_case_file),
            }

            mock_gh_issue = MagicMock()
            mock_gh_issue.title = "Test Issue"
            mock_gh_issue.number = 123
            mock_gh_issue.html_url = "https://github.com/org/repo/issues/123"

            result = await migrate_issue_from_github(
                issue,
                test_case,
                [mock_gh_issue],
                [],
                "https://github.com/org/repo",
            )

            assert result is True
            assert test_case["metadata"]["project_tracking"]["issue_number"] == 123
            assert test_case["metadata"]["project_tracking"]["issue_url"] == "https://github.com/org/repo/issues/123"

    @pytest.mark.asyncio
    async def test_migrates_pr_metadata(self) -> None:
        """Should migrate PR metadata from GitHub to test case in nested structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            test_case_file = tmppath / "my_test_cases.yaml"
            test_case_file.write_text("test_cases:\n  - title: Test Issue\n")

            issue: dict[str, Any] = {"title": "Test Issue"}
            test_case: dict[str, Any] = {
                "title": "Test Issue",
                "_source_file": str(test_case_file),
            }

            mock_gh_pr = MagicMock()
            mock_gh_pr.title = "GenAI, Review: Test Issue"
            mock_gh_pr.number = 456
            mock_gh_pr.html_url = "https://github.com/org/repo/pull/456"
            mock_gh_pr.head.ref = "feature/test"

            result = await migrate_issue_from_github(
                issue,
                test_case,
                [],
                [mock_gh_pr],
                "https://github.com/org/repo",
            )

            assert result is True
            assert test_case["metadata"]["project_tracking"]["pr_number"] == 456
            assert test_case["metadata"]["project_tracking"]["pr_url"] == "https://github.com/org/repo/pull/456"
            assert test_case["metadata"]["project_tracking"]["pr_branch"] == "feature/test"

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found_in_github(self) -> None:
        """Should return False when no matching issue/PR in GitHub."""
        issue: dict[str, Any] = {"title": "Test Issue"}
        test_case: dict[str, Any] = {"title": "Test Issue"}

        result = await migrate_issue_from_github(
            issue,
            test_case,
            [],  # No GitHub issues
            [],  # No GitHub PRs
            "https://github.com/org/repo",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_title(self) -> None:
        """Should return False when issue has no title."""
        issue: dict[str, Any] = {}  # No title
        test_case: dict[str, Any] = {"title": "Test Issue"}

        result = await migrate_issue_from_github(
            issue,
            test_case,
            [],
            [],
            "https://github.com/org/repo",
        )

        assert result is False


class TestRunIssuesYamlMigration:
    """Tests for run_issues_yaml_migration function."""

    @pytest.mark.asyncio
    async def test_returns_zero_counts_for_nonexistent_file(self) -> None:
        """Should return zero counts when issues.yaml doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_adapter = AsyncMock()

            result = await run_issues_yaml_migration(
                issues_yaml_path=Path(tmpdir) / "nonexistent.yaml",
                test_cases_dir=Path(tmpdir),
                repo_url="https://github.com/org/repo",
                github_adapter=mock_adapter,
            )

            assert result["total_issues"] == 0
            assert result["already_migrated"] == 0
            assert result["newly_migrated"] == 0
            assert result["skipped_no_match"] == 0
            assert result["skipped_not_in_github"] == 0
            assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_returns_error_when_no_test_cases(self) -> None:
        """Should report error when no test cases found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text("issues:\n  - title: Test Issue\n")

            mock_adapter = AsyncMock()

            result = await run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
                github_adapter=mock_adapter,
            )

            assert result["total_issues"] == 1
            assert len(result["errors"]) == 1
            assert "No test cases found" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_skips_already_migrated_issues(self) -> None:
        """Should skip issues marked as migrated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text("issues:\n  - title: Test Issue\n    migrated: true\n")
            test_cases_file = tmppath / "my_test_cases.yaml"
            test_cases_file.write_text("test_cases:\n  - title: Test Issue\n")

            mock_adapter = AsyncMock()
            mock_adapter.list_issues.return_value = []
            mock_adapter.list_pull_requests.return_value = []

            result = await run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
                github_adapter=mock_adapter,
            )

            assert result["total_issues"] == 1
            assert result["already_migrated"] == 1
            assert result["newly_migrated"] == 0

    @pytest.mark.asyncio
    async def test_skips_issues_not_in_github(self) -> None:
        """Should skip issues not found in GitHub."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text("issues:\n  - title: Test Issue\n")
            test_cases_file = tmppath / "my_test_cases.yaml"
            test_cases_file.write_text("test_cases:\n  - title: Test Issue\n")

            mock_adapter = AsyncMock()
            mock_adapter.list_issues.return_value = []  # No matching issues
            mock_adapter.list_pull_requests.return_value = []

            result = await run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
                github_adapter=mock_adapter,
            )

            assert result["total_issues"] == 1
            assert result["skipped_not_in_github"] == 1
            assert result["newly_migrated"] == 0

    @pytest.mark.asyncio
    async def test_skips_issues_with_no_matching_test_case(self) -> None:
        """Should skip issues with no matching test case."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text("issues:\n  - title: Test Issue\n")
            test_cases_file = tmppath / "my_test_cases.yaml"
            test_cases_file.write_text("test_cases:\n  - title: Different Title\n")

            mock_adapter = AsyncMock()
            mock_adapter.list_issues.return_value = []
            mock_adapter.list_pull_requests.return_value = []

            result = await run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
                github_adapter=mock_adapter,
            )

            assert result["total_issues"] == 1
            assert result["skipped_no_match"] == 1
            assert result["newly_migrated"] == 0

    @pytest.mark.asyncio
    async def test_successfully_migrates_issue_from_github(self) -> None:
        """Should successfully migrate issue found in GitHub."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text("issues:\n  - title: Test Issue\n")
            test_cases_file = tmppath / "my_test_cases.yaml"
            test_cases_file.write_text("test_cases:\n  - title: Test Issue\n")

            mock_gh_issue = MagicMock()
            mock_gh_issue.title = "Test Issue"
            mock_gh_issue.number = 123
            mock_gh_issue.html_url = "https://github.com/org/repo/issues/123"

            mock_adapter = AsyncMock()
            mock_adapter.list_issues.return_value = [mock_gh_issue]
            mock_adapter.list_pull_requests.return_value = []

            result = await run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
                github_adapter=mock_adapter,
            )

            assert result["total_issues"] == 1
            assert result["newly_migrated"] == 1
            assert result["errors"] == []

            # Verify issues.yaml was updated with migrated marker
            from github_ops_manager.utils.yaml import load_yaml_file

            updated_issues = load_yaml_file(issues_yaml)
            assert updated_issues["issues"][0]["migrated"] is True

    @pytest.mark.asyncio
    async def test_migrates_multiple_issues(self) -> None:
        """Should handle multiple issues in a single migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text(
                """issues:
  - title: Test Issue 1
  - title: Test Issue 2
  - title: Test Issue 3
    migrated: true
"""
            )
            test_cases_file = tmppath / "my_test_cases.yaml"
            test_cases_file.write_text(
                """test_cases:
  - title: Test Issue 1
  - title: Test Issue 2
  - title: Test Issue 3
"""
            )

            mock_gh_issue1 = MagicMock()
            mock_gh_issue1.title = "Test Issue 1"
            mock_gh_issue1.number = 1
            mock_gh_issue1.html_url = "https://github.com/org/repo/issues/1"

            mock_gh_issue2 = MagicMock()
            mock_gh_issue2.title = "Test Issue 2"
            mock_gh_issue2.number = 2
            mock_gh_issue2.html_url = "https://github.com/org/repo/issues/2"

            mock_adapter = AsyncMock()
            mock_adapter.list_issues.return_value = [mock_gh_issue1, mock_gh_issue2]
            mock_adapter.list_pull_requests.return_value = []

            result = await run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
                github_adapter=mock_adapter,
            )

            assert result["total_issues"] == 3
            assert result["already_migrated"] == 1
            assert result["newly_migrated"] == 2
            assert result["errors"] == []
