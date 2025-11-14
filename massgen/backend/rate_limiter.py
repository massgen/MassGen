# -*- coding: utf-8 -*-
"""
Rate limiter for API requests to respect provider rate limits.

Provides a simple async rate limiter that ensures no more than N requests
are made within a given time window.
"""

import asyncio
import time
from collections import deque
from typing import Any, Dict, Optional

from ..logger_config import logger


class RateLimiter:
    """
    Async rate limiter using a sliding window approach.

    Ensures that no more than `max_requests` requests are made
    within any `time_window` second period.

    Example:
        # Allow 7 requests per minute (60 seconds)
        limiter = RateLimiter(max_requests=7, time_window=60)

        async def make_request():
            async with limiter:
                # Make your API call here
                response = await api_call()
            return response
    """

    def __init__(self, max_requests: int, time_window: float):
        """
        Initialize the rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in the time window
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.request_times: deque = deque()
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        """Context manager entry - waits until request is allowed."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        return False

    async def acquire(self):
        """
        Wait until a request slot is available within the rate limit.

        This method blocks until it's safe to make a request without
        exceeding the rate limit.
        """
        async with self._lock:
            current_time = time.time()

            # Remove timestamps outside the current window
            while self.request_times and self.request_times[0] <= current_time - self.time_window:
                self.request_times.popleft()

            # If we've hit the limit, wait until the oldest request falls outside the window
            if len(self.request_times) >= self.max_requests:
                oldest_time = self.request_times[0]
                wait_time = (oldest_time + self.time_window) - current_time

                if wait_time > 0:
                    # Log waiting information
                    logger.info(
                        f"[RateLimiter] Rate limit reached ({len(self.request_times)}/{self.max_requests} " f"requests in {self.time_window}s window). Waiting {wait_time:.2f}s...",
                    )
                    await asyncio.sleep(wait_time)

                    # After waiting, remove the oldest request
                    current_time = time.time()
                    while self.request_times and self.request_times[0] <= current_time - self.time_window:
                        self.request_times.popleft()

            # Record this request
            self.request_times.append(time.time())


