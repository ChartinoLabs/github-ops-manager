"""Schemas/models for Testing as Code constructs."""

from pydantic import BaseModel


class TestingAsCodeCommand(BaseModel):
    """Pydantic model for a Testing as Code command."""

    command: str
    preferred_dut: str | None = None
    api: bool = False
    command_output: str | None = None
    parsed_output: str | None = None
    parser_used: str | None = None
    output_from_device: str | None = None
    genai_regex_pattern: str | None = None


class TestingAsCodeTestCaseDefinition(BaseModel):
    """Pydantic model for a Testing as Code test case definition."""

    title: str
    purpose: str
    labels: list[str]
    commands: list[TestingAsCodeCommand]
    pass_criteria: str | None = None
    jobfile_parameters: str | None = None
    jobfile_parameters_mapping: str | None = None
    resulting_filename: str | None = None


class TestingAsCodeTestCaseDefinitions(BaseModel):
    """Pydantic model for a list of Testing as Code test case definitions."""

    test_cases: list[TestingAsCodeTestCaseDefinition]
