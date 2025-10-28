"""Contains logic for synchronizing pull requests."""

import re
from pathlib import Path

import structlog
from githubkit.versions.latest.models import Issue, PullRequest
from structlog.contextvars import bound_contextvars

from github_ops_manager.github.adapter import GitHubKitAdapter
from github_ops_manager.processing.test_cases_processor import (
    extract_os_from_robot_filename,
    find_test_cases_files,
    load_test_cases_yaml,
    normalize_os_to_catalog_dir,
    save_test_cases_yaml,
    update_test_case_with_pr_metadata,
)
from github_ops_manager.schemas.default_issue import IssueModel, PullRequestModel
from github_ops_manager.synchronize.models import SyncDecision
from github_ops_manager.synchronize.utils import compare_github_field, compare_label_sets
from github_ops_manager.utils.helpers import generate_branch_name

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def pull_request_has_closing_keywords(issue_number: int, pull_request_body: str | None) -> bool:
    """Check if a pull request has closing keywords that reference an issue number."""
    logger.debug(
        "Analyzing pull request body for closing keywords",
        issue_number=issue_number,
        pull_request_body=pull_request_body,
    )
    closing_keywords = [
        "close",
        "closes",
        "closed",
        "fix",
        "fixes",
        "fixed",
        "resolve",
        "resolves",
        "resolved",
    ]
    if pull_request_body is None:
        logger.debug("Pull request body is None, so it cannot have closing keywords")
        return False

    for keyword in closing_keywords:
        # Create regex pattern that matches:
        # - Word boundary before keyword (\b)
        # - The keyword
        # - Word boundary after keyword (\b)
        # - Flexible whitespace (\s+)
        # - Hash symbol (#)
        # - Exact issue number
        # - Word boundary after issue number (\b)
        pattern = rf"\b{re.escape(keyword)}\s+#{issue_number}\b"

        if re.search(pattern, pull_request_body, re.IGNORECASE):
            logger.debug("Pull request body contains closing keyword", keyword=keyword, issue_number=issue_number, pattern=pattern)
            return True

    logger.debug("Pull request body does not contain any closing keywords", issue_number=issue_number)
    return False


async def get_pull_request_associated_with_issue(issue: Issue, existing_pull_requests: list[PullRequest]) -> PullRequest | None:
    """Get the pull request associated with the issue.

    The only way to do this is to parse the body of the pull request and look
    for closing keywords that reference the issue number. This is extremely
    hacky; it's also the only reasonable way to do this, as GitHub does not
    have an API for directly getting the pull request associated with an issue.
    """
    for pr in existing_pull_requests:
        logger.debug("Checking if pull request has closing keywords relating to issue", issue_number=issue.number, pull_request_body=pr.body)
        if await pull_request_has_closing_keywords(issue.number, pr.body):
            logger.debug("Pull request has closing keywords relating to issue", issue_number=issue.number, pull_request_body=pr.body)
            return pr
    logger.debug("No pull request has closing keywords relating to issue", issue_number=issue.number)
    return None


async def get_desired_pull_request_file_content(
    base_directory: Path, desired_issue: IssueModel, catalog_workflow: bool = False
) -> list[tuple[str, str]]:
    """Get the content of the desired pull request files.

    Args:
        base_directory: Base directory where files are located
        desired_issue: Issue model containing pull request information
        catalog_workflow: If True, transform .robot file paths to catalog structure

    Returns:
        List of tuples (file_path_in_pr, file_content)
    """
    if desired_issue.pull_request is None:
        raise ValueError("Desired issue has no pull request associated with it")
    files: list[tuple[str, str]] = []
    for file in desired_issue.pull_request.files:
        file_path = base_directory / file
        logger.info("Checking if file exists", file=file, file_path=str(file_path), base_directory=str(base_directory))
        if file_path.exists():
            file_content = file_path.read_text(encoding="utf-8")

            # Transform path if catalog workflow and file is a robot file
            if catalog_workflow and file.endswith(".robot"):
                filename = Path(file).name
                os_name = extract_os_from_robot_filename(filename)
                if os_name:
                    catalog_dir = normalize_os_to_catalog_dir(os_name)
                    catalog_path = f"catalog/{catalog_dir}/{filename}"
                    logger.info(
                        "Transformed robot file path for catalog",
                        original_path=file,
                        catalog_path=catalog_path,
                        os_name=os_name,
                        catalog_dir=catalog_dir,
                    )
                    files.append((catalog_path, file_content))
                else:
                    logger.warning("Could not extract OS from robot filename, using original path", filename=filename)
                    files.append((file, file_content))
            else:
                files.append((file, file_content))
        else:
            logger.warning("Pull Request file not found", file=file, issue_title=desired_issue.title)
    return files


