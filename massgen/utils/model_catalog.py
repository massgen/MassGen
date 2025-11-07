# -*- coding: utf-8 -*-
"""
Dynamic model catalog fetcher for chat completion providers.
Fetches model lists from provider APIs with caching.

Based on research of official provider APIs.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import httpx

# Cache directory
CACHE_DIR = Path.home() / ".massgen" / "model_cache"
CACHE_DURATION = timedelta(hours=24)  # Cache for 24 hours


def ensure_cache_dir():
    """Ensure cache directory exists."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_path(provider: str) -> Path:
    """Get cache file path for a provider."""
    return CACHE_DIR / f"{provider}_models.json"


def is_cache_valid(cache_path: Path) -> bool:
    """Check if cache file exists and is still valid."""
    if not cache_path.exists():
        return False

    try:
        with open(cache_path) as f:
            data = json.load(f)
            cached_at = datetime.fromisoformat(data.get("cached_at", ""))
            return datetime.now() - cached_at < CACHE_DURATION
    except (json.JSONDecodeError, ValueError, KeyError):
        return False


def read_cache(cache_path: Path) -> Optional[List[str]]:
    """Read model list from cache."""
    try:
        with open(cache_path) as f:
            data = json.load(f)
            return data.get("models", [])
    except (json.JSONDecodeError, FileNotFoundError):
        return None


def write_cache(cache_path: Path, models: List[str]):
    """Write model list to cache."""
    ensure_cache_dir()
    data = {"models": models, "cached_at": datetime.now().isoformat()}
    with open(cache_path, "w") as f:
        json.dump(data, f, indent=2)


async def fetch_openrouter_models(api_key: Optional[str] = None) -> List[str]:
    """Fetch model list from OpenRouter API.

    OpenRouter's /models endpoint works without authentication.

    Args:
        api_key: OpenRouter API key (optional, not required for listing models)

    Returns:
        List of model IDs
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # OpenRouter allows listing models without auth
            headers = {}
            if api_key or os.getenv("OPENROUTER_API_KEY"):
                headers["Authorization"] = f"Bearer {api_key or os.getenv('OPENROUTER_API_KEY')}"

            response = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
            response.raise_for_status()
            data = response.json()
            return [model["id"] for model in data.get("data", [])]
    except (httpx.HTTPError, KeyError, ValueError):
        return []


async def fetch_poe_models() -> List[str]:
    """Fetch model list from POE API.

    Returns:
        List of model IDs
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://api.poe.com/v1/models")
            response.raise_for_status()
            data = response.json()
            return [model["id"] for model in data.get("data", [])]
    except (httpx.HTTPError, KeyError, ValueError):
        return []


async def fetch_openai_compatible_models(base_url: str, api_key: Optional[str] = None) -> List[str]:
    """Fetch model list from OpenAI-compatible API endpoint.

    Args:
        base_url: Base URL of the API (e.g., "https://api.groq.com/openai/v1")
        api_key: API key for authentication

    Returns:
        List of model IDs
    """
    if not api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            data = response.json()
            return [model["id"] for model in data.get("data", [])]
    except (httpx.HTTPError, KeyError, ValueError):
        return []


async def get_models_for_provider(provider: str, use_cache: bool = True) -> List[str]:
    """Get model list for a provider, using cache if available.

    Args:
        provider: Provider name (e.g., "openrouter", "groq")
        use_cache: Whether to use cached results

    Returns:
        List of model IDs
    """
    cache_path = get_cache_path(provider)

    # Try cache first
    if use_cache and is_cache_valid(cache_path):
        cached_models = read_cache(cache_path)
        if cached_models:
            return cached_models

    # Fetch from API based on provider
    models = []

    if provider == "openrouter":
        models = await fetch_openrouter_models()
    elif provider == "poe":
        models = await fetch_poe_models()
    elif provider == "groq":
        models = await fetch_openai_compatible_models("https://api.groq.com/openai/v1", os.getenv("GROQ_API_KEY"))
    elif provider == "cerebras":
        models = await fetch_openai_compatible_models("https://api.cerebras.ai/v1", os.getenv("CEREBRAS_API_KEY"))
    elif provider == "together":
        models = await fetch_openai_compatible_models("https://api.together.xyz/v1", os.getenv("TOGETHER_API_KEY"))
    elif provider == "nebius":
        models = await fetch_openai_compatible_models(
            "https://api.studio.nebius.com/v1",
            os.getenv("NEBIUS_API_KEY"),
        )
    elif provider == "fireworks":
        # Fireworks uses OpenAI-compatible endpoint
        models = await fetch_openai_compatible_models(
            "https://api.fireworks.ai/inference/v1",
            os.getenv("FIREWORKS_API_KEY"),
        )
    elif provider == "moonshot":
        # Moonshot/Kimi uses OpenAI-compatible endpoint
        models = await fetch_openai_compatible_models("https://api.moonshot.cn/v1", os.getenv("MOONSHOT_API_KEY"))
    elif provider == "qwen":
        # Qwen uses DashScope API (OpenAI-compatible)
        models = await fetch_openai_compatible_models(
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            os.getenv("QWEN_API_KEY"),
        )

    # Cache the results
    if models:
        write_cache(cache_path, models)

    return models


def get_models_for_provider_sync(provider: str, use_cache: bool = True) -> List[str]:
    """Synchronous wrapper for get_models_for_provider.

    Args:
        provider: Provider name (e.g., "openrouter", "groq")
        use_cache: Whether to use cached results

    Returns:
        List of model IDs
    """
    import asyncio

    try:
        # Check if we're already in an async context
        try:
            asyncio.get_running_loop()
            # We're in an async context, need to run in thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, get_models_for_provider(provider, use_cache))
                return future.result(timeout=15)
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            return asyncio.run(get_models_for_provider(provider, use_cache))
    except Exception:
        # If async fails, return empty list
        return []
