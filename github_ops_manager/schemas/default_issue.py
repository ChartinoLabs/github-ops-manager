"""Pydantic schema for the default expected YAML issue structure."""

from pydantic import BaseModel


class LabelModel(BaseModel):
    """Pydantic model for a GitHub label."""

    name: str
    color: str
    description: str | None = None


class IssueModel(BaseModel):
    """Pydantic model for a GitHub issue."""

    title: str
    body: str | None = None
    labels: list[str] | None = None
    assignees: list[str] | None = None
    milestone: str | int | None = None
    state: str = "open"


class IssuesYAMLModel(BaseModel):
    """Pydantic model for a list of GitHub issues."""

    issues: list[IssueModel]