async def decide_github_pull_request_file_sync_action(
    desired_file_data: list[tuple[str, str]],
    github_pull_request: PullRequest,
    github_adapter: GitHubKitAdapter,
) -> SyncDecision:
    """Compare a YAML pull request's file and a GitHub pull request, and decide whether to create, update, or no-op."""
    current_files = await github_adapter.list_files_in_pull_request(github_pull_request.number)
    for desired_file_name, desired_file_content in desired_file_data:
        for current_file in current_files:
            if current_file.filename == desired_file_name:
                github_file_content = await github_adapter.get_file_content_from_pull_request(
                    file_path=desired_file_name,
                    branch=github_pull_request.head.ref,
                )
                if github_file_content == desired_file_content:
                    return SyncDecision.NOOP
                else:
                    return SyncDecision.UPDATE
    return SyncDecision.CREATE


async def decide_github_pull_request_sync_action(desired_issue: IssueModel, existing_pull_request: PullRequest | None = None) -> SyncDecision:
    """Compare a YAML issue and a GitHub issue, and decide whether to create, update, or no-op the associated pull request."""
    if desired_issue.pull_request is None:
        raise ValueError("Desired issue has no pull request associated with it")

    if existing_pull_request is None:
        logger.info("Existing issue has no pull request linked to it, creating a new one", issue_title=desired_issue.title)
        return SyncDecision.CREATE

    # Compare relevant pull request fields
    pr_fields_to_compare = ["title", "body"]
    for field in pr_fields_to_compare:
        desired_value = getattr(desired_issue.pull_request, field, None)
        github_value = getattr(existing_pull_request, field, None)
        field_decision = await compare_github_field(desired_value, github_value)
        if field_decision == SyncDecision.UPDATE or field_decision == SyncDecision.CREATE:
            logger.info(
                "Pull request needs to be updated",
                issue_title=desired_issue.title,
                pr_field=field,
                current_value=github_value,
                new_value=desired_value,
            )
            return SyncDecision.UPDATE

    # Next, check the labels of the existing and desired pull request
    decision = await compare_label_sets(desired_issue.pull_request.labels, getattr(existing_pull_request, "labels", []))
    if decision == SyncDecision.UPDATE:
        logger.info(
            "Existing pull request labels do not match desired labels, updating the pull request",
            issue_title=desired_issue.title,
        )
        return SyncDecision.UPDATE

    logger.info(
        "Pull request is up to date",
        issue_title=desired_issue.title,
        pr_number=existing_pull_request.number,
        pr_title=existing_pull_request.title,
        pr_body=existing_pull_request.body,
    )
    return SyncDecision.NOOP


async def commit_files_to_branch(
    desired_issue: IssueModel,
    existing_issue: Issue,
    desired_branch_name: str,
    base_directory: Path,
    github_adapter: GitHubKitAdapter,
    catalog_workflow: bool = False,
) -> None:
    """Commit files to a branch.

    Args:
        desired_issue: Issue model containing pull request information
        existing_issue: GitHub Issue object
        desired_branch_name: Name of the branch to commit to
        base_directory: Base directory where files are located
        github_adapter: GitHub adapter for API calls
        catalog_workflow: If True, transform robot file paths to catalog structure
    """
    if desired_issue.pull_request is None:
        raise ValueError("Desired issue has no pull request associated with it")

    files_to_commit: list[tuple[str, str]] = []
    missing_files: list[str] = []
    logger.info("Preparing files to commit for pull request", issue_title=desired_issue.title, branch=desired_branch_name)
    for file_path in desired_issue.pull_request.files:
        try:
            files_to_commit = await get_desired_pull_request_file_content(base_directory, desired_issue, catalog_workflow)
        except FileNotFoundError as exc:
            logger.error("File for PR not found or unreadable", file=file_path, error=str(exc))
            missing_files.append(file_path)
    if missing_files:
        logger.error("Skipping PR creation due to missing files", files=missing_files, issue_title=desired_issue.title)
        raise ValueError("Skipping PR creation due to missing files")

    # Commit files to branch
    logger.info("Committing files to branch", issue_title=desired_issue.title, branch=desired_branch_name)
    commit_message = (
        f"chore: attach files for PR '{desired_issue.pull_request.title}' associated with issue '{desired_issue.title}' ({existing_issue.number})"
    )
    await github_adapter.commit_files_to_branch(desired_branch_name, files_to_commit, commit_message)


