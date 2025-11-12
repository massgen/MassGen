# -*- coding: utf-8 -*-
"""
Rate limit configuration module for MassGen.

Contains configuration loaders and utilities for rate limiting settings
across different AI providers (Gemini, OpenAI, Claude, etc.).
"""

from .rate_limit_config import RateLimitConfig, get_rate_limit_config

__all__ = ["RateLimitConfig", "get_rate_limit_config"]
