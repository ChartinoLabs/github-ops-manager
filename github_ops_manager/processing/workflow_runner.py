# This file is intended to orchestrate the main actions (e.g., sync-to-github, export-issues).

"""Orchestrates the main workflows (e.g., sync-to-github, export-issues)."""

from github_ops_manager.configuration.models import ProcessIssuesConfig
from github_ops_manager.processing.results import ProcessIssuesResult
from github_ops_manager.processing.yaml_processor import (
    YAMLProcessingError,
    YAMLProcessor,
)


async def run_process_issues_workflow(
    config: ProcessIssuesConfig,
    raise_on_yaml_error: bool = False,
) -> ProcessIssuesResult:
    """Run the process-issues workflow: load issues from YAML and return them/errors."""
    if config.yaml_path is not None:
        processor = YAMLProcessor(raise_on_error=raise_on_yaml_error)
        try:
            issues = processor.load_issues([str(config.yaml_path)])
            return ProcessIssuesResult(issues)
        except YAMLProcessingError as e:
            return ProcessIssuesResult([], errors=e.errors)
    else:
        return ProcessIssuesResult([])
