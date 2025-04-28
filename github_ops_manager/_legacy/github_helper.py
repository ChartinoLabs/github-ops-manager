"""House various GitHub functions required by Quicksilver."""

import datetime
import os
import re
import sys
import time
from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from typing import Tuple

import yaml
from core.shared_utils import logger, render_github_issue_description
from github import (
    BadCredentialsException,
    Github,
    GithubException,
    GithubObject,
    InputGitAuthor,
    UnknownObjectException,
)
from requests.exceptions import HTTPError

__author__ = "Andrea Testino"
__email__ = "atestini@cisco.com"
__license__ = """
################################################################################
# Copyright (c) 2023 Cisco and/or its affiliates.
#
# This software is licensed to you under the terms of the Cisco Sample
# Code License, Version 1.1 (the "License"). You may obtain a copy of the
# License at
#
#                https://developer.cisco.com/docs/licenses
#
# All use of the material herein must be in accordance with the terms of
# the License. All rights not expressly granted by the License are
# reserved. Unless required by applicable law or agreed to separately in
# writing, software distributed under the License is distributed on an "AS
# IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
# or implied.
################################################################################
"""


def retry_on_exception(max_retries=5, default_backoff=60):
    """Decorator for retrying a function when it throws specific exceptions.

    This decorator will retry a function call up to `max_retries` times in the case of
    a `GithubException` or `HTTPError` with a status of 403. In such cases,
    it will respect the `retry-after` header from the server, if available.

    Parameters:
    -----------
    max_retries : int
        Maximum number of retries.
    default_backoff : int
        Default backoff time in seconds when no other time is dictated by headers.

    Returns:
    --------
    callable
        Decorated function that includes retry logic.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except (HTTPError, GithubException) as e:
                    # Extract status code and response based on exception type
                    if isinstance(e, HTTPError):
                        status_code = e.response.status_code
                        response = e.response
                        message = response.json().get("message", "").lower()
                    else:  # GithubException
                        status_code = e.status
                        response = e.headers if hasattr(e, "headers") else {}
                        message = str(e.data.get("message", "")).lower() if hasattr(e, "data") else ""

                    if status_code in [403, 429]:
                        retry_after = response.get("Retry-After") if isinstance(response, dict) else None
                        x_rate_limit_reset = response.get("X-RateLimit-Reset") if isinstance(response, dict) else None

                        if "secondary rate limit" in message:
                            logger.warning(f"Secondary rate limit exceeded: {message}")
                            if retry_after:
                                wait_time = int(retry_after)
                                logger.warning(f"Will wait for {wait_time} seconds based on Retry-After header")
                            elif x_rate_limit_reset:
                                wait_time = max(int(x_rate_limit_reset) - int(time.time()), 1)
                                logger.warning(f"Will wait until rate limit reset: {wait_time} seconds")
                            else:
                                wait_time = min(2**retries * 10, default_backoff)  # Exponential backoff starting at 10s
                                logger.warning(f"No rate limit guidance, will wait for {wait_time} seconds")

                            logger.error(
                                f"Retry {retries+1}/{max_retries}: API call failed with status {status_code}, message '{message}'. "
                                f"Retrying after {wait_time} seconds..."
                            )
                            time.sleep(wait_time)
                            retries += 1
                            continue

                    logger.error(f"Unhandled GitHub exception with status {status_code}: {e}")
                    raise
                except Exception as e:
                    logger.error(f"An unexpected error type: {type(e)}, occurred with details: {e}")
                    raise

            # If we've exhausted all retries, raise a more informative exception
            raise Exception(f"Maximum retry attempts ({max_retries}) exceeded. Last error: Secondary rate limit exceeded")

        return wrapper

    return decorator


def track_github_api_usage(func):
    """Decorator to log the GitHub API usage before and after the function call.

    Args:
        func (callable): The function to be decorated.

    Returns:
        callable: The wrapped function.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        gh = args[0].gh if args and hasattr(args[0], "gh") else None

        if gh:
            rate_limit_before = gh.get_rate_limit().core
            logger.debug(f"Rate limit before calling {func.__name__}: {rate_limit_before.remaining}/{rate_limit_before.limit}")

        result = func(*args, **kwargs)

        if gh:
            rate_limit_after = gh.get_rate_limit().core
            logger.debug(f"Rate limit after calling {func.__name__}: {rate_limit_after.remaining}/{rate_limit_after.limit}")

        return result

    return wrapper


