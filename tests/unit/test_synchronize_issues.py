"""Contains unit tests for GitHub issue synchronization logic."""

from types import SimpleNamespace
from typing import Any

import pytest

from github_ops_manager.synchronize.issues import compare_github_issue_field, decide_github_issue_sync_action
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "desired, github, expected",
    [
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            None,
            SyncDecision.CREATE,
            id="create if github_issue is None",
        ),
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SyncDecision.NOOP,
            id="noop if all fields match",
        ),
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SimpleNamespace(title="A", body="DIFFERENT", labels=["bug"], assignees=["alice"], milestone=1),
            SyncDecision.UPDATE,
            id="update if body differs",
        ),
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SimpleNamespace(title="A", body="B", labels=["feature"], assignees=["alice"], milestone=1),
            SyncDecision.UPDATE,
            id="update if labels differ",
        ),
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["bob"], milestone=1),
            SyncDecision.UPDATE,
            id="update if assignees differ",
        ),
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=2),
            SyncDecision.UPDATE,
            id="update if milestone differs",
        ),
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SimpleNamespace(title="A", body="B", labels=["bug", "feature"], assignees=["alice"], milestone=1),
            SyncDecision.UPDATE,
            id="update if label needs to be removed",
        ),
    ],
)
async def test_decide_github_issue_sync_action(desired: Any, github: Any, expected: SyncDecision) -> None:
    """Test the decide_github_issue_sync_action function."""
    result = await decide_github_issue_sync_action(desired, github)
    assert result == expected
