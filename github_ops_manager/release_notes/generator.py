"""Main release notes generation orchestration."""

import uuid

import structlog

from ..configuration.models import GitHubAuthenticationType
from ..github.adapter import GitHubKitAdapter
from ..utils.constants import (
    DEFAULT_RELEASE_NOTES_HEADER,
    VERSION_HEADER_PATTERN,
)
from .detector import VersionDetector
from .extractor import DataExtractor
from .markdown import MarkdownWriter
from .models import (
    ContentGenerator,
    ReleaseNotesFileConfig,
    ReleaseNotesResult,
    ReleaseNotesStatus,
)

logger = structlog.get_logger(__name__)


class ReleaseNotesGenerator:
    """Orchestrates release notes generation with pluggable content generation.

    This class handles all GitHub operations and provides a clean interface
    for content generation. The actual content generation is delegated to
    a ContentGenerator implementation.

    IMPORTANT: This generator can handle multiple undocumented releases.
    If releases v1.1.2 and v1.1.3 exist but only v1.1.1 is documented,
    it will generate notes for both missing versions.
    """

    def __init__(
        self,
        repo: str,
        github_token: str,
        github_api_url: str,
        file_config: ReleaseNotesFileConfig,
        content_generator: ContentGenerator,
    ) -> None:
        """Initialize with GitHub configuration and content generator.

        Args:
            repo: Repository in 'owner/repo' format
            github_token: GitHub personal access token
            github_api_url: GitHub API URL (e.g., https://api.github.com)
            file_config: Configuration for release notes file handling
            content_generator: Implementation of ContentGenerator protocol
        """
        self.repo = repo
        self.github_token = github_token
        self.github_api_url = github_api_url
        self.file_config = file_config
        self.content_generator = content_generator
        self.adapter: GitHubKitAdapter | None = None

    async def initialize(self) -> None:
        """Initialize GitHub adapter."""
        self.adapter = await GitHubKitAdapter.create(
            repo=self.repo,
            github_auth_type=GitHubAuthenticationType.PAT,
            github_pat_token=self.github_token,
            github_api_url=self.github_api_url,
        )
        logger.info("GitHub adapter initialized", repo=self.repo)

    async def generate(self, dry_run: bool = False) -> ReleaseNotesResult:
        """Generate release notes.

        Args:
            dry_run: If True, generate content but don't create PR

        Returns:
            Result of the generation process
        """
        try:
            if not self.adapter:
                await self.initialize()

            # Initialize components
            detector = VersionDetector(VERSION_HEADER_PATTERN)
            extractor = DataExtractor(self.adapter)
            writer = MarkdownWriter(DEFAULT_RELEASE_NOTES_HEADER)

            # Get all releases
            all_releases = await self.adapter.list_releases()
            logger.debug(f"Total releases from API: {len(all_releases)}")

            # Filter out drafts and prereleases
            filtered_releases = [r for r in all_releases if not r.draft and not r.prerelease]
            logger.debug(f"Releases after filtering (no drafts/prereleases): {len(filtered_releases)}")

            release_versions = [r.tag_name.lstrip("v") for r in filtered_releases]
            logger.debug(f"Release versions for processing: {release_versions}")

            # Get current content from default branch
            repo_info = await self.adapter.get_repository()
            current_content = await self.adapter.get_file_content_from_pull_request(self.file_config.file_path, repo_info.default_branch)

            # Find undocumented releases
            undocumented = detector.find_undocumented_releases(release_versions, current_content)

            if not undocumented:
                logger.info("All releases are already documented")
                return ReleaseNotesResult(status=ReleaseNotesStatus.UP_TO_DATE, version=release_versions[0] if release_versions else None)

            logger.info("Found undocumented releases", versions=undocumented)

            # Process each undocumented release (oldest first)
            all_generated_content = []
            for version in undocumented:
                logger.info("Processing release", version=version)

                # Extract data for this specific release
                release_data = await extractor.extract_release_data(specific_release=version)

                # Extract PR and commit data
                pr_data, standalone_commits = await extractor.extract_pr_and_commit_data(release_data.body)

                # Check if we found any content
                if not pr_data and not standalone_commits:
                    logger.warning("No PRs or commits found in release", version=version)
                    # Continue with other releases instead of failing
                    continue

                # Log what we found
                if pr_data:
                    logger.info(f"Found {len(pr_data)} PRs in release")
                if standalone_commits:
                    logger.info(f"Found {len(standalone_commits)} standalone commits in release")

                # Generate content using pluggable generator
                logger.info("Generating content", version=version, generator=type(self.content_generator).__name__)
                generated_content = await self.content_generator.generate(
                    version=version, prs=pr_data, commits=standalone_commits, release=release_data
                )

                all_generated_content.append((version, generated_content))

                # Update current_content for next iteration
                current_content = writer.insert_release_notes(current_content, generated_content, version)

            if not all_generated_content:
                return ReleaseNotesResult(status=ReleaseNotesStatus.NO_CONTENT, error="No PRs or commits found in any undocumented releases")

            if dry_run:
                logger.info("Dry run mode - not creating PR")
                # Combine all generated content for preview
                combined_content = "\n\n".join([content for _, content in all_generated_content])

                logger.debug("=" * 80)
                logger.debug("DRY RUN - FINAL RELEASE NOTES FILE WOULD CONTAIN:\n")
                logger.debug(current_content)
                logger.debug("=" * 80)

                return ReleaseNotesResult(
                    status=ReleaseNotesStatus.DRY_RUN,
                    version=", ".join([v for v, _ in all_generated_content]),
                    generated_content=combined_content,
                )

            # Create PR with all updates
            versions_str = ", ".join([v for v, _ in all_generated_content])

            # Get default branch (already fetched above)
            default_branch = repo_info.default_branch

            # Create unique branch
            unique_id = str(uuid.uuid4())[:8]
            branch_name = f"docs/automation/release-notes-v{versions_str.replace(', ', '-')}-{unique_id}"

            logger.info("Creating branch", branch=branch_name)
            await self.adapter.create_branch(branch_name, default_branch)

            # Commit changes
            commit_message = f"docs: Update release notes for v{versions_str}"
            await self.adapter.commit_files_to_branch(branch_name, [(self.file_config.file_path, current_content)], commit_message)

            # Create PR
            pr_title = f"docs: Update release notes for v{versions_str}"
            pr_body = (
                f"This PR updates the release notes for version(s) {versions_str}.\n\n"
                f"Generated automatically by release notes automation.\n\n"
                f"Please review the generated content for accuracy before merging."
            )

            pr = await self.adapter.create_pull_request(
                title=pr_title,
                head=branch_name,
                base=default_branch,
                body=pr_body,
            )

            logger.info("Created release notes PR", pr_number=pr.number, pr_url=pr.html_url)

            return ReleaseNotesResult(
                status=ReleaseNotesStatus.SUCCESS,
                pr_url=pr.html_url,
                version=versions_str,
            )

        except Exception as e:
            logger.exception("Failed to generate release notes")
            return ReleaseNotesResult(
                status=ReleaseNotesStatus.ERROR,
                error=str(e),
            )
