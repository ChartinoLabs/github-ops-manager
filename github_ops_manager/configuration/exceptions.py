"""Contains exceptions raised when reconciling application configuration."""


class GitHubAuthenticationConfigurationUndefinedError(Exception):
    """Raised when the GitHub authentication configuration is undefined."""

    pass


class RequiredConfigurationElementError(Exception):
    """Raised when a required configuration element is missing."""

    def __init__(self, name: str, cli_name: str, env_name: str) -> None:
        """Initializes the exception with the name of the missing element."""
        super().__init__(f"Missing required configuration element: {name}")
        self.name = name
        self.cli_name = cli_name
        self.env_name = env_name
