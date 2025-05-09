"""Contains unit tests for GitHub issue synchronization logic."""

import pytest

from github_ops_manager.synchronize.issues import compare_github_issue_field
from github_ops_manager.synchronize.models import SyncDecision


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
async def test_compare_github_issue_field(desired: object, github: object, expected: SyncDecision) -> None:
    """Test the compare_github_issue_field function."""
    result = await compare_github_issue_field(desired, github)
    assert result == expected
