"""Unit tests for the configuration.reconcile module."""

import pytest

from github_ops_manager.configuration.exceptions import (
    GitHubAuthenticationConfigurationUndefinedError,
)
from github_ops_manager.configuration.reconcile import validate_github_authentication_configuration
