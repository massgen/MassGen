"""Centralized constants for backend operations.

This module defines common constants used across different backend implementations,
including provider-specific defaults and configuration values.
"""

from typing import Any

from ..logger_config import logger

# =============================================================================
# OPENROUTER CONSTANTS
# =============================================================================

# Default search engine for OpenRouter web search plugin
# Options: "exa" (default, AI-native search) or "native" (traditional search)
OPENROUTER_DEFAULT_WEB_ENGINE = "exa"

# Default maximum number of search results to return (OpenRouter default is 5)
OPENROUTER_DEFAULT_WEB_MAX_RESULTS = 5

# Valid engine options for OpenRouter web search
OPENROUTER_VALID_WEB_ENGINES = {"exa", "native"}

# Valid search context size options for OpenRouter web search
OPENROUTER_VALID_SEARCH_CONTEXT_SIZES = {"low", "medium", "high"}

# Valid reasoning effort levels for OpenRouter
# See: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
OPENROUTER_VALID_REASONING_EFFORTS = {"xhigh", "high", "medium", "low", "minimal", "none"}


def configure_openrouter_extra_body(
    api_params: dict[str, Any],
    all_params: dict[str, Any],
) -> dict[str, Any] | None:
    """Configure extra_body for OpenRouter API requests.

    Handles cost tracking, provider routing, and web search plugin configuration
    with validation.

    Args:
        api_params: API parameters dict (modified in place)
        all_params: All configuration parameters

    Returns:
        The extra_body dict if OpenRouter detected, None otherwise

    Raises:
        ValueError: If engine is invalid, max_results is not a positive integer,
            or provider_order is not a list of strings
    """
    base_url = all_params.get("base_url", "")
    if "openrouter.ai" not in base_url.lower():
        return None

    extra_body = api_params.get("extra_body", {})
    if not isinstance(extra_body, dict):
        extra_body = {}

    # Enable cost tracking in usage response
    extra_body["usage"] = {"include": True}

    # Configure provider routing order
    # See: https://openrouter.ai/docs/features/provider-routing
    provider_order = all_params.get("provider_order")
    if provider_order is not None:
        if not isinstance(provider_order, list) or not all(isinstance(p, str) for p in provider_order):
            raise ValueError(
                f"OpenRouter provider_order must be a list of provider slug strings, got: {provider_order}",
            )
        if "provider" not in extra_body:
            extra_body["provider"] = {}
        extra_body["provider"]["order"] = provider_order
        logger.info(f"[OpenRouter] Provider order set: {provider_order}")

    # Enable web search via plugins array
    if all_params.get("enable_web_search", False):
        # Validate engine parameter
        engine = all_params.get("engine", OPENROUTER_DEFAULT_WEB_ENGINE)
        if engine not in OPENROUTER_VALID_WEB_ENGINES:
            raise ValueError(
                f"Invalid OpenRouter web search engine: '{engine}'. " f"Must be one of: {OPENROUTER_VALID_WEB_ENGINES}",
            )

        # Validate max_results parameter
        max_results = all_params.get("max_results", OPENROUTER_DEFAULT_WEB_MAX_RESULTS)
        if not isinstance(max_results, int) or max_results < 1:
            raise ValueError(
                f"OpenRouter max_results must be a positive integer, got: {max_results}",
            )

        web_plugin = {
            "id": "web",
            "engine": engine,
            "max_results": max_results,
        }

        # Add optional search_prompt if provided
        search_prompt = all_params.get("search_prompt")
        if search_prompt:
            web_plugin["search_prompt"] = search_prompt

        if "plugins" not in extra_body:
            extra_body["plugins"] = []
        extra_body["plugins"].append(web_plugin)

        # Add web_search_options for search_context_size if provided
        search_context_size = all_params.get("search_context_size")
        if search_context_size:
            if search_context_size not in OPENROUTER_VALID_SEARCH_CONTEXT_SIZES:
                raise ValueError(
                    f"Invalid OpenRouter search_context_size: '{search_context_size}'. " f"Must be one of: {OPENROUTER_VALID_SEARCH_CONTEXT_SIZES}",
                )
            extra_body["web_search_options"] = {"search_context_size": search_context_size}

        logger.info(f"[OpenRouter] Web search plugin enabled: {web_plugin}")

    # Handle reasoning parameter for OpenRouter
    # OpenRouter normalizes reasoning tokens across providers via extra_body.reasoning
    # See: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
    reasoning_config = all_params.get("reasoning") or api_params.get("reasoning")
    if reasoning_config:
        # Remove from api_params if present (will be moved to extra_body)
        api_params.pop("reasoning", None)

        if isinstance(reasoning_config, dict):
            # Validate effort level if provided
            effort = reasoning_config.get("effort")
            if effort and effort not in OPENROUTER_VALID_REASONING_EFFORTS:
                raise ValueError(
                    f"Invalid OpenRouter reasoning effort: '{effort}'. " f"Must be one of: {OPENROUTER_VALID_REASONING_EFFORTS}",
                )

            # Validate max_tokens if provided
            max_tokens = reasoning_config.get("max_tokens")
            if max_tokens is not None:
                if not isinstance(max_tokens, int) or max_tokens < 1:
                    raise ValueError(
                        f"OpenRouter reasoning max_tokens must be a positive integer, got: {max_tokens}",
                    )

            extra_body["reasoning"] = reasoning_config
            logger.info(f"[OpenRouter] Reasoning enabled: {reasoning_config}")
        elif reasoning_config is True:
            # Simple boolean enable - use default medium effort
            extra_body["reasoning"] = {"enabled": True}
            logger.info("[OpenRouter] Reasoning enabled with defaults")

    api_params["extra_body"] = extra_body
    return extra_body
