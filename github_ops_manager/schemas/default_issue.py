"""Pydantic schema for the default expected YAML issue structure."""

from typing import Any

from pydantic import BaseModel


class LabelModel(BaseModel):
    """Pydantic model for a GitHub label."""

    name: str
    color: str
    description: str | None = None


class PullRequestModel(BaseModel):
    """Pydantic model for a GitHub pull request definition attached to an issue."""

    title: str
    branch: str | None = None
    body: str | None = None
    files: list[str]
    labels: list[str] | None = None


class IssueModel(BaseModel):
    """Pydantic model for a GitHub issue."""

    title: str
    body: str | None = None
    labels: list[str] | None = None
    assignees: list[str] | None = None
    milestone: str | int | None = None
    state: str = "open"
    data: dict[str, Any] | None = None
    pull_request: PullRequestModel | None = None


class IssuesYAMLModel(BaseModel):
    """Pydantic model for a list of GitHub issues and optional issue template."""

    issue_template: str | None = None
    issues: list[IssueModel]
