"""Contains unit tests for the synchronize pull_requests module."""

import pytest

from github_ops_manager.synchronize.pull_requests import pull_request_has_closing_keywords


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "issue_number,pull_request_body,expected",
    [
        # Test None body
        (1, None, False),
        (123, None, False),
        (0, None, False),
        # Test empty string body
        (1, "", False),
        (123, "", False),
        # Test whitespace-only body
        (1, "   ", False),
        (1, "\n\t  \n", False),
        # Test bodies with no closing keywords
        (1, "This is a regular PR description", False),
        (1, "Update documentation and examples", False),
        (1, "Add new feature for user management", False),
        # Test bodies with keywords but no issue number
        (1, "This closes the previous implementation", False),
        (1, "This fixes a bug in the code", False),
        (1, "This resolves the performance issue", False),
        # Test bodies with keywords but wrong issue number
        (1, "This closes #2", False),
        (1, "This fixes #123", False),  # Should not match - #123 is not #1
        (2, "This resolves #1", False),
        (123, "This closes #456", False),
        # Test bodies with keywords but missing hash
        (1, "This closes 1", False),
        (1, "This fixes issue 1", False),
        (1, "This resolves issue number 1", False),
        # Test each closing keyword individually - positive cases
        (1, "This close #1", True),
        (1, "This closes #1", True),
        (1, "This closed #1", True),
        (1, "This fix #1", True),
        (1, "This fixes #1", True),
        (1, "This fixed #1", True),
        (1, "This resolve #1", True),
        (1, "This resolves #1", True),
        (1, "This resolved #1", True),
        # Test case insensitivity
        (1, "This CLOSE #1", True),
        (1, "This Closes #1", True),
        (1, "This FIXES #1", True),
        (1, "This ResolveS #1", True),
        (1, "This ClOsEd #1", True),
        # Test with different issue numbers
        (0, "fixes #0", True),
        (5, "closes #5", True),
        (42, "resolves #42", True),
        (123, "fixes #123", True),
        (9999, "closes #9999", True),
        # Test keywords at different positions
        (1, "closes #1", True),  # Beginning
        (1, "This PR closes #1 successfully", True),  # Middle
        (1, "Updated implementation - closes #1", True),  # End
        (1, "closes #1\nAdditional details here", True),  # Beginning with newline
        # Test with multiple keywords (should return True if any matches)
        (1, "This closes #2 and fixes #1", True),
        (1, "This resolves #1 and closes #2", True),
        (2, "This closes #2 and fixes #1", True),
        (3, "This closes #2 and fixes #1", False),  # Neither matches
        # Test with extra whitespace and punctuation
        (1, "This closes  #1", True),  # Multiple spaces should work
        (1, "This closes\t#1", True),  # Tab should work
        (1, "This closes\n#1", True),  # Newline should work
        (1, "closes #1.", True),
        (1, "closes #1,", True),
        (1, "closes #1!", True),
        (1, "closes #1;", True),
        (1, "(closes #1)", True),
        (1, "closes #1:", True),
        # Test longer, more realistic PR bodies
        (
            42,
            """
        ## Summary
        This PR implements the new authentication flow.

        ## Changes
        - Updated login component
        - Added OAuth integration
        - Fixed session management

        Closes #42
        """,
            True,
        ),
        (
            42,
            """
        ## Summary
        This PR implements the new authentication flow.

        ## Changes
        - Updated login component
        - Added OAuth integration
        - Fixed session management

        Resolves #42
        """,
            True,
        ),
        (
            42,
            """
        ## Summary
        This PR implements the new authentication flow.

        ## Changes
        - Updated login component
        - Added OAuth integration
        - Fixed session management

        Fixes issue #123
        """,
            False,
        ),  # Wrong issue number
        # Test with HTML/markdown content
        (1, "This **closes #1** with bold formatting", True),
        (1, "This `closes #1` with code formatting", True),
        (1, "This [closes #1](link) with link formatting", True),
        # Test boundary conditions with similar patterns
        (1, "This closes #11", False),  # Issue 1 but text has #11
        (11, "This closes #11", True),  # Issue 11 and text has #11
        (1, "This closes #111", False),  # Issue 1 but text has #111
        (111, "This closes #111", True),  # Issue 111 and text has #111
        (1, "This closes #1 and #11", True),  # Issue 1, text has both #1 and #11
    ],
)
async def test_pull_request_has_closing_keywords(issue_number: int, pull_request_body: str | None, expected: bool) -> None:
    """Test the pull_request_has_closing_keywords function with various inputs."""
    result = await pull_request_has_closing_keywords(issue_number, pull_request_body)
    assert result == expected


@pytest.mark.asyncio
async def test_pull_request_has_closing_keywords_all_keywords_work() -> None:
    """Test that all defined closing keywords work correctly."""
    # Test all keywords defined in the function
    keywords = ["close", "closes", "closed", "fix", "fixes", "fixed", "resolve", "resolves", "resolved"]

    issue_number = 123

    for keyword in keywords:
        # Test basic case
        body = f"This {keyword} #{issue_number}"
        result = await pull_request_has_closing_keywords(issue_number, body)
        assert result is True, f"Keyword '{keyword}' should match issue #{issue_number}"

        # Test uppercase case
        body_upper = f"This {keyword.upper()} #{issue_number}"
        result_upper = await pull_request_has_closing_keywords(issue_number, body_upper)
        assert result_upper is True, f"Uppercase keyword '{keyword.upper()}' should match issue #{issue_number}"


@pytest.mark.asyncio
async def test_pull_request_has_closing_keywords_complex_scenarios() -> None:
    """Test complex real-world scenarios."""
    issue_number = 456

    # Test GitHub's standard closing keywords format
    github_formats = [
        f"fix #{issue_number}",
        f"fixes #{issue_number}",
        f"fixed #{issue_number}",
        f"close #{issue_number}",
        f"closes #{issue_number}",
        f"closed #{issue_number}",
        f"resolve #{issue_number}",
        f"resolves #{issue_number}",
        f"resolved #{issue_number}",
    ]

    for format_str in github_formats:
        result = await pull_request_has_closing_keywords(issue_number, format_str)
        assert result is True, f"Format '{format_str}' should work"

    # Test that partial matches don't work
    false_positives = [
        f"This doesn't close#{issue_number}",  # Missing space
        f"This closes issue {issue_number}",  # Missing hash
        f"This closes #{issue_number}0",  # Extra digit
        f"This closes #a{issue_number}",  # Extra character
        f"This unclosed #{issue_number}",  # Wrong verb
    ]

    for body in false_positives:
        result = await pull_request_has_closing_keywords(issue_number, body)
        assert result is False, f"Body '{body}' should not match"