class RepoHandler:
    """GitHub Repository handler to clone the repository and manage Pull Requests.

    Provides methods for interacting with GitHub repositories including checking if a
    branch exists, and creating or updating pull requests.

    Parameters:
    -----------
    github_token : str
        GitHub token for authentication.
    github_repo_url : str
        URL of the GitHub repository to clone.
    github_base_url : str
        Base URL of GitHub.

    Attributes:
    -----------
    gh : Github
        Github instance for API interactions.
    repository : github.Repository
        Repository object.

    Example Usage:
    --------------
    repo_handler = RepoHandler('token', 'repo_url', 'base_url')
    """

    @retry_on_exception(max_retries=5)
    def __init__(self, github_token: str, github_repo_url: str, github_base_url: str) -> None:
        """Initialize GitHub related items.

        Initializes the GitHub API client and fetches the repository object based on the
        given GitHub token, repository URL, and base URL.

        Returns:
        --------
        None
        """
        self.github_token = github_token
        self.github_repo_url = github_repo_url
        self.github_base_url = github_base_url
        self.gh = Github(base_url=self.github_base_url, login_or_token=self.github_token)
        self.repository = self.get_github_repository()

    # @track_github_api_usage
    @retry_on_exception(max_retries=5)
    def get_github_repository(self):
        """Retrieve the Github repository based on the URL.

        Returns:
            Union[None, Github.Repository.Repository]: The targeted repository if found, else None.
        """
        try:
            for repo in self.gh.get_user().get_repos():
                if repo.clone_url == self.github_repo_url:
                    return repo
        except BadCredentialsException:
            logger.error("The provided GitHub token is invalid or expired. Please check your token and try again.")
            sys.exit()
        except UnknownObjectException:
            logger.error(
                "The repository cannot be found. This might be due to it being private and the token not having access, or the repository does not exist."
            )
            sys.exit()
        except GithubException as e:
            logger.error(
                "A GitHub error occurred: %s",
                e.data,
            )
            raise

        # We'll end up here if the token is valid, but QS has not been added to the repo
        # This is a limitation of Gh API and is by design
        logger.warning(
            "Could not find GitHub repository matching '%s'. Please verify if the repository exists, the provided token has the necessary permissions, and that quicksilver-gen has been added as a member of the repository.",
            self.github_repo_url,
        )
        sys.exit()

    # Cloning happens via SSH so ssh-keys on host running must be set
    # Not sure if this will break CI/CD so I can flip back to HTTPS later
    @retry_on_exception(max_retries=5)
    # @track_github_api_usage
    def clone_repository(self, path: str) -> None:
        """Clone the repository to a given path.

        Args:
            path (str): The path to clone the repository to.
        """
        try:
            os.system(f"git clone {self.repository.ssh_url} {path}")
        except Exception as e:
            logger.error(f"Failed to clone the repository: {e}")
            sys.exit(1)

    # @track_github_api_usage
    @retry_on_exception(max_retries=5)
    def delete_comments_and_close_open_prs(self):
        """Deletes all types of comments, including the PR's body, from each open PR with no assignee,
        and then closes the PRs in the GitHub repository.

        Returns:
        --------
        None

        Raises:
        -------
        GithubException: If an error occurs while interacting with the GitHub API.
        """
        try:
            pull_requests = self.repository.get_pulls(state="open")
            for pr in pull_requests:
                if pr.assignee is None:
                    # Delete issue (a PR is technically also an issue) comments
                    issue_comments = pr.get_issue_comments()
                    for comment in issue_comments:
                        comment.delete()

                    # Delete review comments
                    review_comments = pr.get_comments()
                    for comment in review_comments:
                        comment.delete()

                    # Leave a comment on the PR to notify the user
                    pr.create_issue_comment(
                        "**Quicksilver**: SME has triggered API to automatically delete all PRs without an assignee. This is likely to force regeneration of the Pull Request (PR) again with the latest changes. \n"
                        "If you believe this is an error, please reach out to the TL/SME."
                    )

                    # Clear PR's body and close it
                    pr.edit(body="")
                    pr.edit(state="closed")

                    logger.info(f"Closed and deleted comments for PR {pr.number}")

        except GithubException as e:
            logger.error(f"An error occurred while processing PRs: {e}")
            raise

    # @track_github_api_usage
    @retry_on_exception(max_retries=5)
    def get_open_issues_content(self):
        """Retrieve the content of all open issues in a GitHub repository, while filtering based on specific conditions.

        This function fetches all open issues and filters them based on several criteria:
        - Whether the issue is actually a pull request.
        - Whether the issue is linked to an open pull request.
        - Whether the issue has a label "ready-for-script-creation".

        Parameters:
        -----------
        self : object
            An instance of the class that contains this method, expected to have a `repository` attribute representing the GitHub repository.

        Returns:
        --------
        Tuple[List[Dict], bool, List[int]]
            A tuple containing three elements:
            - A list of dictionaries, where each dictionary contains the following keys:
                - 'issue_number': int : The unique number of the issue.
                - 'issue_title': str : The title of the issue.
                - 'issue_body': str : The content body of the issue.
            - A boolean flag `no_new_issues_to_process` indicating if no new issues were found that match the criteria for processing.
            - A list of issue numbers that were found to have linked PRs despite having the "ready-for-script-creation" label.

        Exceptions:
        -----------
        GithubException
            This exception is caught and logged if the function fails to get open issues. The program will exit with status code 1.

        Side Effects:
        -------------
        1. API calls to GitHub to fetch open issues and pull requests.
        2. Logging debug, info, and error messages.

        Example Usage:
        --------------
        # Assuming `obj` is an instance of the class containing this method
        result = obj.get_open_issues_content()

        # Result will be a tuple (List of Dictionaries, Boolean Flag)
        """
        open_issues_content = []
        no_new_issues_to_process = True
        issues_with_linked_prs = []

        try:
            open_issues = self.repository.get_issues(state="open")
            open_pulls = list(self.repository.get_pulls(state="all"))

            linked_issue_numbers = set()
            for pull in open_pulls:
                linked_issue_number = self.extract_issue_number_from_pull(pull)
                if linked_issue_number:
                    linked_issue_numbers.add(linked_issue_number)
                    logger.debug(f"Pull request #{pull.number} is linked with issue #{linked_issue_number}")

            for issue in open_issues:
                issue_number = issue.number
                issue_title = issue.title
                issue_labels = [label.name for label in issue.labels]
                logger.debug(f"Scanning GitHub issue #{issue_number} titled {issue_title}")

                if not isinstance(issue._pull_request, type(GithubObject.NotSet)):
                    logger.debug(f"Skipping #{issue_number} as it is actually a pull request.")
                    continue

                github_issue_attributes = {
                    "issue_number": issue.number,
                    "issue_title": issue.title,
                    "issue_body": issue.body,
                    "issue_purpose": "",
                    "labels": issue_labels,
                    "has_linked_pr": issue_number in linked_issue_numbers,
                }

                if issue_number in linked_issue_numbers:
                    if "ready-for-script-creation" in issue_labels:
                        logger.info(
                            f"Issue #{issue_number}, {issue_title} has 'ready-for-script-creation' label but already has a linked PR. Marking for label update."
                        )
                        issues_with_linked_prs.append(github_issue_attributes)
                    else:
                        logger.debug(f"Skipping issue #{issue_number}, {issue_title} as it already has a linked PR.")
                    continue

                purpose_found = False
                # Iterate through comments to find specific markdown header
                # indicating a "purpose" field was injected at some point in time
                for comment in issue.get_comments():
                    header_marker = "## What is the purpose of this test case?"
                    if header_marker in comment.body:
                        header_index = comment.body.find(header_marker) + len(header_marker)
                        start_of_content = comment.body.find("\n", header_index) + 1
                        # Extract everything below the markdown header
                        purpose_found = comment.body[start_of_content:].strip()
                        github_issue_attributes["issue_purpose"] = purpose_found
                        # Not breaking here b/c I want the latest "purpose" comment
                        # It is possible (although rare) that it was updated

                if purpose_found:
                    github_issue_attributes["issue_purpose"] = purpose_found

                open_issues_content.append(github_issue_attributes)
                no_new_issues_to_process = False

            return open_issues_content, no_new_issues_to_process, issues_with_linked_prs

        except GithubException as e:
            logger.error(f"Failed to get open issues: {e}")
            raise

    @retry_on_exception(max_retries=5)
    def extract_issue_number_from_pull(self, pull):
        """Extract the linked issue number from a pull request description.

        Args:
            pull (github.PullRequest.PullRequest): The pull request object.

        Returns:
            int or None: The linked issue number if found, otherwise None.
        """
        pr_body = pull.body if pull.body else ""
        issue_numbers = re.findall(r"Closes #(\d+)", pr_body)
        if issue_numbers:
            # Currently only returning the first match
            logger.debug(f"Extracted issue numbers {issue_numbers} from PR #{pull.number}")
            return int(issue_numbers[0])
        return None

    # @track_github_api_usage
    def branch_exists(self, branch_name):
        """Check if a branch exists in the GitHub repository.

        Parameters:
        -----------
        branch_name : str
            Name of the branch to check.

        Returns:
        --------
        bool
            True if the branch exists, False otherwise.
        """
        try:
            self.repository.get_branch(branch=branch_name)
            return True
        except GithubException:
            return False

    @retry_on_exception(max_retries=5)
    def create_or_update_pull_request(self, issue, new_file_path_in_repo, combined_content, label=None):
        """Create or update a GitHub Pull Request with the specified issue, file path, and content.

        This function calls `create_pull_request_with_issue` to actually create or update the pull request.

        Parameters:
        -----------
        issue : dict
            Dictionary containing issue data including issue number and title.
        new_file_path_in_repo : str
            The new file path where the changes should be committed within the repository.
        combined_content : str
            The new content that should be committed to the file.
        label : str, optional
            An additional label to be added to the pull request.

        Returns:
        --------
        None

        Example Usage:
        --------------
        create_or_update_pull_request(github_issue_attributes, 'path/to/file', 'file_content')

        Note:
        -----
        - This function is essentially a wrapper for `create_pull_request_with_issue`.
        - The pull request creation is subject to the retry policy specified in the decorator
        applied to `create_pull_request_with_issue`.
        """
        self.create_pull_request_with_issue(
            github_issue_attributes=issue,
            file_path=new_file_path_in_repo,
            file_content=combined_content,
            label=label,
        )

    @retry_on_exception(max_retries=5)
    # @track_github_api_usage
    def create_pull_request_with_issue(
        self,
        github_issue_attributes: dict,
        file_path: str,
        file_content: str,
        label: str = None,
    ) -> None:
        """Creates a Pull Request linked to a specific issue.

        This function creates a new branch, commits a file to it, and then creates a pull request.
        The pull request is linked to the issue specified in `github_issue_attributes`.

        Parameters:
        -----------
        github_issue_attributes : dict
            Dictionary containing details of the issue.
        file_path : str
            Path where the file needs to be committed.
        file_content : str
            Content that needs to be committed to the file.
        label : str, optional
            An additional label to be added to the pull request.

        Returns:
        --------
        None

        Note:
        -----
        - This function is retried up to 5 times in the case of specific exceptions,
          as configured by the `retry_on_exception` decorator.
        """
        issue_number = github_issue_attributes["issue_number"]
        issue_title = github_issue_attributes["issue_title"]

        # Extract the directory part from the file path
        dir_path = os.path.dirname(file_path)
        gitkeep_path = f"{dir_path}/.gitkeep"

        try:
            logger.debug(f"Starting PR creation for issue #{issue_number}")
            # Create a new branch
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

            # Create sanitized title
            issue_title_sanitized = (
                issue_title.replace(" ", "_")
                .replace("/", "_")
                .replace(":", "")
                .replace("[", "")
                .replace("]", "")
                .replace("(", "")
                .replace(")", "")
                .replace(",", "")
                .replace("-", "_")
                .replace("'", "")
                .replace("&", "and")
                .lower()
            )

            issue_title_sanitized = re.sub(r"_{2,}", "_", issue_title_sanitized)

            new_branch_name = f"genai/{issue_number}_{timestamp}/{issue_title_sanitized}"

            default_branch = self.repository.default_branch  # Determine the default branch

            if not self.branch_exists(new_branch_name):
                try:
                    main_branch = self.repository.get_branch(default_branch)
                    self.repository.create_git_ref(ref=f"refs/heads/{new_branch_name}", sha=main_branch.commit.sha)
                except GithubException as e:
                    logger.error(f"Failed to create a new branch {new_branch_name} based on {default_branch}: {e}")
                    raise
            else:
                logger.warning(f"Branch {new_branch_name} already exists.")

            logger.debug(f"Committing file to branch {new_branch_name}")

            # Commit the file to the new branch
            author = InputGitAuthor("quicksilver-gen", "quicksilver.gen@cisco.com")
        except Exception as e:
            logger.error(f"An error occurred while creating the PR for issue #{issue_number}: {e}")
            raise

        # Check if the directory exists, if not create it
        # This is because OS will be dynamic
        try:
            self.repository.get_contents(gitkeep_path, ref=new_branch_name)
        except GithubException:
            # Create the .gitkeep file to simulate directory creation
            self.repository.create_file(
                path=gitkeep_path,
                message=f"Create directory for issue #{issue_number}",
                content="",
                branch=new_branch_name,
                author=author,
            )

        # Create the actual file
        self.repository.create_file(
            path=file_path,
            message=f"Add auto-generated file for issue #{issue_number}",
            content=file_content,
            branch=new_branch_name,
            author=author,
        )

        logger.debug(f"Creating Pull Request for branch {new_branch_name}")

        # Create a pull request
        pr = self.repository.create_pull(
            title=f"GenAI, Review: {issue_title}",
            body=f"**Quicksilver**: Automatically generated Pull Request for issue #{issue_number}, {issue_title}. Closes #{issue_number}",
            base=default_branch,
            head=new_branch_name,
        )

        # Set labels
        labels = ["GenAI", "Quicksilver"]
        if label:
            labels.append(label)
        pr.set_labels(*labels)

        # Comment on the PR with issue # and link to the issue
        pr.create_issue_comment(f"Linked to issue #{issue_number}")
        logger.debug(f"Successfully created Pull Request #{pr.number} for issue #{issue_number}")

    @retry_on_exception(max_retries=5)
    # @track_github_api_usage
    def get_file_contents(self, file_name: str, return_sha: bool = False) -> str | None | Tuple[str | None, str | None]:
        """Retrieve the content of a specified file from the GitHub repository.

        This method searches the repository for a file with the given name and returns its contents, and optionally its SHA.
        It is capable of navigating through directories within the repository. For large files (over 1MB), it fetches the file
        content as a Git blob due to size limitations on the regular content API.

        Parameters:
        -----------
        file_name : str
            The name of the file whose contents are to be fetched.
        return_sha : bool, optional
            Whether to return the SHA hash of the file along with its contents. Defaults to False.

        Returns:
        --------
        Optional[str] or Tuple[Optional[str], Optional[str]]
            - The content of the file as a string if the file is found, None otherwise.
            - If return_sha is True, returns a tuple of the content and the SHA hash of the file, with None values if not found.

        Raises:
        -------
        GithubException
            Captures and logs any exceptions that occur during the file content retrieval process.

        Logging:
        --------
        - Logs an error message if there is an exception during the file content fetch.
        - Logs a warning if no file with the given name is found in the repository.

        Note:
        -----
        - The method begins at the root of the repository and searches through all directories.
        - It handles large files differently from smaller ones due to API limitations.
        - The content is decoded from base64 for large files and directly decoded for smaller files.
        - In case of any errors or if the file is not found, the method returns None or (None, None) if return_sha is True.
        """
        try:
            logger.debug(f"Fetching file content for {file_name} from GitHub")
            contents = self.repository.get_contents("")
            while contents:
                file_content = contents.pop(0)  # process each file one at a time
                if file_content.type == "dir":  # navigate through sub-dirs
                    contents.extend(self.repository.get_contents(file_content.path))
                elif file_content.name == file_name:
                    if file_content.size > 1e6:  # For large files, >1MB
                        # Fetch the blob for large files
                        # https://github.com/PyGithub/PyGithub/issues/2345
                        blob = self.repository.get_git_blob(file_content.sha)
                        file_data = b64decode(blob.content).decode("utf-8")
                    else:
                        file_data = file_content.decoded_content.decode("utf-8")

                    logger.info(f"Successfully fetched content for file: {file_name}")
                    if return_sha:
                        return (file_data, file_content.sha)
                    else:
                        return file_data

        except GithubException as e:
            logger.error(f"An error occurred while fetching the file content: {e}")
            return (None, None) if return_sha else None

        logger.warning(f"No file named {file_name} found in the repository.")
        return (None, None) if return_sha else None

    # @track_github_api_usage
    @retry_on_exception(max_retries=5)
    def create_labels(self):
        """Create or update GitHub labels with pre-defined name and color configurations.

        The method iterates over a dictionary of label names and their respective color codes.
        It compares them against the existing labels in the GitHub repository, updating or creating them as necessary.

        Parameters:
        -----------
        None

        Returns:
        --------
        None

        Exceptions:
        -----------
        GithubException:
            - Captures any exception that occurs while interacting with GitHub APIs.

        Logging:
        --------
        - Logs information about the creation or updating of labels.
        - Logs errors if exceptions are encountered.

        Example Usage:
        --------------
        repo_handler_object.create_labels()

        Note:
        -----
        - The labels are pre-defined in a dictionary inside the function.
        - The function updates a label's color if it already exists but has a different color.
        - Label names and colors are hard-coded within the method.

        """
        try:
            labels_to_create = {
                "changes-requested": "ee0701",
                "under-review": "fbca04",
                "parameters-needed": "5319e7",
                "pending-DUT-configuration": "fbca04",
                "To-Be-Considered": "555555",
                "GenAI-Ignore": "555555",
                "new-test-case": "84b6eb",
                "Review-Show-CLI": "ee0701",
                "Review-Device-Connection": "ee0701",
                "Dict-Diff-KW-Detected": "ee0701",
                "GenAI": "0e8a16",
                "ready-for-script-creation": "0e8a16",
                "needs-criteria": "5319e7",
                "Criteria-Ready-For-SME-Review": "94acf8",
                "PR-Created-Linked": "a2eeef",
                "needs-scope-review": "C21FEB",
            }

            existing_labels = {label.name: label for label in self.repository.get_labels()}

            for label_name, color in labels_to_create.items():
                if label_name in existing_labels:
                    existing_label = existing_labels[label_name]
                    if existing_label.color != color:
                        existing_label.edit(name=label_name, color=color)
                        logger.info(f"Updated color of label '{label_name}' to {color}")
                    else:
                        logger.info(f"Label '{label_name}' already exists with correct color, skipping")
                else:
                    self.repository.create_label(name=label_name, color=color)
                    logger.info(f"Created label '{label_name}'")
        except GithubException as e:
            logger.error(f"Exception occurred: {e}")

    @staticmethod  # Dont need to use class attributes here
    def load_issues_from_yaml(file_path: str) -> list:
        """Load issues from a YAML file.

        Args:
            file_path (str): The path to the YAML file containing issue details.

        Returns:
            list: List of dictionaries representing issues.
        """
        with open(file_path) as file:
            logger.debug(f"Loading issues from {file_path}")
            issues_data = yaml.safe_load(file)
        logger.debug(f"We are done loading issues from {file_path}")
        return issues_data["issues"]

    @retry_on_exception(max_retries=5)
    # @track_github_api_usage
    def create_or_update_issue(self, github_issue_attributes: dict, open_issues_dict: dict) -> None:
        """Create or update a GitHub issue based on provided issue data.

        This method checks if an issue with the same title already exists in the given dictionary of open issues.
        If it exists, the issue is updated with the new data; otherwise, a new issue is created.

        Parameters:
        -----------
        github_issue_attributes : dict
            A dictionary containing details of the issue to be created or updated.
            Expected to have keys like 'title', 'body', and 'labels'.

        open_issues_dict : dict
            A dictionary where keys are issue titles, and values are corresponding GitHub issue objects.
            This dictionary is used to check if an issue already exists.

        Returns:
        --------
        None

        Raises:
        -------
        GithubException
            Captures exceptions related to GitHub API interactions, typically raised from within
            the `create_issue` or `update_issue` methods.

        Logging:
        --------
        - Logs the process of checking, creating, or updating issues.
        - Errors are logged if any exception is encountered during the issue creation or update process.

        Example Usage:
        --------------
        repo_handler.create_or_update_issue(github_issue_attributes, open_issues_dict)

        Note:
        -----
        - The method assumes that 'open_issues_dict' contains all current open issues from the GitHub repository.
        - It is expected that the 'github_issue_attributes' dictionary will have the necessary keys and values required to create or update an issue.
        - The method delegates the actual creation and updating of issues to `create_issue` and `update_issue` methods respectively.
        """
        existing_issue = open_issues_dict.get(github_issue_attributes["title"])

        if existing_issue:
            self.update_issue(existing_issue, github_issue_attributes)
        else:
            self.create_issue(github_issue_attributes)

    # TODO: Need to implement a global rate limit handler that can control th rate of requests across all threads at once
    @retry_on_exception(max_retries=5)
    # @track_github_api_usage
    def create_issues(self, yaml_file_path: str) -> None:
        """Create GitHub issues in parallel from a specified YAML file.

        This method reads a list of issue data from a YAML file and uses a ThreadPoolExecutor
        to create or update issues concurrently. It first fetches all open issues from the GitHub repository
        to prevent redundant API calls during the issue creation/update process. Each issue from the YAML file
        is then processed to either create a new issue or update an existing one.

        Parameters:
        -----------
        yaml_file_path : str
            The filesystem path to the YAML file containing the issue data.
            The YAML file is expected to contain a list of issue details.

        Returns:
        --------
        None

        Raises:
        -------
        Exception
            Captures and logs any exceptions that occur during the processing of each individual issue.

        Logging:
        --------
        - Logs the number of issues loaded from the YAML file.
        - Logs the completion of the issue processing.
        - Errors are logged if any exception is encountered during the processing of issues.

        Example Usage:
        --------------
        repo_handler.create_issues('path/to/issues.yaml')

        Note:
        -----
        - The YAML file should be structured in a way that each entry contains the required data for an issue.
        - The method uses multithreading to improve efficiency, especially when dealing with a large number of issues.
        - The global rate limit handler mentioned in the TODO is intended to manage the rate of GitHub API requests across all threads.
        """
        issues_list = self.load_issues_from_yaml(yaml_file_path)

        # Fetch open issues only once
        logger.debug(f"Fetching open issues from GitHub for {yaml_file_path}")
        open_issues = self.repository.get_issues(state="all")
        open_issues_dict = {issue.title: issue for issue in open_issues}

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                (
                    github_issue_attributes["title"],
                    executor.submit(
                        self.create_or_update_issue,
                        github_issue_attributes,
                        open_issues_dict,
                    ),
                )
                for github_issue_attributes in issues_list
            ]

            for title, future in futures:
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Error processing issue with title {title}: {e}")

    @retry_on_exception(max_retries=5)
    def update_issue(self, existing_issue, github_issue_attributes: dict) -> None:
        """Update an existing GitHub issue based on the provided issue data.

        This method updates the body and labels of an existing GitHub issue. It compares the current issue data
        with the new data provided and makes necessary updates. The issue's body is rendered from the issue data
        using a Jinja template, and labels are updated to reflect any changes in the expected labels.

        Parameters:
        -----------
        existing_issue : github.Issue
            The GitHub issue object that needs to be updated.

        github_issue_attributes : dict
            A dictionary containing updated issue details. This includes fields like title, purpose, commands,
            pass_criteria, etc. used to render the issue body, and 'labels' (a list of label names).

        Returns:
        --------
        None

        Logging:
        --------
        - Logs updates made to the issue's body and labels.
        - Logs a message if no update is required for the issue.
        """
        update_required = False

        # Render the issue body from the issue data
        rendered_body = render_github_issue_description(github_issue_attributes)

        # Update issue body if needed and if rendering was successful
        if rendered_body is not None and existing_issue.body != rendered_body:
            existing_issue.edit(body=rendered_body)
            logger.info(f"Updated body of issue '{github_issue_attributes['title']}'")
            update_required = True
        elif rendered_body is None:
            logger.error(f"Failed to render body for issue '{github_issue_attributes['title']}'")

        # Get existing labels from GitHub issue
        existing_labels = {label.name for label in existing_issue.get_labels()}

        # Get expected labels from github_issue_attributes SOT
        expected_labels = set(github_issue_attributes.get("labels", []))

        # Find labels to be added and removed
        labels_to_add = expected_labels - existing_labels
        labels_to_remove = existing_labels - expected_labels

        # Update labels if needed
        if labels_to_add or labels_to_remove:
            for label in labels_to_add:
                existing_issue.add_to_labels(label)
                logger.info(f"Added label '{label}' to issue '{github_issue_attributes['title']}'")

            for label in labels_to_remove:
                existing_issue.remove_from_labels(label)
                logger.info(f"Removed label '{label}' from issue '{github_issue_attributes['title']}'")

            update_required = True

        # Add a comment if 'purpose' key is present and not already added as a comment
        if "purpose" in github_issue_attributes:
            comment_text = f"## What is the purpose of this test case?\n\n{github_issue_attributes['purpose']}"
            purpose_comment_exists = any(comment.body == comment_text for comment in existing_issue.get_comments())
            if not purpose_comment_exists:
                existing_issue.create_comment(comment_text)
            else:
                logger.info(f"Comment regarding purpose with header already exists for issue '{github_issue_attributes['title']}'.")

        if not update_required:
            logger.info(f"No update required for issue '{github_issue_attributes['title']}'.")

    def create_issue(self, github_issue_attributes: dict) -> None:
        """Create a new GitHub issue based on the provided issue data.

        This method creates a new issue in the GitHub repository. It renders the issue body from the provided
        issue data using a template, and sets the title and labels. If an exception occurs during the issue
        creation process, it is caught and handled appropriately.

        Parameters:
        -----------
        github_issue_attributes : dict
            A dictionary containing the details for the issue to be created. The dictionary should include
            fields needed to render the issue body (title, purpose, commands, etc.) and 'labels' for any
            labels to be attached to the issue.

        Returns:
        --------
        None

        Raises:
        -------
        GithubException
            Captures and handles exceptions related to GitHub API interactions, typically raised
            during the issue creation process.

        Logging:
        --------
        - Logs the successful creation of an issue, including any labels that were added.
        - Errors are logged and handled if any exceptions occur during issue creation.
        """
        try:
            # Render the issue body from the issue data
            rendered_body = render_github_issue_description(github_issue_attributes)
            if rendered_body is None:
                logger.error(f"Failed to render body for issue '{github_issue_attributes['title']}'")
                rendered_body = ""  # Fallback to empty string if rendering fails

            new_issue = self.repository.create_issue(
                title=github_issue_attributes["title"],
                body=rendered_body,
                labels=github_issue_attributes.get("labels", []),
            )
            logger.info(f"Created issue '{github_issue_attributes['title']}' with labels {github_issue_attributes.get('labels', [])}")

            if "purpose" in github_issue_attributes:
                comment_text = f"## What is the purpose of this test case?\n\n{github_issue_attributes['purpose']}"
                new_issue.create_comment(comment_text)

        except GithubException as e:
            self.handle_github_exception(e, github_issue_attributes)

    def handle_github_exception(self, e, github_issue_attributes: dict) -> None:
        """Handle GithubException during issue creation.

        Args:
            e (GithubException): The GithubException instance.
            github_issue_attributes (dict): Dictionary containing issue details.

        Returns:
            None
        """
        if e.status == 422:
            error_data = e.data.get("errors", [])
            for error in error_data:
                if error.get("field") == "body" and error.get("message") == "body is too long (maximum is 65536 characters)":
                    labels_with_error = github_issue_attributes.get("labels", [])
                    labels_with_error.append("Body-TooLong-Trim-YAML")
                    self.repository.create_issue(title=github_issue_attributes["title"], labels=labels_with_error)
                    logger.warning(f"Created issue '{github_issue_attributes['title']}' with 'Body-TooLong-Review-YAML' label due to long body")
                    break
            else:
                logger.error(f"An unknown validation error occurred: {e}")
        else:
            logger.error(f"An unknown error occurred: {e}")

    # @track_github_api_usage
    @retry_on_exception(max_retries=5)
    def commit_file_to_github(self, github_file_path: str, commit_message: str, local_file_path: str):
        try:
            # Read local file content
            with open(local_file_path) as f:
                local_file_data = f.read()

            repo_file_data, sha = self.get_file_contents(github_file_path, return_sha=True)

            if repo_file_data is not None and local_file_data == repo_file_data:
                logger.debug(f"No changes detected for {github_file_path}; commit skipped.")
                return

            logger.debug(f"Committing file {github_file_path} to GitHub, local file and repo file are different.")
            author = InputGitAuthor("quicksilver-gen", "quicksilver.gen@cisco.com")

            if sha is not None:
                # Update the file if it exists
                self.repository.update_file(
                    path=github_file_path,
                    message=commit_message,
                    content=local_file_data,
                    author=author,
                    sha=sha,
                )
                logger.info(f"File {github_file_path} updated with message: '{commit_message}'")
            else:
                # Create the file if it doesn't exist
                self.repository.create_file(
                    path=github_file_path,
                    message=commit_message,
                    content=local_file_data,
                    author=author,
                )
                logger.info(f"File {github_file_path} created with message: '{commit_message}'")

        except Exception as e:
            logger.error(f"An exception occurred during GitHub commit: {e}")
            raise

    @retry_on_exception(max_retries=5)
    def cleanup_duplicate_issues(self) -> None:
        """Find and clean up duplicate issues in the repository.
        Keeps the issue with the lowest number and deletes all other duplicates.
        Also finds and deletes PRs associated with the deleted issues.

        The process:
        1. Get all issues and filter out PRs
        2. Group remaining true issues by title (excluding CXTM failure issues)
        3. For each group with duplicates:
           - Keep the lowest numbered issue
           - Find and close PRs associated with higher numbered duplicates
           - Close the duplicate issues

        Note: Issues with titles starting with "Failed CXTM test case" are preserved
        and never considered for duplicate cleanup.
        """
        try:
            # Get all issues and filter out PRs
            all_items = list(self.repository.get_issues(state="all"))
            true_issues = [
                issue
                for issue in all_items
                if isinstance(issue._pull_request, type(GithubObject.NotSet)) and not issue.title.startswith("Failed CXTM test case")
            ]

            logger.info(f"Found {len(all_items)} total items, {len(true_issues)} are true issues (excluding CXTM failures)")

            # Group issues by title
            issues_by_title = {}
            for issue in true_issues:
                if issue.title not in issues_by_title:
                    issues_by_title[issue.title] = []
                issues_by_title[issue.title].append(issue)

            # Find and clean up duplicates
            logger.info("Checking for duplicate issues...")
            for title, issues in issues_by_title.items():
                if len(issues) > 1:
                    # Sort by issue number to keep the lowest
                    issues.sort(key=lambda x: x.number)
                    kept_issue = issues[0]
                    duplicates = issues[1:]

                    logger.info(f"Found duplicate issues for title: {title}")
                    duplicate_numbers = [d.number for d in duplicates]
                    logger.info(f"Keeping issue #{kept_issue.number} (duplicates found: #{', #'.join(map(str, duplicate_numbers))})")

                    for duplicate in duplicates:
                        try:
                            # Find PRs referencing this specific duplicate issue
                            pattern = f"#{duplicate.number}"
                            kept_pattern = f"#{kept_issue.number}"
                            prs = self.repository.get_pulls(state="all")

                            for pr in prs:
                                pr_body = pr.body or ""

                                # Only close PR if it references the duplicate issue and NOT the kept issue
                                if pattern in pr_body and kept_pattern not in pr_body:
                                    # Double check comments as well
                                    should_close = True
                                    for comment in pr.get_issue_comments():
                                        if kept_pattern in comment.body:
                                            should_close = False
                                            logger.info(f"Keeping PR #{pr.number} open as it references kept issue #{kept_issue.number}")
                                            break

                                    if should_close:
                                        if pr.state == "closed":
                                            logger.info(
                                                f"Skipping PR #{pr.number} as it is already closed (was associated with duplicate issue #{duplicate.number})"
                                            )
                                        else:
                                            logger.info(
                                                f"Closing PR #{pr.number} associated with duplicate issue #{duplicate.number} (original: #{kept_issue.number})"
                                            )
                                            pr.create_issue_comment(
                                                f"Closing this PR as it references issue #{duplicate.number} which was identified as a duplicate of #{kept_issue.number}."
                                            )
                                            pr.edit(state="closed")

                            # Only attempt to close the duplicate issue if it's still open
                            if duplicate.state == "closed":
                                logger.info(f"Skipping issue #{duplicate.number} as it is already closed (duplicate of #{kept_issue.number})")
                            else:
                                logger.info(f"Closing duplicate issue #{duplicate.number} (keeping original: #{kept_issue.number})")
                                duplicate.create_comment(f"Closing this issue as it is a duplicate of #{kept_issue.number}.")
                                duplicate.edit(state="closed")

                        except Exception as e:
                            logger.error(f"Error cleaning up issue #{duplicate.number}: {str(e)}")
                            continue

        except Exception as e:
            logger.error(f"Error during duplicate issue cleanup: {str(e)}")
