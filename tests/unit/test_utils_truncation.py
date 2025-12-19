"""Unit tests for the truncation utility module."""

from github_ops_manager.schemas.tac import TestingAsCodeCommand, TestingAsCodeTestCaseDefinition
from github_ops_manager.utils.constants import MIN_OUTPUT_LENGTH
from github_ops_manager.utils.truncation import (
    calculate_field_sizes,
    distribute_budget_proportionally,
    estimate_template_overhead,
    truncate_data_dict_outputs,
    truncate_string_at_end,
    truncate_test_case_outputs,
)


class TestTruncateStringAtEnd:
    """Tests for truncate_string_at_end function."""

    def test_no_truncation_when_under_limit(self) -> None:
        """Content under the limit should not be truncated."""
        content = "Hello, world!"
        result, was_truncated = truncate_string_at_end(content, max_length=100)
        assert result == content
        assert was_truncated is False

    def test_no_truncation_when_at_limit(self) -> None:
        """Content exactly at the limit should not be truncated."""
        content = "x" * 50
        result, was_truncated = truncate_string_at_end(content, max_length=50)
        assert result == content
        assert was_truncated is False

    def test_truncates_long_content(self) -> None:
        """Content over the limit should be truncated with indicator."""
        content = "a" * 1000
        result, was_truncated = truncate_string_at_end(content, max_length=100)
        assert was_truncated is True
        assert len(result) <= 100
        assert "truncated" in result
        assert "characters removed" in result

    def test_empty_string_not_truncated(self) -> None:
        """Empty string should pass through unchanged."""
        result, was_truncated = truncate_string_at_end("", max_length=100)
        assert result == ""
        assert was_truncated is False

    def test_none_string_not_truncated(self) -> None:
        """None value should pass through unchanged."""
        result, was_truncated = truncate_string_at_end(None, max_length=100)  # type: ignore[arg-type]
        assert result is None
        assert was_truncated is False

    def test_truncation_suffix_includes_char_count(self) -> None:
        """Truncation suffix should include the number of characters removed."""
        content = "a" * 1000
        result, was_truncated = truncate_string_at_end(content, max_length=100)
        assert was_truncated is True
        # The suffix should mention how many chars were removed
        # Check that a number is in the result
        import re

        match = re.search(r"\d+", result.split("truncated")[1])
        assert match is not None
        chars_removed = int(match.group())
        assert chars_removed > 0


class TestEstimateTemplateOverhead:
    """Tests for estimate_template_overhead function."""

    def test_basic_overhead_calculation(self) -> None:
        """Basic test case should have minimal overhead."""
        test_case = TestingAsCodeTestCaseDefinition(
            title="Test",
            purpose="Simple purpose",
            labels=["test"],
            commands=[
                TestingAsCodeCommand(command="show version"),
            ],
        )
        overhead = estimate_template_overhead(test_case)
        # Should include base overhead + 1 command overhead + purpose length
        assert overhead > 0
        assert overhead >= len("Simple purpose")

    def test_multiple_commands_increase_overhead(self) -> None:
        """More commands should increase overhead."""
        test_case_1_cmd = TestingAsCodeTestCaseDefinition(
            title="Test",
            purpose="Purpose",
            labels=["test"],
            commands=[TestingAsCodeCommand(command="cmd1")],
        )
        test_case_3_cmd = TestingAsCodeTestCaseDefinition(
            title="Test",
            purpose="Purpose",
            labels=["test"],
            commands=[
                TestingAsCodeCommand(command="cmd1"),
                TestingAsCodeCommand(command="cmd2"),
                TestingAsCodeCommand(command="cmd3"),
            ],
        )
        overhead_1 = estimate_template_overhead(test_case_1_cmd)
        overhead_3 = estimate_template_overhead(test_case_3_cmd)
        assert overhead_3 > overhead_1

    def test_includes_optional_fields(self) -> None:
        """Optional fields should contribute to overhead."""
        test_case_minimal = TestingAsCodeTestCaseDefinition(
            title="Test",
            purpose="Purpose",
            labels=["test"],
            commands=[TestingAsCodeCommand(command="cmd1")],
        )
        test_case_full = TestingAsCodeTestCaseDefinition(
            title="Test",
            purpose="Purpose",
            labels=["test"],
            commands=[TestingAsCodeCommand(command="cmd1")],
            pass_criteria="* Check X\n* Check Y",
            jobfile_parameters="key: value\nkey2: value2",
            jobfile_parameters_mapping="mapping info",
        )
        overhead_minimal = estimate_template_overhead(test_case_minimal)
        overhead_full = estimate_template_overhead(test_case_full)
        assert overhead_full > overhead_minimal


