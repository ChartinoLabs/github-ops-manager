"""Module-level singleton for application configuration.

After reconciliation, set `config` to the resolved configuration instance.
Other modules can import and use this reference.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from github_ops_manager.configuration.models import (
        BaseConfig,
        ExportIssuesConfig,
        ProcessIssuesConfig,
    )

    ConfigType = BaseConfig | ProcessIssuesConfig | ExportIssuesConfig
else:
    ConfigType = object


# Ignore type checking below because for the overwhelming majority of the time
# except at the very beginning of the program, the config will not be None.
config: ConfigType = None  # type: ignore


async def set_configuration(desired_config: ConfigType) -> None:
    """Set the configuration for the application."""
    global config
    config = desired_config
