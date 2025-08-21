"""Contains utilities for rendering Jinja2 templates."""

from pathlib import Path

import jinja2
import structlog
from pydantic import BaseModel

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def construct_jinja2_environment() -> jinja2.Environment:
    """Construct a Jinja2 environment."""
    jinja_env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    return jinja_env


def construct_jinja2_template_from_string(template_string: str, environment: jinja2.Environment | None = None) -> jinja2.Template:
    """Construct a Jinja2 template from a string."""
    if environment is None:
        environment = construct_jinja2_environment()
    return environment.from_string(template_string)


def construct_jinja2_template_from_file(template_path: Path | str, environment: jinja2.Environment | None = None) -> jinja2.Template:
    """Construct a Jinja2 template from a file."""
    if environment is None:
        environment = construct_jinja2_environment()
    try:
        with open(template_path, encoding="utf-8") as f:
            template_content = f.read()
    except FileNotFoundError:
        logger.error("Jinja2 template not found", template_path=template_path)
        raise
    return environment.from_string(template_content)


def render_template_with_model(model: BaseModel, template: jinja2.Template) -> str:
    """Render a Jinja2 template against a Pydantic model."""
    try:
        rendered_template = template.render(model.model_dump())
    except jinja2.UndefinedError as exc:
        logger.error("Failed to render template with model", model_type=type(model).__name__, model=model, error=str(exc))
        raise
    return rendered_template
