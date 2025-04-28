"""House GitHub synchronization utilities."""

import os
from uuid import uuid4

from core.github_helper import RepoHandler
from core.shared_utils import logger, ordered_dump
from ruamel.yaml import YAML


def synchronize_yaml_issues(yaml_file: str, repo_handler: RepoHandler) -> dict:
    """Synchronizes issues from a YAML file with GitHub.

    This function:
    1. Fetches the YAML file from GitHub
    2. Creates a temporary local copy
    3. Updates labels and creates/updates GitHub issues
    4. Commits changes back to GitHub

    The issue descriptions are rendered live when creating/updating GitHub issues,
    rather than being stored in the YAML file.

    Parameters:
    -----------
    yaml_file : str
        Name of the YAML file to synchronize
    repo_handler : RepoHandler
        Instance of RepoHandler for GitHub operations

    Returns:
    --------
    dict
        Status message and count of synchronized issues
    """
    # Fetch contents of YAML file from GitHub repository
    issues_content = repo_handler.get_file_contents(yaml_file)

    if issues_content is None:
        return {"message": f"No issues found in {yaml_file}", "synchronized_count": 0}

    # Create temporary file with unique name
    temp_issues_uuid = uuid4()
    temp_issues_path = f"tmp/issues_{temp_issues_uuid}.yaml"
    os.makedirs("tmp", exist_ok=True)

    try:
        # Write content to temporary file
        with open(temp_issues_path, "wb") as temp_file:
            temp_file.write(issues_content.encode("utf-8"))

        # Load and process issues
        yaml = YAML()
        with open(temp_issues_path) as infile:
            local_issue_metadata = yaml.load(infile)

        issues_count = len(local_issue_metadata["issues"])

        # Remove description key if present (for backward compatibility)
        for local_issue in local_issue_metadata["issues"]:
            if "description" in local_issue:
                del local_issue["description"]

        # Write updates back to temp file
        with open(temp_issues_path, "w") as outfile:
            ordered_dump(local_issue_metadata, outfile)

        # Create/update GitHub issues (descriptions will be rendered live)
        repo_handler.create_issues(temp_issues_path)

        # Create any missing labels
        repo_handler.create_labels()

        # Commit changes back to GitHub
        repo_handler.commit_file_to_github(
            yaml_file,
            f"GenAI: Synchronized {issues_count} issues and labels",
            temp_issues_path,
        )

        return {
            "message": f"Successfully synchronized {issues_count} issues in {yaml_file}",
            "synchronized_count": issues_count,
        }

    except Exception as e:
        logger.error(f"Error synchronizing {yaml_file}: {e}")
        return {
            "message": f"Error synchronizing {yaml_file}: {str(e)}",
            "synchronized_count": 0,
        }
    finally:
        # Clean up temporary file
        if os.path.exists(temp_issues_path):
            os.remove(temp_issues_path)
