"""Schemas/models for Testing as Code constructs."""

from pydantic import BaseModel, Field


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
    generated_script_path: str | None = None


class TestingAsCodeTestCaseDefinitions(BaseModel):
    """Pydantic model for a list of Testing as Code test case definitions."""

    test_cases: list[TestingAsCodeTestCaseDefinition]


# =============================================================================
# CXTM Configuration Models (cxtm.yaml)
# =============================================================================
# These models represent the test case definitions stored in cxtm.yaml,
# which is the authoritative source for test case metadata used by tac-tools.


class CXTMTestCase(BaseModel):
    """A single test case within a test case group in cxtm.yaml."""

    identifier: str = Field(description="Unique identifier within the group (e.g., '0')")
    title: str = Field(description="Human-readable test case title")
    robot_file: str | None = Field(default=None, description="Path to the Robot Framework test file")
    git_url: str | None = Field(default=None, description="URL of the git repository containing the test")
    git_commit_sha: str | None = Field(default=None, description="Git commit SHA or branch name")
    parameters_file: str | None = Field(default=None, description="Path to parameters JSON file")
    parameters: dict | None = Field(default=None, description="Inline test parameters")


class CXTMTestCaseGroup(BaseModel):
    """A test case group in cxtm.yaml containing one or more test cases."""

    name: str = Field(description="Name of the test case group")
    test_cases: list[CXTMTestCase] = Field(default_factory=list, description="List of test cases in this group")


class CXTMConfiguration(BaseModel):
    """Root model for cxtm.yaml configuration file."""

    cxta_version: str | None = Field(default=None, description="CXTA version")
    cxtm_project_id: str | None = Field(default=None, description="CXTM project ID")
    git_branch: str | None = Field(default=None, description="Default git branch")
    git_url: str | None = Field(default=None, description="Project repository URL")
    test_case_groups: list[CXTMTestCaseGroup] = Field(default_factory=list, description="List of test case groups")
