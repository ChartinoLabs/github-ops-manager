"""Internal data models (e.g., processed issue data structures)."""

from enum import Enum


class IssueSyncDecision(Enum):
    """Enum for issue sync decisions."""

    CREATE = "create"
    UPDATE = "update"
    NOOP = "noop"