async def write_pr_metadata_to_test_cases(
    pr: PullRequest,
    catalog_repo_url: str,
    test_cases_dir: Path,
) -> None:
    """Write PR metadata back to test_cases.yaml files after catalog PR creation.

    Args:
        pr: GitHub PullRequest object with created PR information
        catalog_repo_url: Full URL to catalog repository
        test_cases_dir: Directory containing test_cases.yaml files
    """
    logger.info("Writing PR metadata to test cases files", pr_number=pr.number, test_cases_dir=str(test_cases_dir))

    # Get robot filename from PR files
    pr_files = [f.filename for f in pr.changed_files] if hasattr(pr, "changed_files") else []
    robot_files = [f for f in pr_files if f.endswith(".robot")]

    if not robot_files:
        logger.warning("No robot files found in PR, cannot write back metadata", pr_number=pr.number)
        return

    # For catalog PRs, the filename will be in format: catalog/<OS_NAME>/<filename>.robot
    # We need to extract just the filename
    robot_filename = Path(robot_files[0]).name

    logger.info("Processing robot file for metadata writeback", robot_filename=robot_filename, pr_number=pr.number)

    # Find test_cases.yaml files
    test_case_files = find_test_cases_files(test_cases_dir)

    if not test_case_files:
        logger.warning("No test case files found in directory", test_cases_dir=str(test_cases_dir))
        return

    # Search through test case files for matching test case
    for test_case_file in test_case_files:
        data = load_test_cases_yaml(test_case_file)
        if not data or "test_cases" not in data:
            continue

        test_cases = data["test_cases"]
        if not isinstance(test_cases, list):
            logger.warning("test_cases field is not a list", filepath=str(test_case_file))
            continue

        # Look for test case with matching generated_script_path
        # The generated_script_path might be just the filename or include a directory
        for test_case in test_cases:
            generated_script_path = test_case.get("generated_script_path")
            if generated_script_path and Path(generated_script_path).name == robot_filename:
                logger.info(
                    "Found matching test case, updating with PR metadata",
                    test_case_file=str(test_case_file),
                    generated_script_path=generated_script_path,
                )

                # Update test case with PR metadata
                update_test_case_with_pr_metadata(test_case, pr, catalog_repo_url)

                # Save updated YAML
                if save_test_cases_yaml(test_case_file, data):
                    logger.info("Successfully wrote PR metadata back to test case file", test_case_file=str(test_case_file))
                    return
                else:
                    logger.error("Failed to save test case file", test_case_file=str(test_case_file))
                    return

    logger.warning("No matching test case found for robot file", robot_filename=robot_filename)


