"""Contains unit tests for GitHub issue synchronization logic."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.synchronize.issues import compare_github_issue_field, decide_github_issue_label_sync_action, decide_github_issue_sync_action
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "desired_issues, existing_issues, expected_decisions",
    [
        pytest.param(
            [SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1)],
            [],
            [SyncDecision.CREATE],
            id="all issues need to be created",
        ),
        pytest.param(
            [SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1)],
            [SimpleNamespace(number=1, title="A", body="DIFFERENT", labels=["bug"], assignees=["alice"], milestone=1)],
            [SyncDecision.UPDATE],
            id="all issues need to be updated",
        ),
        pytest.param(
            [SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1)],
            [SimpleNamespace(number=1, title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1)],
            [SyncDecision.NOOP],
            id="all issues are up to date (noop)",
        ),
        pytest.param(
            # Composite: one create, one update, one noop
            [
                SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
                SimpleNamespace(title="B", body="B2", labels=["feature"], assignees=["bob"], milestone=2),
                SimpleNamespace(title="C", body="C3", labels=["enhancement"], assignees=["carol"], milestone=3),
            ],
            [
                SimpleNamespace(number=1, title="B", body="DIFFERENT", labels=["feature"], assignees=["bob"], milestone=2),  # needs update
                SimpleNamespace(number=2, title="C", body="C3", labels=["enhancement"], assignees=["carol"], milestone=3),  # noop
            ],
            [SyncDecision.CREATE, SyncDecision.UPDATE, SyncDecision.NOOP],
            id="composite: create, update, noop",
        ),
        pytest.param(
            # Composite: one create, one noop
            [
                SimpleNamespace(title="X", body="Y", labels=["bug"], assignees=["alice"], milestone=1),
                SimpleNamespace(title="Y", body="Y2", labels=["feature"], assignees=["bob"], milestone=2),
            ],
            [
                SimpleNamespace(number=3, title="Y", body="Y2", labels=["feature"], assignees=["bob"], milestone=2),  # noop
            ],
            [SyncDecision.CREATE, SyncDecision.NOOP],
            id="composite: create, noop",
        ),
    ],
)
async def test_sync_github_issues(
    desired_issues: list[Any],
    existing_issues: list[Any],
    expected_decisions: list[SyncDecision],
) -> None:
    """Test the sync_github_issues function."""
    # Mock the adapter
    adapter = AsyncMock(spec=GitHubKitAdapter)
    adapter.list_issues.return_value = existing_issues
    adapter.create_issue.return_value = SimpleNamespace(number=1, title="A")
    adapter.update_issue.return_value = None

    from github_ops_manager.synchronize.issues import sync_github_issues

    results = await sync_github_issues(desired_issues, adapter)
    # Extract the decisions from the results
    actual_decisions = [r.decision for r in results.results]
    assert actual_decisions == expected_decisions
    # Check that the correct adapter methods were called the expected number of times
    assert adapter.create_issue.call_count == expected_decisions.count(SyncDecision.CREATE)
    assert adapter.update_issue.call_count == expected_decisions.count(SyncDecision.UPDATE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "desired_label, github_labels, expected",
    [
        # Label present as string
        ("bug", ["bug", "feature"], SyncDecision.NOOP),
        ("enhancement", ["bug", "feature"], SyncDecision.UPDATE),
        # Label present as object with name
        ("bug", [SimpleNamespace(name="bug"), SimpleNamespace(name="feature")], SyncDecision.NOOP),
        ("enhancement", [SimpleNamespace(name="bug"), SimpleNamespace(name="feature")], SyncDecision.UPDATE),
        # Mixed types
        ("bug", ["bug", SimpleNamespace(name="feature")], SyncDecision.NOOP),
        ("feature", ["bug", SimpleNamespace(name="feature")], SyncDecision.NOOP),
        ("enhancement", ["bug", SimpleNamespace(name="feature")], SyncDecision.UPDATE),
        # Empty labels
        ("bug", [], SyncDecision.UPDATE),
    ],
)
async def test_decide_github_issue_label_sync_action(desired_label: str, github_labels: list[Any], expected: SyncDecision) -> None:
    """Test the decide_github_issue_label_sync_action function."""
    github_issue = SimpleNamespace(labels=github_labels)
    result = await decide_github_issue_label_sync_action(desired_label, github_issue)
    assert result == expected
