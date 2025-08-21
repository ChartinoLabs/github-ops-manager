"""Contains utility functions for working with YAML files."""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

yaml = YAML(typ="safe")


def load_yaml_file(path: Path) -> dict[str, Any]:
    """Loads a YAML file and returns a dictionary."""
    with open(path, encoding="utf-8") as f:
        return yaml.load(f)  # type: ignore[no-any-return]


def create_yaml_dumper() -> YAML:
    """Creates a properly configured YAML object for dumping with multiline string support."""
    yaml_dumper = YAML()
    yaml_dumper.default_flow_style = False
    yaml_dumper.explicit_start = True
    yaml_dumper.indent(mapping=2, sequence=4, offset=2)  # type: ignore[attr-defined]
    yaml_dumper.width = 4096  # Prevent line wrapping for long lines
    yaml_dumper.preserve_quotes = True

    # Configure multiline string handling
    def represent_str(dumper: Any, data: str) -> Any:
        """Custom string representer that uses literal scalar style for multiline strings."""
        if "\n" in data:
            # Use literal scalar style (|) for multiline strings
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        # Use default representation for single-line strings
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    yaml_dumper.representer.add_representer(str, represent_str)  # type: ignore[attr-defined]

    return yaml_dumper


def dump_yaml_to_file(data: Any, file_path: Path) -> None:
    """Dumps data to a YAML file with proper multiline string formatting."""
    yaml_dumper = create_yaml_dumper()
    with open(file_path, "w", encoding="utf-8") as f:
        yaml_dumper.dump(data, f)  # type: ignore[misc]
