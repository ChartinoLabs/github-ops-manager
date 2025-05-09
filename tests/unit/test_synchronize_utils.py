"""Contains unit tests for the synchronize utils."""

from unittest.mock import MagicMock

import pytest
from githubkit.versions.latest.models import IssuePropLabelsItemsOneof1, Label

from github_ops_manager.synchronize.models import SyncDecision
from github_ops_manager.synchronize.utils import compare_github_field, compare_label_sets, extract_label_names, value_is_noney


def make_label_mock(name: str) -> MagicMock:
    """Create a mock for a Label object."""
    mock = MagicMock(spec=Label)
    mock.name = name
    return mock


def make_issue_prop_label_mock(name: str) -> MagicMock:
    """Create a mock for an IssuePropLabelsItemsOneof1 object."""
    mock = MagicMock(spec=IssuePropLabelsItemsOneof1)
    mock.name = name
    return mock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),
        ([], True),
        ("", True),
        ({}, True),
        ([1, 2, 3], False),
        ("non-empty", False),
        ({"key": "value"}, False),
        (0, False),
        (False, False),
    ],
)
async def test_value_is_noney(value: object, expected: bool) -> None:
    """Test the value_is_noney function."""
    result = await value_is_noney(value)
    assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "desired, github, expected",
    [
        (None, None, SyncDecision.NOOP),
        ([], [], SyncDecision.NOOP),
        ("", "", SyncDecision.NOOP),
        ({}, {}, SyncDecision.NOOP),
        (None, [1], SyncDecision.CREATE),
        ([], "non-empty", SyncDecision.CREATE),
        ("", [1, 2], SyncDecision.CREATE),
        ({}, {"key": "value"}, SyncDecision.CREATE),
        ([1, 2], None, SyncDecision.UPDATE),
        ("non-empty", None, SyncDecision.UPDATE),
        ({"key": "value"}, None, SyncDecision.UPDATE),
        ([1, 2], [1, 2], SyncDecision.NOOP),
        ("foo", "foo", SyncDecision.NOOP),
        ({"a": 1}, {"a": 1}, SyncDecision.NOOP),
        ([1, 2], [2, 1], SyncDecision.UPDATE),
        ("foo", "bar", SyncDecision.UPDATE),
        ({"a": 1}, {"a": 2}, SyncDecision.UPDATE),
        ({"key": "value"}, {"key": "value"}, SyncDecision.NOOP),
        ({"key": "value"}, {"key": "value", "extra": "extra"}, SyncDecision.UPDATE),
    ],
)
async def test_compare_github_field(desired: object, github: object, expected: SyncDecision) -> None:
    """Test the compare_github_field function."""
    result = await compare_github_field(desired, github)
    assert result == expected


@pytest.mark.parametrize(
    "labels,expected",
    [
        (["bug", "feature"], {"bug", "feature"}),
        ([make_label_mock("bug"), make_label_mock("feature")], {"bug", "feature"}),
        ([make_issue_prop_label_mock("bug"), make_issue_prop_label_mock("feature")], {"bug", "feature"}),
        ([{"name": "bug"}, {"name": "feature"}], {"bug", "feature"}),
        (["bug", make_label_mock("feature"), {"name": "enhancement"}], {"bug", "feature", "enhancement"}),
        (["bug", make_issue_prop_label_mock("feature"), {"name": "enhancement"}], {"bug", "feature", "enhancement"}),
        ([], set()),
    ],
)
def test_extract_label_names(labels: list, expected: set[str]) -> None:
    """Test the extract_label_names function."""
    result = extract_label_names(labels)
    assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "desired,github,expected",
    [
        ([], [], SyncDecision.NOOP),
        (None, None, SyncDecision.NOOP),
        (["bug"], ["bug"], SyncDecision.NOOP),
        (["bug", "feature"], ["feature", "bug"], SyncDecision.NOOP),
        (["bug"], ["feature"], SyncDecision.UPDATE),
        (["bug", "feature"], ["bug"], SyncDecision.UPDATE),
        (["bug"], ["bug", "feature"], SyncDecision.UPDATE),
        ([], ["bug"], SyncDecision.UPDATE),
        (["bug"], [], SyncDecision.UPDATE),
        (["bug"], None, SyncDecision.UPDATE),
        (None, ["bug"], SyncDecision.UPDATE),
        (["bug"], [make_label_mock("bug")], SyncDecision.NOOP),
        (["bug"], [make_label_mock("feature")], SyncDecision.UPDATE),
        (["bug", "feature"], [make_label_mock("feature"), make_label_mock("bug")], SyncDecision.NOOP),
        (["bug"], ["bug", make_label_mock("feature")], SyncDecision.UPDATE),
        (["bug", "feature"], ["bug", {"name": "feature"}], SyncDecision.NOOP),
        (["bug"], ["bug", {"name": "feature"}], SyncDecision.UPDATE),
        (["bug"], [{"name": "bug"}], SyncDecision.NOOP),
        (["bug"], [{"name": "feature"}], SyncDecision.UPDATE),
        (["bug", "feature"], [{"name": "feature"}, {"name": "bug"}], SyncDecision.NOOP),
        (["bug"], [make_issue_prop_label_mock("bug")], SyncDecision.NOOP),
        (["bug"], [make_issue_prop_label_mock("feature")], SyncDecision.UPDATE),
        (["bug", "feature"], [make_issue_prop_label_mock("feature"), make_issue_prop_label_mock("bug")], SyncDecision.NOOP),
        (["bug"], ["bug", make_issue_prop_label_mock("feature")], SyncDecision.UPDATE),
        (["bug", "feature"], ["bug", {"name": "feature"}], SyncDecision.NOOP),
        (["bug"], ["bug", {"name": "feature"}], SyncDecision.UPDATE),
        (["bug"], [{"name": "bug"}], SyncDecision.NOOP),
        (["bug"], [{"name": "feature"}], SyncDecision.UPDATE),
        (["bug", "feature"], [{"name": "feature"}, {"name": "bug"}], SyncDecision.NOOP),
    ],
)
async def test_compare_label_sets(desired: list[str] | None, github: list | None, expected: SyncDecision) -> None:
    """Test the compare_label_sets function."""
    github_labels = github if github is not None else None
    result = await compare_label_sets(desired, github_labels)
    assert result == expected
