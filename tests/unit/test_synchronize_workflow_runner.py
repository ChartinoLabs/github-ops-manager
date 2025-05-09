"""Contains unit tests for the processing workflow runner."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.synchronize.models import SyncDecision


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

    from github_ops_manager.synchronize.workflow_runner import sync_github_issues

    results = await sync_github_issues(desired_issues, adapter)
    # Extract the decisions from the results
    actual_decisions = [r.decision for r in results.results]
    assert actual_decisions == expected_decisions
    # Check that the correct adapter methods were called the expected number of times
    assert adapter.create_issue.call_count == expected_decisions.count(SyncDecision.CREATE)
    assert adapter.update_issue.call_count == expected_decisions.count(SyncDecision.UPDATE)
