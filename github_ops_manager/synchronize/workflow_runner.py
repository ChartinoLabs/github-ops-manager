# This file is intended to orchestrate the main actions (e.g., sync-to-github, export-issues).

"""Orchestrates the main workflows (e.g., sync-to-github, export-issues)."""

import structlog
from structlog.stdlib import BoundLogger

logger: BoundLogger = structlog.get_logger(__name__)  # type: ignore
