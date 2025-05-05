"""Unit tests for the YAMLProcessor class."""

from typing import Any
from unittest.mock import mock_open, patch

from _pytest.logging import LogCaptureFixture

from github_ops_manager.processing.yaml_processor import YAMLProcessor
from github_ops_manager.schemas.default_issue import IssueModel

VALID_YAML = """
issues:
  - title: Test Issue
    body: This is a test.
    labels: [bug, help wanted]
    assignees: [alice]
    milestone: v1.0
    state: open
"""

YAML_MISSING_ISSUES = """
not_issues:
  - title: Should not load
"""

YAML_EXTRA_FIELDS = """
issues:
  - title: Extra Field Issue
    body: Has extra
    foo: bar
"""

YAML_FIELD_MAPPING = """
issues:
  - my_title: Mapped Title
    body: Field mapping works
"""

YAML_INVALID_ISSUE = """
issues:
  - title: Valid
  - 12345
"""

YAML_VALIDATION_ERROR = """
issues:
  - title: Valid
  - title: 12345  # Should be str, not int
"""


def m_open(data: str) -> Any:
    """Mock open for testing."""
    return mock_open(read_data=data)


def test_load_valid_yaml() -> None:
    """Test loading a valid YAML file with all fields present."""
    processor = YAMLProcessor()
    with patch("builtins.open", m_open(VALID_YAML)), patch("builtins.exit"):
        issues = processor.load_issues(["dummy.yaml"])
    issues = [IssueModel.model_validate(issue) for issue in issues]
    assert len(issues) == 1
    assert issues[0].title == "Test Issue"
    assert issues[0].labels == ["bug", "help wanted"]
    assert issues[0].assignees == ["alice"]
    assert issues[0].milestone == "v1.0"
    assert issues[0].state == "open"


def test_missing_issues_key() -> None:
    """Test YAML file missing the 'issues' key returns an empty list."""
    processor = YAMLProcessor(raise_on_error=False)
    with patch("builtins.open", m_open(YAML_MISSING_ISSUES)), patch("builtins.exit"):
        issues = processor.load_issues(["dummy.yaml"])
    assert issues == []


def test_extra_fields_logged_and_ignored(caplog: LogCaptureFixture) -> None:
    """Test that extra fields are logged and ignored."""
    processor = YAMLProcessor()
    with patch("builtins.open", m_open(YAML_EXTRA_FIELDS)), patch("builtins.exit"):
        issues = processor.load_issues(["dummy.yaml"])
    issues = [IssueModel.model_validate(issue) for issue in issues]
    assert len(issues) == 1
    assert not hasattr(issues[0], "foo")
    # Check that a warning about extra fields was logged
    assert any(
        "Extra fields in issue will be ignored" in r for r in caplog.text.splitlines()
    )


def test_field_mapping() -> None:
    """Test that field mapping correctly renames fields."""
    processor = YAMLProcessor(field_mapping={"my_title": "title"})
    with patch("builtins.open", m_open(YAML_FIELD_MAPPING)), patch("builtins.exit"):
        issues = processor.load_issues(["dummy.yaml"])
    issues = [IssueModel.model_validate(issue) for issue in issues]
    assert len(issues) == 1
    assert issues[0].title == "Mapped Title"


def test_invalid_issue_entry(caplog: LogCaptureFixture) -> None:
    """Test that non-dict issue entries are skipped and logged."""
    processor = YAMLProcessor(raise_on_error=False)
    with patch("builtins.open", m_open(YAML_INVALID_ISSUE)), patch("builtins.exit"):
        issues = processor.load_issues(["dummy.yaml"])
    issues = [IssueModel.model_validate(issue) for issue in issues]
    # Only the valid dict should be loaded
    assert len(issues) == 1
    assert issues[0].title == "Valid"
    # Check that a warning about non-dict was logged
    assert any("Issue entry is not a dict" in r for r in caplog.text.splitlines())


def test_validation_error(caplog: LogCaptureFixture) -> None:
    """Test that validation errors are logged and invalid issues are skipped."""
    processor = YAMLProcessor(raise_on_error=False)
    with patch("builtins.open", m_open(YAML_VALIDATION_ERROR)), patch("builtins.exit"):
        issues = processor.load_issues(["dummy.yaml"])
    issues = [IssueModel.model_validate(issue) for issue in issues]
    # Only the valid issue should be loaded
    assert len(issues) == 1
    assert issues[0].title == "Valid"
    # Check that a validation error was logged
    assert any("Validation error for issue" in r for r in caplog.text.splitlines())
