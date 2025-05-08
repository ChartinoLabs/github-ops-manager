"""Unit tests for utility helper functions: slugify_title and generate_branch_name."""

import pytest

from github_ops_manager.utils.helpers import generate_branch_name, slugify_title


@pytest.mark.parametrize(
    "input_title,expected",
    [
        ("Hello World!", "hello-world"),
        ("A  B  C", "a-b-c"),
        ("Python_3.10+ is cool!", "python-3-10-is-cool"),
        ("  --foo--bar--  ", "foo-bar"),
        ("", ""),
        ("123", "123"),
        ("foo_bar baz", "foo-bar-baz"),
    ],
)
def test_slugify_title(input_title: str, expected: str) -> None:
    """Test slugify_title with various input cases."""
    assert slugify_title(input_title) == expected


@pytest.mark.parametrize(
    "issue_id,title,prefix,expected",
    [
        (123, "Hello World!", "feature", "feature/123-hello-world"),
        ("42", "A B C", "bugfix", "bugfix/42-a-b-c"),
        (0, "Test", "feature", "feature/0-test"),
        ("x", "Y Z", "hotfix", "hotfix/x-y-z"),
    ],
)
def test_generate_branch_name(issue_id: str | int, title: str, prefix: str, expected: str) -> None:
    """Test generate_branch_name with various ids, titles, and prefixes."""
    assert generate_branch_name(issue_id, title, prefix=prefix) == expected
