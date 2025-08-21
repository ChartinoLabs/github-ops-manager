"""Contains utility functions for working with YAML files."""

from pathlib import Path

from ruamel.yaml import YAML

yaml = YAML(typ="safe")


def load_yaml_file(path: Path) -> dict:
    """Loads a YAML file and returns a dictionary."""
    with open(path, encoding="utf-8") as f:
        return yaml.load(f)
