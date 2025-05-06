"""Internal data models (e.g., processed issue data structures)."""

from enum import Enum


class SyncDecision(Enum):
    """Enum for sync decisions."""

    CREATE = "create"
    UPDATE = "update"
    NOOP = "noop"
