"""Unit tests for issues_yaml_migration module.

⚠️ DEPRECATION NOTICE: These tests are for the issues.yaml migration module
which should be removed post-migration along with the module itself.
"""

import tempfile
from pathlib import Path
from typing import Any

from github_ops_manager.synchronize.issues_yaml_migration import (
    extract_issue_metadata_from_issues_yaml,
    extract_pr_metadata_from_issues_yaml,
    find_matching_test_case,
    is_issue_migrated,
    load_issues_yaml,
    mark_issue_as_migrated,
    migrate_issue_to_test_case,
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
            f.write("issues:\n  - title: Test Issue\n    number: 123\n")
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


class TestExtractIssueMetadataFromIssuesYaml:
    """Tests for extract_issue_metadata_from_issues_yaml function."""

    def test_extracts_issue_number_and_url(self) -> None:
        """Should extract issue number and URL."""
        issue: dict[str, Any] = {
            "title": "Test Issue",
            "number": 123,
            "url": "https://github.com/org/repo/issues/123",
        }
        result = extract_issue_metadata_from_issues_yaml(issue)
        assert result is not None
        assert result["issue_number"] == 123
        assert result["issue_url"] == "https://github.com/org/repo/issues/123"

    def test_returns_empty_url_when_missing(self) -> None:
        """Should return empty URL when not present."""
        issue: dict[str, Any] = {"title": "Test Issue", "number": 123}
        result = extract_issue_metadata_from_issues_yaml(issue)
        assert result is not None
        assert result["issue_number"] == 123
        assert result["issue_url"] == ""

    def test_returns_none_when_no_number(self) -> None:
        """Should return None when issue number is missing."""
        issue: dict[str, Any] = {"title": "Test Issue"}
        result = extract_issue_metadata_from_issues_yaml(issue)
        assert result is None


class TestExtractPrMetadataFromIssuesYaml:
    """Tests for extract_pr_metadata_from_issues_yaml function."""

    def test_extracts_pr_metadata(self) -> None:
        """Should extract PR number, URL, and branch."""
        issue: dict[str, Any] = {
            "title": "Test Issue",
            "pull_request": {
                "number": 456,
                "url": "https://github.com/org/repo/pull/456",
                "branch": "feature/test",
            },
        }
        result = extract_pr_metadata_from_issues_yaml(issue)
        assert result is not None
        assert result["pr_number"] == 456
        assert result["pr_url"] == "https://github.com/org/repo/pull/456"
        assert result["pr_branch"] == "feature/test"

    def test_returns_empty_strings_for_missing_fields(self) -> None:
        """Should return empty strings for missing optional fields."""
        issue: dict[str, Any] = {
            "title": "Test Issue",
            "pull_request": {"number": 456},
        }
        result = extract_pr_metadata_from_issues_yaml(issue)
        assert result is not None
        assert result["pr_number"] == 456
        assert result["pr_url"] == ""
        assert result["pr_branch"] == ""

    def test_returns_none_when_no_pull_request(self) -> None:
        """Should return None when pull_request is missing."""
        issue: dict[str, Any] = {"title": "Test Issue"}
        result = extract_pr_metadata_from_issues_yaml(issue)
        assert result is None

    def test_returns_none_when_pr_has_no_number(self) -> None:
        """Should return None when PR number is missing."""
        issue: dict[str, Any] = {
            "title": "Test Issue",
            "pull_request": {"url": "https://url"},
        }
        result = extract_pr_metadata_from_issues_yaml(issue)
        assert result is None


class TestMigrateIssueToTestCase:
    """Tests for migrate_issue_to_test_case function."""

    def test_migrates_issue_metadata_to_test_case(self) -> None:
        """Should migrate issue metadata to test case."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create test case file
            test_case_file = tmppath / "my_test_cases.yaml"
            test_case_file.write_text("test_cases:\n  - title: Test Issue\n")

            issue: dict[str, Any] = {
                "title": "Test Issue",
                "number": 123,
                "url": "https://github.com/org/repo/issues/123",
            }
            test_case: dict[str, Any] = {
                "title": "Test Issue",
                "_source_file": str(test_case_file),
            }

            result = migrate_issue_to_test_case(issue, test_case, "https://github.com/org/repo")

            assert result is True
            assert test_case["project_issue_number"] == 123
            assert test_case["project_issue_url"] == "https://github.com/org/repo/issues/123"

    def test_migrates_pr_metadata_to_test_case(self) -> None:
        """Should migrate PR metadata to test case."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create test case file
            test_case_file = tmppath / "my_test_cases.yaml"
            test_case_file.write_text("test_cases:\n  - title: Test Issue\n")

            issue: dict[str, Any] = {
                "title": "Test Issue",
                "number": 123,
                "url": "https://github.com/org/repo/issues/123",
                "pull_request": {
                    "number": 456,
                    "url": "https://github.com/org/repo/pull/456",
                    "branch": "feature/test",
                },
            }
            test_case: dict[str, Any] = {
                "title": "Test Issue",
                "_source_file": str(test_case_file),
            }

            result = migrate_issue_to_test_case(issue, test_case, "https://github.com/org/repo")

            assert result is True
            assert test_case["project_pr_number"] == 456
            assert test_case["project_pr_url"] == "https://github.com/org/repo/pull/456"
            assert test_case["project_pr_branch"] == "feature/test"

    def test_returns_false_when_no_metadata(self) -> None:
        """Should return False when no metadata to migrate."""
        issue: dict[str, Any] = {"title": "Test Issue"}
        test_case: dict[str, Any] = {"title": "Test Issue"}

        result = migrate_issue_to_test_case(issue, test_case, "https://github.com/org/repo")

        assert result is False

    def test_returns_false_when_no_title(self) -> None:
        """Should return False when issue has no title."""
        issue: dict[str, Any] = {"number": 123}
        test_case: dict[str, Any] = {"title": "Test Issue"}

        result = migrate_issue_to_test_case(issue, test_case, "https://github.com/org/repo")

        assert result is False


class TestRunIssuesYamlMigration:
    """Tests for run_issues_yaml_migration function."""

    def test_returns_zero_counts_for_nonexistent_file(self) -> None:
        """Should return zero counts when issues.yaml doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_issues_yaml_migration(
                issues_yaml_path=Path(tmpdir) / "nonexistent.yaml",
                test_cases_dir=Path(tmpdir),
                repo_url="https://github.com/org/repo",
            )

            assert result["total_issues"] == 0
            assert result["already_migrated"] == 0
            assert result["newly_migrated"] == 0
            assert result["skipped_no_match"] == 0
            assert result["skipped_no_metadata"] == 0
            assert result["errors"] == []

    def test_returns_error_when_no_test_cases(self) -> None:
        """Should report error when no test cases found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create issues.yaml
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text("issues:\n  - title: Test Issue\n    number: 123\n")

            result = run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
            )

            assert result["total_issues"] == 1
            assert len(result["errors"]) == 1
            assert "No test cases found" in result["errors"][0]

    def test_skips_already_migrated_issues(self) -> None:
        """Should skip issues marked as migrated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create issues.yaml with migrated issue
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text("issues:\n  - title: Test Issue\n    number: 123\n    migrated: true\n")
            # Create test case file
            test_cases_file = tmppath / "my_test_cases.yaml"
            test_cases_file.write_text("test_cases:\n  - title: Test Issue\n")

            result = run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
            )

            assert result["total_issues"] == 1
            assert result["already_migrated"] == 1
            assert result["newly_migrated"] == 0

    def test_skips_issues_with_no_metadata(self) -> None:
        """Should skip issues without metadata to migrate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create issues.yaml without issue number
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text("issues:\n  - title: Test Issue\n")
            # Create test case file
            test_cases_file = tmppath / "my_test_cases.yaml"
            test_cases_file.write_text("test_cases:\n  - title: Test Issue\n")

            result = run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
            )

            assert result["total_issues"] == 1
            assert result["skipped_no_metadata"] == 1
            assert result["newly_migrated"] == 0

    def test_skips_issues_with_no_matching_test_case(self) -> None:
        """Should skip issues with no matching test case."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create issues.yaml
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text("issues:\n  - title: Test Issue\n    number: 123\n")
            # Create test case file with different title
            test_cases_file = tmppath / "my_test_cases.yaml"
            test_cases_file.write_text("test_cases:\n  - title: Different Title\n")

            result = run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
            )

            assert result["total_issues"] == 1
            assert result["skipped_no_match"] == 1
            assert result["newly_migrated"] == 0

    def test_successfully_migrates_issue(self) -> None:
        """Should successfully migrate issue to test case."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create issues.yaml
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text("issues:\n  - title: Test Issue\n    number: 123\n    url: https://github.com/org/repo/issues/123\n")
            # Create test case file
            test_cases_file = tmppath / "my_test_cases.yaml"
            test_cases_file.write_text("test_cases:\n  - title: Test Issue\n")

            result = run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
            )

            assert result["total_issues"] == 1
            assert result["newly_migrated"] == 1
            assert result["errors"] == []

            # Verify issues.yaml was updated with migrated marker
            from github_ops_manager.utils.yaml import load_yaml_file

            updated_issues = load_yaml_file(issues_yaml)
            assert updated_issues["issues"][0]["migrated"] is True

    def test_migrates_multiple_issues(self) -> None:
        """Should handle multiple issues in a single migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create issues.yaml with multiple issues
            issues_yaml = tmppath / "issues.yaml"
            issues_yaml.write_text(
                """issues:
  - title: Test Issue 1
    number: 123
  - title: Test Issue 2
    number: 456
  - title: Test Issue 3
    migrated: true
"""
            )
            # Create test case file
            test_cases_file = tmppath / "my_test_cases.yaml"
            test_cases_file.write_text(
                """test_cases:
  - title: Test Issue 1
  - title: Test Issue 2
  - title: Test Issue 3
"""
            )

            result = run_issues_yaml_migration(
                issues_yaml_path=issues_yaml,
                test_cases_dir=tmppath,
                repo_url="https://github.com/org/repo",
            )

            assert result["total_issues"] == 3
            assert result["already_migrated"] == 1
            assert result["newly_migrated"] == 2
            assert result["errors"] == []
