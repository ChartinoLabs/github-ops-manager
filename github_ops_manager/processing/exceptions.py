"""Custom exceptions for the processing module."""

from typing import Any


class YAMLProcessingError(Exception):
    """Raised when errors are encountered during YAML processing."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        """Initialize the error with a list of errors."""
        super().__init__("Errors encountered during YAML processing.")
        self.errors = errors