async def sync_github_pull_request(
    desired_issue: IssueModel,
    existing_issue: Issue,
    github_adapter: GitHubKitAdapter,
    default_branch: str,
    base_directory: Path,
    existing_pull_request: PullRequest | None = None,
    testing_as_code_workflow: bool = False,
    catalog_workflow: bool = False,
    catalog_repo_url: str | None = None,
    test_cases_dir: Path | None = None,
) -> None:
    """Synchronize a specific pull request for an issue."""
    with bound_contextvars(
        desired_issue_title=desired_issue.title,
        existing_issue_title=existing_issue.title,
        existing_issue_number=existing_issue.number,
        existing_pull_request_number=existing_pull_request.number if existing_pull_request is not None else "None",
        existing_pull_request_title=existing_pull_request.title if existing_pull_request is not None else "None",
        existing_pull_request_body=existing_pull_request.body if existing_pull_request is not None else "None",
    ):
        # Ignoring type below because we know that the pull_request field is
        # not None at this point.
        pr: PullRequestModel = desired_issue.pull_request  # type: ignore
        if testing_as_code_workflow is True:
            pr.body = (
                f"**Quicksilver**: Automatically generated Pull Request for "
                f"issue #{existing_issue.number}, {existing_issue.title}. "
                f"Closes #{existing_issue.number}"
            )

        if pr.body is None:
            pr.body = f"Closes #{existing_issue.number}"
        pr_labels = pr.labels or []

        # Determine branch name
        desired_branch_name = pr.branch or generate_branch_name(existing_issue.number, desired_issue.title)

        # Ensure that pull request body has closing keywords. If it doesn't,
        # then we need to add them to the bottom of the body.
        if not await pull_request_has_closing_keywords(existing_issue.number, pr.body):
            pr.body = f"{pr.body}\n\nCloses #{existing_issue.number}"

        logger.info("Pull request body", body=pr.body, existing_issue_number=existing_issue.number, existing_issue_title=existing_issue.title)

        # Make overall PR sync decision
        pr_sync_decision = await decide_github_pull_request_sync_action(desired_issue, existing_pull_request=existing_pull_request)
        if pr_sync_decision == SyncDecision.CREATE:
            # Check if branch exists, create if not
            if not await github_adapter.branch_exists(desired_branch_name):
                logger.info("Creating branch for PR", branch=desired_branch_name, base_branch=default_branch)
                await github_adapter.create_branch(desired_branch_name, default_branch)
            else:
                logger.info("Branch already exists, skipping creation", branch=desired_branch_name)

            # Commit files to branch
            await commit_files_to_branch(desired_issue, existing_issue, desired_branch_name, base_directory, github_adapter, catalog_workflow)

            logger.info("Creating new PR for issue", branch=desired_branch_name, base_branch=default_branch)
            new_pr = await github_adapter.create_pull_request(
                title=pr.title,
                head=desired_branch_name,
                base=default_branch,
                body=pr.body,
            )
            logger.info("Created new PR", pr_number=new_pr.number, branch=desired_branch_name)
            await github_adapter.set_labels_on_issue(new_pr.number, pr_labels)
            logger.info("Set labels on new PR", pr_number=new_pr.number, labels=pr_labels)

            # Write PR metadata back to test_cases.yaml if catalog workflow
            if catalog_workflow and catalog_repo_url and test_cases_dir:
                logger.info("Catalog workflow enabled, writing PR metadata back to test cases")
                await write_pr_metadata_to_test_cases(new_pr, catalog_repo_url, test_cases_dir)
        elif pr_sync_decision == SyncDecision.UPDATE:
            if existing_pull_request is None:
                raise ValueError("Existing pull request not found")
            logger.info("Updating existing PR for issue", pr_number=existing_pull_request.number)
            await github_adapter.update_pull_request(
                pull_number=existing_pull_request.number,
                title=pr.title,
                body=pr.body,
            )
            await github_adapter.set_labels_on_issue(existing_pull_request.number, pr_labels)
            desired_file_data = await get_desired_pull_request_file_content(base_directory, desired_issue, catalog_workflow)
            pr_file_sync_decision = await decide_github_pull_request_file_sync_action(desired_file_data, existing_pull_request, github_adapter)
            if pr_file_sync_decision == SyncDecision.CREATE:
                # The branch will already exist, so we don't need to create it.
                # However, we do need to commit the files to the branch.
                await commit_files_to_branch(desired_issue, existing_issue, desired_branch_name, base_directory, github_adapter, catalog_workflow)


async def sync_github_pull_requests(
    desired_issues: list[IssueModel],
    existing_issues: list[Issue],
    existing_pull_requests: list[PullRequest],
    github_adapter: GitHubKitAdapter,
    default_branch: str,
    base_directory: Path,
    testing_as_code_workflow: bool = False,
    catalog_workflow: bool = False,
    catalog_repo_url: str | None = None,
    test_cases_dir: Path | None = None,
) -> None:
    """Process pull requests for issues that specify a pull_request field.

    Args:
        desired_issues: List of desired issues from YAML
        existing_issues: List of existing issues from GitHub
        existing_pull_requests: List of existing pull requests from GitHub
        github_adapter: GitHub adapter for API calls
        default_branch: Default branch name
        base_directory: Base directory where files are located
        testing_as_code_workflow: If True, augment PR bodies for Testing as Code
        catalog_workflow: If True, enable catalog workflow features
        catalog_repo_url: Full URL to catalog repository (required if catalog_workflow=True)
        test_cases_dir: Directory containing test_cases.yaml files (required if catalog_workflow=True)
    """
    desired_issues_with_prs = [issue for issue in desired_issues if issue.pull_request is not None]
    for desired_issue in desired_issues_with_prs:
        existing_issue = next((issue for issue in existing_issues if issue.title == desired_issue.title), None)
        if existing_issue is not None:
            logger.info(
                "Existing issue found",
                desired_issue_title=desired_issue.title,
                existing_issue_title=existing_issue.title,
                existing_issue_number=existing_issue.number,
            )
        else:
            logger.error("Desired issue not found in existing issues", desired_issue_title=desired_issue.title)
            continue

        # Find existing PR associated with existing issue, if any.
        existing_pr = await get_pull_request_associated_with_issue(existing_issue, existing_pull_requests)

        await sync_github_pull_request(
            desired_issue,
            existing_issue,
            github_adapter,
            default_branch,
            base_directory,
            existing_pull_request=existing_pr,
            testing_as_code_workflow=testing_as_code_workflow,
            catalog_workflow=catalog_workflow,
            catalog_repo_url=catalog_repo_url,
            test_cases_dir=test_cases_dir,
        )
