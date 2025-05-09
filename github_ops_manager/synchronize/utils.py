"""Contains utility functions for synchronization actions."""

from typing import Any


async def value_is_noney(value: Any) -> bool:
    """Check if a value is None, an empty list, an empty string, or an empty dict."""
    if value is None:
        return True
    elif isinstance(value, list) and value == []:
        return True
    elif isinstance(value, str) and value == "":
        return True
    elif isinstance(value, dict) and not value:
        return True
    return False
