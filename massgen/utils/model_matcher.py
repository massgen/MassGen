# -*- coding: utf-8 -*-
"""
Fuzzy model name matching utility for config builder.
Allows users to type approximate model names and find exact matches.

Based on contribution from acrobat3 (K. from JP).
"""

from typing import List

from massgen.backend.capabilities import BACKEND_CAPABILITIES

# Curated lists of common models for providers with many models
# Used for fuzzy matching when full model list is too large to enumerate
COMMON_MODELS_BY_PROVIDER = {
    "openrouter": [
        # Anthropic models
        "anthropic/claude-sonnet-4-5-20250929",
        "anthropic/claude-opus-4-1-20250805",
        "anthropic/claude-sonnet-4-20250514",
        "anthropic/claude-3-7-sonnet-20250219",
        "anthropic/claude-3-5-sonnet-20241022",
        "anthropic/claude-3-5-haiku-20241022",
        # OpenAI models
        "openai/gpt-5",
        "openai/gpt-5-mini",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openai/o3",
        "openai/o3-mini",
        # Google models
        "google/gemini-2.5-flash",
        "google/gemini-2.5-pro",
        "google/gemini-2.0-flash-exp",
        # Meta models
        "meta-llama/llama-3.3-70b-instruct",
        "meta-llama/llama-3.1-405b-instruct",
        "meta-llama/llama-3.1-70b-instruct",
        # Mistral models
        "mistralai/mistral-large-2411",
        "mistralai/mistral-small-2501",
        # DeepSeek
        "deepseek/deepseek-chat",
        "deepseek/deepseek-r1",
        # Qwen
        "qwen/qwen-2.5-72b-instruct",
        "qwen/qwq-32b-preview",
        # X.AI
        "x-ai/grok-4",
        "x-ai/grok-4-fast",
    ],
    "poe": [
        # Top models on POE
        "GPT-5-Chat",
        "Claude-Sonnet-4.5",
        "Gemini-2.5-Pro",
        "GPT-5",
        "Grok-4",
        "GPT-5-Pro",
        "GPT-5-Codex",
        "GPT-4o",
        "Claude-Haiku-4.5",
        "Claude-Opus-4.1",
        "GPT-5-mini",
        "Grok-4-Fast-Reasoning",
        "Grok-4-Fast-Non-Reasoning",
        "DeepSeek-R1",
        "Assistant",
    ],
    "nebius": [
        "deepseek-ai/DeepSeek-R1-0528",
        "deepseek-ai/DeepSeek-V3-0324",
        "deepseek-ai/DeepSeek-R1-Distill-70B",
        "meta-llama/Meta-Llama-3.1-70B-Instruct",
        "meta-llama/Meta-Llama-3.3-70B-Instruct",
        "Qwen/Qwen3-235B-A22B",
        "Qwen/Qwen2.5-72B-Instruct",
        "Qwen/Qwen3-4B-fast",
        "Qwen/QwQ-32B",
        "THUDM/GLM-4.5",
        "google/gemma-2-9b-it",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "meta-llama/llama-guard-4-12b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "whisper-large-v3",
        "whisper-large-v3-turbo",
        "groq/compound",
        "groq/compound-mini",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    ],
    "cerebras": [
        "llama3.1-8b",
        "llama-3.3-70b",
        "qwen-3-32b",
        "qwen-3-235b-a22b-instruct-2507",
        "qwen-3-235b-a22b-thinking-2507",
        "gpt-oss-120b",
        "llama-4-scout-17b-16e-instruct",
        "llama-4-maverick-17b-128e-instruct",
        "deepseek-r1-distill-llama-70b",
        "qwen-3-coder-480b",
    ],
    "together": [
        "meta-llama/Llama-Vision-Free",
        "meta-llama/Llama-3-3-70b",
        "meta-llama/Llama-3.1-405B-Instruct-Turbo",
        "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "deepseek-ai/deepseek-v3",
        "deepseek-ai/deepseek-r1",
        "Qwen/Qwen2.5-Coder-32B-Instruct",
        "Qwen/QwQ-32B",
        "meta-llama/Llama-3.2-11b-free",
        "meta-llama/Llama-3.2-90b",
        "meta-llama/Llama-4-Maverick",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
    ],
    "fireworks": [
        "fireworks/kimi-k2-instruct-0905",
        "fireworks/deepseek-v3p1",
        "fireworks/glm-4p6",
        "fireworks/qwen2p5-coder-32b-instruct",
        "fireworks/qwen3-coder-30b-a3b-instruct",
        "fireworks/qwen3-235b-a22b",
        "fireworks/gpt-oss-120b",
        "fireworks/qwen2p5-72b-instruct",
        "fireworks/llama-v3p3-70b-instruct",
        "fireworks/qwen3-vl-235b-a22b",
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "accounts/fireworks/models/qwen2p5-72b-instruct",
    ],
    "moonshot": [
        "moonshot-v1-8k",
        "moonshot-v1-32k",
        "moonshot-v1-128k",
        "moonshot-v1-auto",
        "moonshot-v1-8k-vision-preview",
        "moonshot-v1-32k-vision-preview",
        "moonshot-v1-128k-vision-preview",
        "kimi-k2-instruct",
        "kimi-k2-base",
    ],
    "qwen": [
        "qwen3-max",
        "qwen3-max-2025-09-23",
        "qwen-plus",
        "qwen-plus-latest",
        "qwen-turbo",
        "qwen-flash",
        "qwq-plus",
        "qwen-long-latest",
        "qwen3-coder-plus",
        "qwen3-vl-plus",
        "qwen3-235b-a22b",
        "qwen3-32b",
        "qwen3-14b",
        "qwen3-8b",
        "qwen2.5-72b-instruct",
        "qwq-32b",
    ],
}


def get_all_models_for_provider(provider_type: str, use_api: bool = True) -> List[str]:
    """Get all models for a specific provider from capabilities registry.

    For providers with many models (marked as "custom"), attempts to fetch from API first,
    then falls back to curated common models. Otherwise returns the full list from capabilities.

    Args:
        provider_type: Backend type (e.g., "openai", "openrouter")
        use_api: Whether to attempt fetching from provider API (default True)

    Returns:
        List of model names for that provider
    """
    caps = BACKEND_CAPABILITIES.get(provider_type)
    if not caps:
        return []

    # All chatcompletion providers can potentially fetch from API
    chatcompletion_providers = [
        "openrouter",
        "poe",
        "groq",
        "cerebras",
        "together",
        "nebius",
        "fireworks",
        "moonshot",
        "qwen",
    ]

    # Try API first for chatcompletion providers
    if use_api and provider_type in chatcompletion_providers:
        try:
            from .model_catalog import get_models_for_provider_sync

            api_models = get_models_for_provider_sync(provider_type, use_cache=True)
            if api_models and len(api_models) > 0:
                return api_models
        except Exception:
            # Fall through to curated list or capabilities
            pass

    # If provider has "custom" in models, try curated list
    if "custom" in caps.models and provider_type in COMMON_MODELS_BY_PROVIDER:
        return COMMON_MODELS_BY_PROVIDER[provider_type]

    return caps.models