class MultiRateLimiter:
    """
    Multi-dimensional rate limiter that enforces multiple concurrent limits.

    Supports:
    - RPM (Requests Per Minute)
    - TPM (Tokens Per Minute)
    - RPD (Requests Per Day)

    All limits are enforced concurrently using sliding windows.

    Example:
        limiter = MultiRateLimiter(
            rpm=10,      # 10 requests per minute
            tpm=100000,  # 100K tokens per minute
            rpd=500      # 500 requests per day
        )

        async def make_request():
            async with limiter:
                # Before making request
                response = await api_call()
                # After request, record tokens used
                await limiter.record_tokens(response.usage.total_tokens)
            return response
    """

    def __init__(
        self,
        rpm: Optional[int] = None,
        tpm: Optional[int] = None,
        rpd: Optional[int] = None,
    ):
        """
        Initialize multi-dimensional rate limiter.

        Args:
            rpm: Requests Per Minute limit (None = no limit)
            tpm: Tokens Per Minute limit (None = no limit)
            rpd: Requests Per Day limit (None = no limit)
        """
        self.rpm = rpm
        self.tpm = tpm
        self.rpd = rpd

        # Sliding window trackers
        self.request_times_minute: deque = deque()  # For RPM
        self.request_times_day: deque = deque()  # For RPD
        self.token_usage: deque = deque()  # For TPM: (timestamp, tokens)

        # Lazy initialization of lock to ensure it's created in the correct event loop
        self._lock: Optional[asyncio.Lock] = None

    async def __aenter__(self):
        """Context manager entry - waits until request is allowed."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        return False

    def _get_lock(self) -> asyncio.Lock:
        """
        Lazily initialize and return the asyncio lock.

        This ensures the lock is created in the correct event loop context.
        """
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self):
        """
        Wait until a request is allowed under all rate limits.

        Checks RPM, TPM, and RPD limits and waits for the most restrictive one.
        """
        async with self._get_lock():
            max_wait_time = 0.0
            wait_reasons = []

            current_time = time.time()

            # Check RPM (60 second window)
            if self.rpm is not None:
                while self.request_times_minute and self.request_times_minute[0] <= current_time - 60:
                    self.request_times_minute.popleft()

                if len(self.request_times_minute) >= self.rpm:
                    oldest_time = self.request_times_minute[0]
                    wait_time = (oldest_time + 60) - current_time
                    if wait_time > max_wait_time:
                        max_wait_time = wait_time
                        wait_reasons.append(
                            f"RPM limit ({len(self.request_times_minute)}/{self.rpm})",
                        )

            # Check RPD (86400 second window = 24 hours)
            if self.rpd is not None:
                while self.request_times_day and self.request_times_day[0] <= current_time - 86400:
                    self.request_times_day.popleft()

                if len(self.request_times_day) >= self.rpd:
                    oldest_time = self.request_times_day[0]
                    wait_time = (oldest_time + 86400) - current_time
                    if wait_time > max_wait_time:
                        max_wait_time = wait_time
                        wait_reasons.append(
                            f"RPD limit ({len(self.request_times_day)}/{self.rpd})",
                        )

            # Check TPM (60 second window)
            if self.tpm is not None:
                # Remove old token usage records
                while self.token_usage and self.token_usage[0][0] <= current_time - 60:
                    self.token_usage.popleft()

                # Calculate current token usage in the window
                current_tokens = sum(tokens for _, tokens in self.token_usage)

                if current_tokens >= self.tpm:
                    # Find when the oldest tokens will expire
                    if self.token_usage:
                        oldest_time = self.token_usage[0][0]
                        wait_time = (oldest_time + 60) - current_time
                        if wait_time > max_wait_time:
                            max_wait_time = wait_time
                            wait_reasons.append(
                                f"TPM limit ({current_tokens}/{self.tpm} tokens)",
                            )

            # If we need to wait, do it
            if max_wait_time > 0:
                reason_str = " and ".join(wait_reasons)
                logger.info(
                    f"[MultiRateLimiter] Rate limit reached: {reason_str}. " f"Waiting {max_wait_time:.2f}s...",
                )
                await asyncio.sleep(max_wait_time)

                # After waiting, clean up old records
                current_time = time.time()
                while self.request_times_minute and self.request_times_minute[0] <= current_time - 60:
                    self.request_times_minute.popleft()
                while self.request_times_day and self.request_times_day[0] <= current_time - 86400:
                    self.request_times_day.popleft()
                while self.token_usage and self.token_usage[0][0] <= current_time - 60:
                    self.token_usage.popleft()

            # Record this request
            current_time = time.time()
            if self.rpm is not None:
                self.request_times_minute.append(current_time)
            if self.rpd is not None:
                self.request_times_day.append(current_time)

    async def record_tokens(self, tokens: int):
        """
        Record token usage for TPM tracking.

        Call this after receiving a response to track tokens used.

        Args:
            tokens: Number of tokens used in the request
        """
        if self.tpm is not None:
            async with self._get_lock():
                self.token_usage.append((time.time(), tokens))


class GlobalRateLimiter:
    """
    Global rate limiter registry for managing rate limits across different providers.

    Allows sharing a single rate limiter instance across multiple backend instances
    for the same provider.
    """

    _limiters: Dict[str, Any] = {}
    _lock = asyncio.Lock()

    @classmethod
    def get_limiter_sync(cls, provider: str, max_requests: int, time_window: float) -> RateLimiter:
        """
        Synchronous version - get or create a rate limiter for a specific provider.
        Use this in __init__ methods.

        Args:
            provider: Provider name (e.g., "gemini")
            max_requests: Maximum requests per time window
            time_window: Time window in seconds

        Returns:
            RateLimiter instance for the provider
        """
        if provider not in cls._limiters:
            cls._limiters[provider] = RateLimiter(max_requests, time_window)
        return cls._limiters[provider]

    @classmethod
    def get_multi_limiter_sync(
        cls,
        provider: str,
        rpm: Optional[int] = None,
        tpm: Optional[int] = None,
        rpd: Optional[int] = None,
    ) -> MultiRateLimiter:
        """
        Get or create a multi-dimensional rate limiter for a specific provider.
        Use this in __init__ methods.

        Args:
            provider: Provider name (e.g., "gemini-2.5-flash")
            rpm: Requests Per Minute limit
            tpm: Tokens Per Minute limit
            rpd: Requests Per Day limit

        Returns:
            MultiRateLimiter instance for the provider
        """
        if provider not in cls._limiters:
            cls._limiters[provider] = MultiRateLimiter(rpm=rpm, tpm=tpm, rpd=rpd)
        return cls._limiters[provider]

    @classmethod
    def clear_limiters(cls):
        """Clear all rate limiters (useful for testing)."""
        cls._limiters.clear()
