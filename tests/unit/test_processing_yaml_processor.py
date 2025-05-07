"""Unit tests for the YAMLProcessor class."""

import tempfile
from typing import Any
from unittest.mock import mock_open, patch

from github_ops_manager.processing.yaml_processor import YAMLProcessor
from github_ops_manager.schemas.default_issue import IssuesYAMLModel

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

YAML_WITH_TEMPLATE_AND_DATA = """
issue_template: ./template.md.j2
issues:
  - title: Template Issue
    data:
      foo: bar
    body: Should be replaced
  - title: No Data Issue
    body: Should not be replaced
"""

YAML_WITH_TEMPLATE_NO_DATA = """
issue_template: ./template.md.j2
issues:
  - title: Only Body
    body: Should not be replaced
"""

YAML_WITH_TEMPLATE_EMPTY_ISSUES = """
issue_template: ./template.md.j2
issues: []
"""


def m_open(data: str) -> Any:
    """Mock open for testing."""
    return mock_open(read_data=data)


def test_load_valid_yaml_model() -> None:
    """Test loading a valid YAML file with all fields present using load_issues_model."""
    processor = YAMLProcessor()
    with patch("builtins.open", m_open(VALID_YAML)), patch("builtins.exit"):
        model = processor.load_issues_model(["dummy.yaml"])
    assert isinstance(model, IssuesYAMLModel)
    assert model.issue_template is None
    assert len(model.issues) == 1
    issue = model.issues[0]
    assert issue.title == "Test Issue"
    assert issue.labels == ["bug", "help wanted"]
    assert issue.assignees == ["alice"]
    assert issue.milestone == "v1.0"
    assert issue.state == "open"


def test_load_yaml_model_with_template_and_data() -> None:
    """Test loading YAML with issue_template and issues with data fields using load_issues_model."""
    processor = YAMLProcessor()
    with tempfile.NamedTemporaryFile("w", suffix=".md.j2", delete=False) as tmp_template:
        tmp_template_path = tmp_template.name
    yaml_with_template = f"""
issue_template: {tmp_template_path}
issues:
  - title: Template Issue
    data:
      foo: bar
    body: Should be replaced
  - title: No Data Issue
    body: Should not be replaced
"""
    try:
        with patch("builtins.open", m_open(yaml_with_template)), patch("builtins.exit"):
            model = processor.load_issues_model(["dummy.yaml"])
        assert model.issue_template == tmp_template_path
        assert len(model.issues) == 2
        assert model.issues[0].title == "Template Issue"
        assert model.issues[0].data == {"foo": "bar"}
        assert model.issues[1].title == "No Data Issue"
        assert model.issues[1].data is None
    finally:
        import os

        os.remove(tmp_template_path)


def test_load_yaml_model_with_template_no_data() -> None:
    """Test loading YAML with issue_template and issues without data fields using load_issues_model."""
    processor = YAMLProcessor()
    with tempfile.NamedTemporaryFile("w", suffix=".md.j2", delete=False) as tmp_template:
        tmp_template_path = tmp_template.name
    yaml_with_template = f"""
issue_template: {tmp_template_path}
issues:
  - title: Only Body
    body: Should not be replaced
"""
    try:
        with patch("builtins.open", m_open(yaml_with_template)), patch("builtins.exit"):
            model = processor.load_issues_model(["dummy.yaml"])
        assert model.issue_template == tmp_template_path
        assert len(model.issues) == 1
        assert model.issues[0].title == "Only Body"
        assert model.issues[0].data is None
    finally:
        import os

        os.remove(tmp_template_path)


def test_load_yaml_model_with_template_empty_issues() -> None:
    """Test loading YAML with issue_template and empty issues list using load_issues_model."""
    processor = YAMLProcessor()
    with tempfile.NamedTemporaryFile("w", suffix=".md.j2", delete=False) as tmp_template:
        tmp_template_path = tmp_template.name
    yaml_with_template = f"""
issue_template: {tmp_template_path}
issues: []
"""
    try:
        with patch("builtins.open", m_open(yaml_with_template)), patch("builtins.exit"):
            model = processor.load_issues_model(["dummy.yaml"])
        assert model.issue_template == tmp_template_path
        assert model.issues == []
    finally:
        import os

        os.remove(tmp_template_path)


def test_load_yaml_model_with_template_backward_compat() -> None:
    """Test loading YAML with no issue_template still works (backward compatibility) using load_issues_model."""
    processor = YAMLProcessor()
    with patch("builtins.open", m_open(VALID_YAML)), patch("builtins.exit"):
        model = processor.load_issues_model(["dummy.yaml"])
    assert model.issue_template is None
    assert len(model.issues) == 1
    assert model.issues[0].title == "Test Issue"


def test_issue_template_file_does_not_exist_raises() -> None:
    """Test that specifying a non-existent issue_template file raises YAMLProcessingError if raise_on_error=True."""
    processor = YAMLProcessor(raise_on_error=True)
    fake_template = "/tmp/this_file_should_not_exist_123456789.md.j2"
    yaml_with_fake_template = f"""
issue_template: {fake_template}
issues:
  - title: "Test"
    body: "Body"
"""
    with patch("builtins.open", m_open(yaml_with_fake_template)), patch("builtins.exit"):
        try:
            processor.load_issues_model(["dummy.yaml"])
            raise AssertionError("Expected YAMLProcessingError to be raised")
        except Exception as e:
            from github_ops_manager.processing.exceptions import YAMLProcessingError

            assert isinstance(e, YAMLProcessingError)
            assert any("does not exist" in str(err.get("error", "")) for err in e.errors)


def test_issue_template_file_does_not_exist_no_raise() -> None:
    """Test that specifying a non-existent issue_template file logs error and includes error in result if raise_on_error=False."""
    processor = YAMLProcessor(raise_on_error=False)
    fake_template = "/tmp/this_file_should_not_exist_987654321.md.j2"
    yaml_with_fake_template = f"""
issue_template: {fake_template}
issues:
  - title: "Test"
    body: "Body"
"""
    with patch("builtins.open", m_open(yaml_with_fake_template)), patch("builtins.exit"):
        model = processor.load_issues_model(["dummy.yaml"])
    assert model.issue_template == fake_template
    assert len(model.issues) == 1
