"""Contains unit tests for GitHub issue synchronization logic."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jinja2
import pytest

import github_ops_manager.synchronize.issues
from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.schemas.default_issue import IssueModel, IssuesYAMLModel
from github_ops_manager.synchronize.issues import (
    decide_github_issue_label_sync_action,
    decide_github_issue_sync_action,
    render_issue_bodies,
)
from github_ops_manager.synchronize.models import SyncDecision


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


@pytest.mark.asyncio
async def test_render_issue_bodies_success() -> None:
    """Test successful rendering of issue bodies using a mock template."""
    issues = [
        IssueModel(title="Test", body="old", data={"foo": "bar"}),
        IssueModel(title="NoData", body="should stay", data=None),
    ]
    model = IssuesYAMLModel(issue_template="fake_template.j2", issues=issues)
    mock_template = MagicMock()
    mock_template.render.side_effect = lambda **ctx: f"rendered: {ctx['title']}"
    with patch.object(github_ops_manager.synchronize.issues, "construct_jinja2_template", new=AsyncMock(return_value=mock_template)):
        result = await render_issue_bodies(model)
    assert result.issues[0].body == "rendered: Test"
    assert result.issues[1].body == "should stay"


@pytest.mark.asyncio
async def test_render_issue_bodies_template_syntax_error() -> None:
    """Test that a jinja2.TemplateSyntaxError is properly raised and logged."""
    issues = [IssueModel(title="Test", body="old", data={"foo": "bar"})]
    model = IssuesYAMLModel(issue_template="bad_template.j2", issues=issues)
    with patch.object(
        github_ops_manager.synchronize.issues, "construct_jinja2_template", new=AsyncMock(side_effect=jinja2.TemplateSyntaxError("bad syntax", 1))
    ):
        with pytest.raises(jinja2.TemplateSyntaxError):
            await render_issue_bodies(model)


@pytest.mark.asyncio
async def test_render_issue_bodies_undefined_error() -> None:
    """Test that a jinja2.UndefinedError is properly raised and logged during rendering."""
    issues = [IssueModel(title="Test", body="old", data={"foo": "bar"})]
    model = IssuesYAMLModel(issue_template="fake_template.j2", issues=issues)
    mock_template = MagicMock()
    mock_template.render.side_effect = jinja2.UndefinedError("undefined var")
    with patch.object(github_ops_manager.synchronize.issues, "construct_jinja2_template", new=AsyncMock(return_value=mock_template)):
        with pytest.raises(jinja2.UndefinedError):
            await render_issue_bodies(model)