class TestCalculateFieldSizes:
    """Tests for calculate_field_sizes function."""

    def test_empty_outputs(self) -> None:
        """Commands with no outputs should have zero sizes."""
        commands = [TestingAsCodeCommand(command="show version")]
        sizes = calculate_field_sizes(commands)
        assert len(sizes) == 1
        assert sizes[0]["command_output"] == 0
        assert sizes[0]["parsed_output"] == 0

    def test_populated_outputs(self) -> None:
        """Commands with outputs should have correct sizes."""
        commands = [
            TestingAsCodeCommand(
                command="show version",
                command_output="output" * 100,
                parsed_output="parsed" * 50,
            ),
        ]
        sizes = calculate_field_sizes(commands)
        assert sizes[0]["command_output"] == 600  # "output" * 100 = 600 chars
        assert sizes[0]["parsed_output"] == 300  # "parsed" * 50 = 300 chars

    def test_multiple_commands(self) -> None:
        """Should calculate sizes for all commands."""
        commands = [
            TestingAsCodeCommand(command="cmd1", command_output="a" * 100),
            TestingAsCodeCommand(command="cmd2", parsed_output="b" * 200),
        ]
        sizes = calculate_field_sizes(commands)
        assert len(sizes) == 2
        assert sizes[0]["command_output"] == 100
        assert sizes[0]["parsed_output"] == 0
        assert sizes[1]["command_output"] == 0
        assert sizes[1]["parsed_output"] == 200


class TestDistributeBudgetProportionally:
    """Tests for distribute_budget_proportionally function."""

    def test_no_truncation_when_under_budget(self) -> None:
        """Should return original sizes if under budget."""
        field_sizes = [{"command_output": 100, "parsed_output": 100}]
        budgets = distribute_budget_proportionally(field_sizes, available_budget=500)
        assert budgets == field_sizes

    def test_proportional_distribution(self) -> None:
        """Larger fields should get larger budget share."""
        field_sizes = [
            {"command_output": 8000, "parsed_output": 2000},  # 80% vs 20%
        ]
        budgets = distribute_budget_proportionally(field_sizes, available_budget=5000)
        # 8000 is 80% of 10000, so should get ~80% of 5000 = 4000
        # 2000 is 20% of 10000, so should get ~20% of 5000 = 1000
        assert budgets[0]["command_output"] > budgets[0]["parsed_output"]
        assert budgets[0]["command_output"] >= 3500  # Roughly 80% of 5000

    def test_minimum_budget_enforced(self) -> None:
        """Each field should get at least MIN_OUTPUT_LENGTH if original was larger."""
        field_sizes = [
            {"command_output": 10000, "parsed_output": 10000},
        ]
        # Very small budget
        budgets = distribute_budget_proportionally(field_sizes, available_budget=200)
        # Even with tiny budget, should get minimum
        assert budgets[0]["command_output"] >= MIN_OUTPUT_LENGTH
        assert budgets[0]["parsed_output"] >= MIN_OUTPUT_LENGTH

    def test_empty_fields_get_zero_budget(self) -> None:
        """Empty fields should get zero budget."""
        field_sizes = [{"command_output": 0, "parsed_output": 1000}]
        budgets = distribute_budget_proportionally(field_sizes, available_budget=500)
        assert budgets[0]["command_output"] == 0


