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

from github_ops_manager.processing.exceptions import YAMLProcessingError
from github_ops_manager.schemas.default_issue import IssueModel, IssuesYAMLModel

logger: BoundLogger = structlog.get_logger(__name__)  # type: ignore

yaml = YAML(typ="safe")


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
        raise_on_error: bool = True,
    ) -> None:
        """Initialize YAMLProcessor with a schema and optional field mapping.

        Args:
            schema (Type[BaseModel]): The Pydantic model to use for validation (default: IssueModel).
            field_mapping (dict[str, str] | None): Optional mapping from YAML field names to schema field names.
            raise_on_error (bool): Whether to raise a YAMLProcessingError on validation errors.
        """
        self.schema = schema  # This is unused for now
        self.field_mapping = field_mapping
        self.raise_on_error = raise_on_error

    def load_issues_model(self, yaml_paths: list[str]) -> IssuesYAMLModel:
        """Load and validate issues and template from one or more YAML files, returning an IssuesYAMLModel."""
        all_issues: list[IssueModel] = []
        issue_template: str | None = None
        errors: list[dict[str, Any]] = []
        for path in yaml_paths:
            data = self._load_yaml_file(path, errors)
            if data is None:
                continue
            # Only set issue_template if present and not already set
            if issue_template is None and "issue_template" in data:
                issue_template = data["issue_template"]
            for idx, issue_dict in enumerate(self._extract_issues(data, path, errors)):
                if not isinstance(issue_dict, dict):
                    logger.warning(
                        "Issue entry is not a dict and will be skipped",
                        file=path,
                        issue_index=idx,
                        actual_type=type(issue_dict).__name__,
                    )
                    errors.append({"file": path, "issue_index": idx, "error": "Issue entry is not a dict"})
                    continue
                mapped: dict[str, Any] = self._apply_field_mapping(issue_dict, self.field_mapping)
                extra_fields = set(mapped.keys()) - set(IssueModel.model_fields.keys())
                if extra_fields:
                    logger.warning(
                        "Extra fields in issue will be ignored",
                        file=path,
                        issue_index=idx,
                        extra_fields=list(extra_fields),
                    )
                filtered = {k: v for k, v in mapped.items() if k in IssueModel.model_fields}
                try:
                    all_issues.append(IssueModel(**filtered))
                except ValidationError as ve:
                    logger.error(
                        "Validation error for issue",
                        file=path,
                        issue_index=idx,
                        error=ve.errors(),
                    )
                    errors.append({"file": path, "issue_index": idx, "error": ve.errors()})
        if errors:
            logger.error("One or more errors occurred during YAML processing", errors=errors)
            if self.raise_on_error:
                raise YAMLProcessingError(errors)
        return IssuesYAMLModel(issue_template=issue_template, issues=all_issues)

    def _load_yaml_file(self, path: str, errors: list[dict[str, Any]]) -> dict[str, Any] | None:
        try:
            with open(path) as f:
                data: dict[str, Any] = yaml.load(f)  # type: ignore
            # If loaded data is not a dictionary, throw an error.
            if not isinstance(data, dict):
                logger.error("YAML file is not a dictionary", path=path)
                errors.append({"file": path, "error": "YAML file is not a dictionary"})
                return None
            return data
        except Exception as e:
            logger.error("Failed to parse YAML file", path=path, error=str(e))
            errors.append({"file": path, "error": str(e)})
            return None

    def _extract_issues(self, data: dict[str, Any], path: str, errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if "issues" not in data:
            logger.error("YAML file missing top-level 'issues' key", path=path)
            errors.append({"file": path, "error": "Missing top-level 'issues' key"})
            return []
        return data["issues"]

    def _apply_field_mapping(self, issue_dict: dict[str, Any], field_mapping: dict[str, str] | None) -> dict[str, Any]:
        """Apply a field mapping (renaming) to a dictionary representing an issue.

        Args:
            issue_dict (dict[str, Any]): The original issue dictionary from YAML.
            field_mapping (dict[str, str] | None): Optional mapping from YAML field names to schema field names.

        Returns:
            dict[str, Any]: The issue dictionary with fields renamed according to the mapping.
        """
        if not field_mapping:
            return issue_dict
        return {field_mapping.get(k, k): v for k, v in issue_dict.items()}
