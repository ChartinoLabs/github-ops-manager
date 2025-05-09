"""Contains unit tests for the synchronize utils."""

import pytest

from github_ops_manager.synchronize.utils import value_is_noney


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),
        ([], True),
        ("", True),
        ({}, True),
        ([1, 2, 3], False),
        ("non-empty", False),
        ({"key": "value"}, False),
        (0, False),
        (False, False),
    ],
)
async def test_value_is_noney(value: object, expected: bool) -> None:
    """Test the value_is_noney function."""
    result = await value_is_noney(value)
    assert result == expected
