"""Contains utilities for rendering Jinja2 templates."""

from pathlib import Path

import jinja2
import structlog

from github_ops_manager.utils.exceptions import FileNotFoundError

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def construct_jinja2_environment() -> jinja2.Environment:
    """Construct a Jinja2 environment."""
    jinja_env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    return jinja_env


async def construct_jinja2_template(template_path: Path | str, environment: jinja2.Environment | None = None) -> jinja2.Template:
    """Construct a Jinja2 template from a file."""
    if environment is None:
        environment = await construct_jinja2_environment()
    try:
        with open(template_path, encoding="utf-8") as f:
            template_content = f.read()
    except FileNotFoundError:
        logger.error("Jinja2 template not found", template_path=template_path)
        raise
    return environment.from_string(template_content)
