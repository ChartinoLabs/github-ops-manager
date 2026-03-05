"""Retry decorator for handling GitHub API rate limits and transient errors.

This module provides a decorator that implements intelligent retry logic for GitHub API calls,
including respect for rate limit headers and exponential backoff.
"""

import asyncio
import functools
import time
from typing import Any, Callable, TypeVar

import structlog
from githubkit.exception import PrimaryRateLimitExceeded, RequestFailed, SecondaryRateLimitExceeded

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry_on_rate_limit(
    max_retries: int = 100,
    initial_delay: float = 10.0,
    max_delay: float = 300.0,
    exponential_base: float = 2.0,
) -> Callable[[F], F]:
    """Decorator for retrying async functions when they encounter GitHub rate limits.

    This decorator handles:
    - GitHub rate limit errors (403/429)
    - Secondary rate limits
    - Respects retry-after and x-ratelimit-reset headers
    - Implements exponential backoff for other transient errors

    Args:
        max_retries: Maximum number of retry attempts (default: 100)
        initial_delay: Initial delay in seconds between retries (default: 10.0)
        max_delay: Maximum delay in seconds between retries (default: 300.0)
        exponential_base: Base for exponential backoff calculation (default: 2.0)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_on_rate_limit()
        async def get_user_data(username: str):
            return await github_client.get_user(username)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (PrimaryRateLimitExceeded, SecondaryRateLimitExceeded) as e:
                    # These exceptions already have retry_after as a timedelta
                    last_exception = e

                    if attempt == max_retries:
                        # Max retries reached
                        logger.error(
                            "Max retries reached for GitHub rate limit error",
                            function=func.__name__,
                            attempt=attempt + 1,
                            error_type=type(e).__name__,
                            retry_after=str(e.retry_after) if hasattr(e, "retry_after") else "unknown",
                        )
                        raise

                    # Extract wait time from the exception's retry_after timedelta
                    if hasattr(e, "retry_after") and e.retry_after:
                        wait_time = min(e.retry_after.total_seconds(), max_delay)
                    else:
                        # Fallback to exponential backoff if no retry_after
                        wait_time = min(delay, max_delay)

                    logger.warning(
                        f"GitHub rate limit exceeded, waiting {wait_time} seconds",
                        function=func.__name__,
                        rate_limit_type="primary" if isinstance(e, PrimaryRateLimitExceeded) else "secondary",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_time=wait_time,
                    )

                    await asyncio.sleep(wait_time)

                    # Exponential backoff for next attempt
                    delay = min(delay * exponential_base, max_delay)

                except RequestFailed as e:
                    last_exception = e

                    # Check if this is a rate limit error
                    is_rate_limit = e.response.status_code in (403, 429)
                    is_secondary_rate_limit = e.response.status_code == 403 and "rate limit" in str(e).lower()

                    if not (is_rate_limit or is_secondary_rate_limit):
                        # Not a rate limit error, don't retry
                        raise

                    if attempt == max_retries:
                        # Max retries reached
                        logger.error(
                            "Max retries reached for rate limit error",
                            function=func.__name__,
                            attempt=attempt + 1,
                            status_code=e.response.status_code,
                            error=str(e),
                        )
                        raise

                    # Calculate wait time
                    wait_time = delay

                    # Check for retry-after header
                    retry_after = e.response.headers.get("retry-after")
                    if retry_after:
                        try:
                            wait_time = float(retry_after)
                            logger.info(
                                "Using retry-after header value",
                                retry_after=wait_time,
                                function=func.__name__,
                            )
                        except ValueError:
                            logger.warning(
                                "Invalid retry-after header value",
                                retry_after=retry_after,
                                function=func.__name__,
                            )
                    else:
                        # Check for x-ratelimit-reset header
                        rate_limit_reset = e.response.headers.get("x-ratelimit-reset")
                        if rate_limit_reset:
                            try:
                                reset_timestamp = int(rate_limit_reset)
                                current_timestamp = int(time.time())
                                if reset_timestamp > current_timestamp:
                                    wait_time = reset_timestamp - current_timestamp + 1
                                    logger.info(
                                        "Using x-ratelimit-reset header",
                                        wait_time=wait_time,
                                        function=func.__name__,
                                    )
                            except ValueError:
                                logger.warning(
                                    "Invalid x-ratelimit-reset header value",
                                    rate_limit_reset=rate_limit_reset,
                                    function=func.__name__,
                                )

                    # Apply max delay cap
                    wait_time = min(wait_time, max_delay)

                    logger.warning(
                        f"Rate limit hit, retrying in {wait_time} seconds",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_time=wait_time,
                        status_code=e.response.status_code,
                    )

                    await asyncio.sleep(wait_time)

                    # Exponential backoff for next attempt
                    delay = min(delay * exponential_base, max_delay)

                except Exception as e:
                    # For non-RequestFailed exceptions, don't retry
                    logger.error(
                        "Unexpected error in rate limit retry decorator",
                        function=func.__name__,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    raise

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Sync version of the retry wrapper - raises error since we only support async."""
            raise RuntimeError(
                f"Function {func.__name__} decorated with @retry_on_rate_limit must be async. This decorator only supports async functions."
            )

        # Return the appropriate wrapper based on whether the function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore

    return decorator