class TestTruncateTestCaseOutputs:
    """Tests for truncate_test_case_outputs function."""

    def test_no_truncation_when_under_limit(self) -> None:
        """Test case under limit should not be modified."""
        test_case = TestingAsCodeTestCaseDefinition(
            title="Test",
            purpose="Purpose",
            labels=["test"],
            commands=[
                TestingAsCodeCommand(
                    command="show version",
                    command_output="short output",
                    parsed_output="short parsed",
                ),
            ],
        )
        result = truncate_test_case_outputs(test_case, max_body_length=60000)
        assert result.commands[0].command_output == "short output"
        assert result.commands[0].parsed_output == "short parsed"

    def test_truncates_large_outputs(self) -> None:
        """Large outputs should be truncated."""
        large_output = "x" * 50000
        test_case = TestingAsCodeTestCaseDefinition(
            title="Test",
            purpose="Purpose",
            labels=["test"],
            commands=[
                TestingAsCodeCommand(
                    command="show version",
                    command_output=large_output,
                    parsed_output=large_output,
                ),
            ],
        )
        result = truncate_test_case_outputs(test_case, max_body_length=30000)
        assert len(result.commands[0].command_output or "") < len(large_output)
        assert len(result.commands[0].parsed_output or "") < len(large_output)
        assert "truncated" in (result.commands[0].command_output or "")
        assert "truncated" in (result.commands[0].parsed_output or "")

    def test_does_not_mutate_original(self) -> None:
        """Original test case should not be modified."""
        large_output = "x" * 50000
        test_case = TestingAsCodeTestCaseDefinition(
            title="Test",
            purpose="Purpose",
            labels=["test"],
            commands=[
                TestingAsCodeCommand(
                    command="show version",
                    command_output=large_output,
                ),
            ],
        )
        original_length = len(test_case.commands[0].command_output or "")
        _ = truncate_test_case_outputs(test_case, max_body_length=10000)
        # Original should be unchanged
        assert len(test_case.commands[0].command_output or "") == original_length

    def test_multiple_commands_distributed(self) -> None:
        """Budget should be distributed across multiple commands."""
        test_case = TestingAsCodeTestCaseDefinition(
            title="Test",
            purpose="Purpose",
            labels=["test"],
            commands=[
                TestingAsCodeCommand(command="cmd1", command_output="a" * 30000),
                TestingAsCodeCommand(command="cmd2", command_output="b" * 30000),
            ],
        )
        result = truncate_test_case_outputs(test_case, max_body_length=30000)
        # Both should be truncated, each getting roughly half the budget
        len1 = len(result.commands[0].command_output or "")
        len2 = len(result.commands[1].command_output or "")
        assert len1 < 30000
        assert len2 < 30000
        # They should be roughly equal since original sizes were equal
        assert abs(len1 - len2) < 1000


class TestTruncateDataDictOutputs:
    """Tests for truncate_data_dict_outputs function."""

    def test_no_commands_returns_unchanged(self) -> None:
        """Data without commands should pass through unchanged."""
        data = {"key": "value", "other": 123}
        result = truncate_data_dict_outputs(data, max_body_length=60000)
        assert result == data

    def test_truncates_command_outputs(self) -> None:
        """Large outputs in data dict should be truncated."""
        large_output = "x" * 50000
        data = {
            "purpose": "Test",
            "commands": [
                {"command": "show version", "command_output": large_output},
            ],
        }
        result = truncate_data_dict_outputs(data, max_body_length=30000)
        assert len(result["commands"][0]["command_output"]) < len(large_output)
        assert "truncated" in result["commands"][0]["command_output"]

    def test_does_not_mutate_original_dict(self) -> None:
        """Original data dict should not be modified."""
        large_output = "x" * 50000
        data = {
            "commands": [
                {"command": "show version", "command_output": large_output},
            ],
        }
        original_length = len(data["commands"][0]["command_output"])
        _ = truncate_data_dict_outputs(data, max_body_length=10000)
        assert len(data["commands"][0]["command_output"]) == original_length

    def test_handles_missing_output_fields(self) -> None:
        """Commands without output fields should not cause errors."""
        data = {
            "commands": [
                {"command": "show version"},  # No output fields
            ],
        }
        result = truncate_data_dict_outputs(data, max_body_length=60000)
        assert result["commands"][0] == {"command": "show version"}
