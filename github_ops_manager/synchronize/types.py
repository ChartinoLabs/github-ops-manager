"""Type hints for the synchronize module."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HasName(Protocol):
    """Protocol for objects that have a name attribute."""

    name: str


LabelType = str | dict[str, Any] | HasName
