"""Version detection and comparison for release notes."""

import re
from typing import List, Tuple
import structlog
from packaging import version


logger = structlog.get_logger(__name__)


class VersionDetector:
    """Detects and compares versions in release notes."""
    
    def __init__(self, version_pattern: str):
        """Initialize with version pattern."""
        self.pattern = re.compile(version_pattern, re.MULTILINE | re.IGNORECASE)
        
    def extract_versions(self, content: str) -> List[str]:
        """Extract all version numbers from content."""
        versions = self.pattern.findall(content)
        logger.debug("Extracted versions", versions=versions)
        return versions
        
    def get_latest_version(self, content: str) -> str | None:
        """Get the most recent version from content."""
        versions = self.extract_versions(content)
        if not versions:
            return None
            
        sorted_versions = sorted(versions, key=version.parse, reverse=True)
        return sorted_versions[0]
        
    def is_version_documented(self, content: str, version: str) -> bool:
        """Check if a version is already documented."""
        # Case insensitive check in full content
        if f"v{version}".lower() in content.lower():
            return True
            
        # Check parsed versions
        documented_versions = self.extract_versions(content)
        return version in documented_versions
        
    def find_undocumented_releases(
        self, 
        all_releases: List[str], 
        documented_content: str
    ) -> List[str]:
        """Find all releases that are not yet documented.
        
        Args:
            all_releases: List of all release versions (without 'v' prefix)
            documented_content: Current release notes content
            
        Returns:
            List of undocumented versions, sorted oldest first
        """
        documented = set(self.extract_versions(documented_content))
        undocumented = []
        
        for release in all_releases:
            if release not in documented and not self.is_version_documented(documented_content, release):
                undocumented.append(release)
                
        # Sort oldest first so we document in chronological order
        return sorted(undocumented, key=version.parse) 