"""Release notes generation module."""

from .detector import VersionDetector
from .extractor import DataExtractor
from .generator import ReleaseNotesGenerator
from .markdown import MarkdownWriter
from .models import (
    ContentGenerator,
    PRWithCommits,
    ReleaseNotesFileConfig,
    ReleaseNotesResult,
    ReleaseNotesStatus,
)

__all__ = [
    "ReleaseNotesStatus",
    "ReleaseNotesFileConfig",
    "PRWithCommits",
    "ReleaseNotesResult",
    "ContentGenerator",
    "VersionDetector",
    "DataExtractor",
    "MarkdownWriter",
    "ReleaseNotesGenerator",
]
