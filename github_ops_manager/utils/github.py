"""Contains utility functions for GitHub interactions."""


async def split_repository_in_configuration(repo: str | None) -> tuple[str, str]:
    """Splits the repository in the configuration into owner and repository."""
    if repo is None:
        raise ValueError("GitHub App authentication requires repo in config.")
    repo = repo.strip("/")
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("Repository must be in the format 'owner/repo' with no leading/trailing slashes or extra parts.")
    owner, repository = parts
    return owner, repository
