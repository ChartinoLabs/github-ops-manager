"""Handles reading/mapping YAML input and writing YAML output.

This module provides the YAMLProcessor class, which loads and validates issues from YAML files
according to a Pydantic schema. It supports field renaming, merging issues from multiple files,
logging extra fields, and collecting validation errors. All logging is performed using structlog.
"""

from typing import Any, Type

import structlog
from pydantic import BaseModel, ValidationError
from ruamel.yaml import YAML
from structlog.stdlib import BoundLogger

from github_ops_manager.schemas.default_issue import IssueModel

logger: BoundLogger = structlog.get_logger(__name__)  # type: ignore

yaml = YAML(typ="safe")


def _apply_field_mapping(
    issue_dict: dict[str, Any] | Any, field_mapping: dict[str, str] | None
) -> dict[str, Any]:
    """Apply a field mapping (renaming) to a dictionary representing an issue.

    Args:
        issue_dict (Dict[str, Any]): The original issue dictionary from YAML.
        field_mapping (Dict[str, str] | None): Optional mapping from YAML field names to schema field names.

    Returns:
        Dict[str, Any]: The issue dictionary with fields renamed according to the mapping.
    """
    if not field_mapping:
        return issue_dict
    return {field_mapping.get(k, k): v for k, v in issue_dict.items()}


class YAMLProcessor:
    """Loads and validates issues from one or more YAML files using a Pydantic schema.

    This processor supports field renaming, merging issues from multiple files,
    logging extra fields, and collecting all validation errors. It expects each YAML file
    to have a top-level 'issues' key containing a list of issue dictionaries.
    """

    def __init__(
        self,
        schema: Type[BaseModel] = IssueModel,
        field_mapping: dict[str, str] | None = None,
    ) -> None:
        """Initialize YAMLProcessor with a schema and optional field mapping.

        Args:
            schema (Type[BaseModel]): The Pydantic model to use for validation (default: IssueModel).
            field_mapping (dict[str, str] | None): Optional mapping from YAML field names to schema field names.
        """
        self.schema = schema
        self.field_mapping = field_mapping

    def load_issues(self, yaml_paths: list[str]) -> list[BaseModel]:
        """Load and validate issues from one or more YAML files.

        Args:
            yaml_paths (list[str]): List of file paths to YAML files.

        Returns:
            list[BaseModel]: List of validated issue models. Issues with validation errors are skipped.

        Side Effects:
            Logs warnings for extra fields, errors for validation failures, and collects all errors.
        """
        all_issues: list[BaseModel] = []
        errors: list[dict[str, Any]] = []
        for path in yaml_paths:
            try:
                with open(path) as f:
                    data: dict[str, Any] = yaml.load(f)  # type: ignore
            except Exception as e:
                logger.error("Failed to parse YAML file", path=path, error=str(e))
                errors.append({"file": path, "error": str(e)})
                continue
            if not isinstance(data, dict) or "issues" not in data:
                logger.error("YAML file missing top-level 'issues' key", path=path)
                errors.append({"file": path, "error": "Missing top-level 'issues' key"})
                continue
            issue_dict: dict[str, Any] | Any
            for idx, issue_dict in enumerate(data["issues"]):
                if not isinstance(issue_dict, dict):
                    logger.warning(
                        "Issue entry is not a dict and will be skipped",
                        file=path,
                        issue_index=idx,
                        actual_type=type(issue_dict).__name__,
                    )
                    errors.append(
                        {
                            "file": path,
                            "issue_index": idx,
                            "error": "Issue entry is not a dict",
                        }
                    )
                    continue
                mapped: dict[str, Any] = _apply_field_mapping(
                    issue_dict, self.field_mapping
                )
                # Warn about extra fields
                extra_fields = set(mapped.keys()) - set(self.schema.model_fields.keys())
                if extra_fields:
                    logger.warning(
                        "Extra fields in issue will be ignored",
                        file=path,
                        issue_index=idx,
                        extra_fields=list(extra_fields),
                    )
                # Only keep fields that are in the schema
                filtered = {
                    k: v for k, v in mapped.items() if k in self.schema.model_fields
                }
                try:
                    issue = self.schema(**filtered)
                    all_issues.append(issue)
                except ValidationError as ve:
                    logger.error(
                        "Validation error for issue",
                        file=path,
                        issue_index=idx,
                        error=ve.errors(),
                    )
                    errors.append(
                        {"file": path, "issue_index": idx, "error": ve.errors()}
                    )
        if errors:
            logger.error(
                "One or more errors occurred during YAML processing", errors=errors
            )
        return all_issues
