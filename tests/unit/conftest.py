"""Fixtures for unit tests."""

from typing import Generator

import pytest
import structlog


@pytest.fixture(autouse=True)
def configure_structlog_for_caplog() -> Generator[None, None, None]:
    """Configure structlog for use with caplog."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    yield
    structlog.reset_defaults()
