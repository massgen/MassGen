# -*- coding: utf-8 -*-
"""
Built-in toolkits module providing common tools like web search and code interpreter.
"""

import logging
from typing import Optional

from ..registry import BaseToolkit, toolkit_registry
from .code_interpreter import CodeInterpreterToolkit
from .web_search import WebSearchToolkit

logger = logging.getLogger(__name__)

# Registry of builtin toolkit classes for lazy loading
_BUILTIN_TOOLKIT_CLASSES = {
    "web_search": WebSearchToolkit,
    "code_interpreter": CodeInterpreterToolkit,
}

# Lazy loading registry for advanced toolkits
_LAZY_TOOLKIT_REGISTRY = {
    # Example for future additions:
    # 'code_execution': 'massgen.toolkits.builtin_toolkits.gemini:GeminiCodeExecutionToolkit',
}


def get_toolkit_by_name(name: str) -> Optional[BaseToolkit]:
    """
    Get a builtin toolkit instance by name.

    Args:
        name: Name of the toolkit to retrieve.

    Returns:
        Toolkit instance or None if not found.
    """
    # Check direct classes first
    if name in _BUILTIN_TOOLKIT_CLASSES:
        return _BUILTIN_TOOLKIT_CLASSES[name]()

    # Check lazy registry
    if name in _LAZY_TOOLKIT_REGISTRY:
        try:
            module_path, class_name = _LAZY_TOOLKIT_REGISTRY[name].split(":")
            module = __import__(module_path, fromlist=[class_name])
            toolkit_class = getattr(module, class_name)
            return toolkit_class()
        except Exception as e:
            logger.error(f"Failed to load toolkit {name}: {e}")
            return None

    return None


def register_builtin_toolkits():
    """
    Register all builtin toolkits with their supported providers.
    This should be called during application initialization.
    """
    logger.info("Registering builtin toolkits...")

    # Web search toolkit - supported by OpenAI-compatible providers
    toolkit_registry.register(
        WebSearchToolkit(),
        providers=["openai", "azure_openai", "grok", "lmstudio", "chat_completions"],
    )

    # Code interpreter toolkit - supported by OpenAI-compatible providers
    toolkit_registry.register(
        CodeInterpreterToolkit(),
        providers=["openai", "azure_openai", "grok", "chat_completions"],
    )

    logger.info("Builtin toolkits registered successfully")


# Optional: Auto-register on import (can be disabled if manual control is preferred)
# Uncomment the following line to enable auto-registration
# register_builtin_toolkits()
