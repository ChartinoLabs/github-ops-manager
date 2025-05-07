"""Pytest configuration for integration tests."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv


@pytest.fixture(autouse=True, scope="session")
def load_env() -> None:
    """Load environment variables from .env file before running integration tests.

    This fixture is automatically used for all tests in this directory and its subdirectories.
    It loads environment variables from:
    1. .env.integration (if it exists)
    2. .env (if it exists)

    The .env.integration file takes precedence over .env.
    """
    # Get the project root directory (3 levels up from this file)
    project_root = Path(__file__).parent.parent.parent

    # Try to load .env.integration first
    integration_env = project_root / ".env.integration"
    if integration_env.exists():
        load_dotenv(dotenv_path=integration_env)

    # Then try to load .env as fallback
    default_env = project_root / ".env"
    if default_env.exists():
        load_dotenv(dotenv_path=default_env)

    # Verify required environment variables are set
    required_vars = ["REPO"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}. Please ensure they are set in either .env.integration or .env"
        )
