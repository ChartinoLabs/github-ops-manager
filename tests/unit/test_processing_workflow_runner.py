"""Contains unit tests for the processing workflow runner."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.models import IssueSyncDecision
from github_ops_manager.processing.workflow_runner import decide_github_issue_sync_action


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "desired, github, expected",
    [
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            None,
            IssueSyncDecision.CREATE,
            id="create if github_issue is None",
        ),
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            IssueSyncDecision.NOOP,
            id="noop if all fields match",
        ),
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SimpleNamespace(title="A", body="DIFFERENT", labels=["bug"], assignees=["alice"], milestone=1),
            IssueSyncDecision.UPDATE,
            id="update if body differs",
        ),
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SimpleNamespace(title="A", body="B", labels=["feature"], assignees=["alice"], milestone=1),
            IssueSyncDecision.UPDATE,
            id="update if labels differ",
        ),
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["bob"], milestone=1),
            IssueSyncDecision.UPDATE,
            id="update if assignees differ",
        ),
        pytest.param(
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1),
            SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=2),
            IssueSyncDecision.UPDATE,
            id="update if milestone differs",
        ),
    ],
)
async def test_decide_github_issue_sync_action(desired: Any, github: Any, expected: IssueSyncDecision) -> None:
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
            [IssueSyncDecision.CREATE],
            id="all issues need to be created",
        ),
        pytest.param(
            [SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1)],
            [SimpleNamespace(number=1, title="A", body="DIFFERENT", labels=["bug"], assignees=["alice"], milestone=1)],
            [IssueSyncDecision.UPDATE],
            id="all issues need to be updated",
        ),
        pytest.param(
            [SimpleNamespace(title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1)],
            [SimpleNamespace(number=1, title="A", body="B", labels=["bug"], assignees=["alice"], milestone=1)],
            [IssueSyncDecision.NOOP],
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
            [IssueSyncDecision.CREATE, IssueSyncDecision.UPDATE, IssueSyncDecision.NOOP],
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
            [IssueSyncDecision.CREATE, IssueSyncDecision.NOOP],
            id="composite: create, noop",
        ),
    ],
)
async def test_sync_github_issues(
    desired_issues: list[Any],
    existing_issues: list[Any],
    expected_decisions: list[IssueSyncDecision],
) -> None:
    """Test the sync_github_issues function."""
    # Mock the adapter
    adapter = AsyncMock(spec=GitHubKitAdapter)
    adapter.list_issues.return_value = existing_issues
    adapter.create_issue.return_value = SimpleNamespace(number=1, title="A")
    adapter.update_issue.return_value = None

    from github_ops_manager.processing.workflow_runner import sync_github_issues

    results = await sync_github_issues(desired_issues, adapter)
    # Extract the decisions from the results
    actual_decisions = [r.decision for r in results.results]
    assert actual_decisions == expected_decisions
    # Check that the correct adapter methods were called the expected number of times
    assert adapter.create_issue.call_count == expected_decisions.count(IssueSyncDecision.CREATE)
    assert adapter.update_issue.call_count == expected_decisions.count(IssueSyncDecision.UPDATE)
