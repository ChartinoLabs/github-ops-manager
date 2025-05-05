"""Integration tests for the CLI."""

import subprocess
import sys
from pathlib import Path
from typing import List


def run_cli(args: List[str]) -> subprocess.CompletedProcess[str]:
    """Helper to run the CLI as a subprocess and capture output."""
    base_args = ["--github-pat-token", "dummy-token", "--repo", "dummy/repo"]
    result = subprocess.run(
        [sys.executable, "-m", "github_ops_manager.configuration.cli"] + base_args + args,
        capture_output=True,
        text=True,
    )
    return result


def test_no_yaml_path_provided() -> None:
    """Test that the CLI exits with an error if no YAML path is provided."""
    result = run_cli(["process-issues"])
    assert "No YAML path provided" in result.stdout


def test_malformed_yaml(tmp_path: Path) -> None:
    """Test that the CLI exits with an error if the YAML is malformed."""
    malformed_yaml = tmp_path / "bad.yaml"
    malformed_yaml.write_text("not: [valid: yaml")
    result = run_cli(["process-issues", "--yaml-path", str(malformed_yaml)])
    assert "Error(s) encountered while processing YAML" in result.stderr
