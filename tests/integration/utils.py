"""Utility functions for integration tests."""

import os
from pathlib import Path


def get_cli_script_path() -> str:
    """Get the path to the github-ops-manager CLI script.

    Returns:
        str: The absolute path to the CLI script.

    Raises:
        FileNotFoundError: If the CLI script cannot be found.
    """
    # Start from the current file's location and go up to the project root
    cli_script = str(Path(__file__).parent.parent.parent / "github-ops-manager")
    if not os.path.exists(cli_script):
        raise FileNotFoundError(f"CLI script not found at {cli_script}")

    # Ensure the script is executable
    os.chmod(cli_script, 0o755)

    return cli_script
