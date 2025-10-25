# -*- coding: utf-8 -*-
"""
Rate limiter for API requests to respect provider rate limits.

Provides a simple async rate limiter that ensures no more than N requests
are made within a given time window.
"""

import asyncio
import time
from collections import deque
from typing import Optional


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
                    from .logger_config import logger
                    logger.info(
                        f"[RateLimiter] Rate limit reached ({len(self.request_times)}/{self.max_requests} "
                        f"requests in {self.time_window}s window). Waiting {wait_time:.2f}s..."
                    )
                    await asyncio.sleep(wait_time)
                    
                    # After waiting, remove the oldest request
                    current_time = time.time()
                    while self.request_times and self.request_times[0] <= current_time - self.time_window:
                        self.request_times.popleft()
            
            # Record this request
            self.request_times.append(time.time())


class GlobalRateLimiter:
    """
    Global rate limiter registry for managing rate limits across different providers.
    
    Allows sharing a single rate limiter instance across multiple backend instances
    for the same provider.
    """
    
    _limiters: dict = {}
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
    def clear_limiters(cls):
        """Clear all rate limiters (useful for testing)."""
        cls._limiters.clear()
