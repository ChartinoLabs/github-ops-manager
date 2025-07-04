"""Contains utility functions for interacting with Testing as Code constructs."""

from github_ops_manager.schemas.default_issue import IssueModel, IssuesYAMLModel
from github_ops_manager.schemas.tac import TestingAsCodeTestCaseDefinition, TestingAsCodeTestCaseDefinitions


def find_issue_with_title(issues_yaml_model: IssuesYAMLModel, title: str) -> IssueModel | None:
    """Finds an issue with a specific title."""
    if not title:
        raise ValueError("Provided title is an empty string")

    for issue in issues_yaml_model.issues:
        if issue.title == title:
            return issue
    return None


def find_test_case_definition_with_file(test_case_definitions: TestingAsCodeTestCaseDefinitions, file: str) -> TestingAsCodeTestCaseDefinition | None:
    """Finds a test case definition that resulted in a specific created file."""
    for test_case_definition in test_case_definitions.test_cases:
        if test_case_definition.generated_script_path == file:
            return test_case_definition
    return None


def find_test_case_definition_with_files(
    test_case_definitions: TestingAsCodeTestCaseDefinitions, files: list[str]
) -> TestingAsCodeTestCaseDefinition | None:
    """Finds a test case definition that resulted in a specific created file.

    This takes in a list of files; the first test case definition that contains
    one of any of the files is returned.
    """
    for file in files:
        test_case_definition = find_test_case_definition_with_file(test_case_definitions, file)
        if test_case_definition is not None:
            return test_case_definition
    return None
