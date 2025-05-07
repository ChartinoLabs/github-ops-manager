"""Integration tests for the CLI."""

import subprocess
from pathlib import Path

from .utils import get_cli_with_starting_args


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Helper to run the CLI as a subprocess and capture output.

    Args:
        args: List of command line arguments to pass to the CLI.

    Returns:
        subprocess.CompletedProcess: The result of running the CLI command.
    """
    cli_with_starting_args = get_cli_with_starting_args()
    complete_command = cli_with_starting_args + args
    print(f"Running command: {' '.join(complete_command)}")
    result = subprocess.run(
        complete_command,
        capture_output=True,
        text=True,
    )
    print(f"Command result: {result.returncode}")
    print(f"Command stdout: {result.stdout}")
    print(f"Command stderr: {result.stderr}")
    return result


def test_no_yaml_path_provided() -> None:
    """Test that the CLI exits with an error if no YAML path is provided."""
    result = run_cli(["process-issues"])
    assert "Missing argument 'YAML_PATH'" in result.stderr


def test_malformed_yaml(tmp_path: Path) -> None:
    """Test that the CLI exits with an error if the YAML is malformed."""
    malformed_yaml = tmp_path / "bad.yaml"
    malformed_yaml.write_text("not: [valid: yaml")
    result = run_cli(["process-issues", str(malformed_yaml)])
    assert "Failed to parse YAML file" in result.stdout
