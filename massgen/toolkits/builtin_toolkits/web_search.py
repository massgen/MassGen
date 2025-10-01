# -*- coding: utf-8 -*-
"""
Web search toolkit for providing search capabilities.
"""

from typing import Any, Dict, List

from ..registry import BaseToolkit, ToolType


class WebSearchToolkit(BaseToolkit):
    """Web search toolkit implementation."""

    @property
    def toolkit_id(self) -> str:
        """Unique identifier for web search toolkit."""
        return "web_search"

    @property
    def toolkit_type(self) -> ToolType:
        """Type of this toolkit."""
        return ToolType.BUILTIN

    def is_enabled(self, config: Dict[str, Any]) -> bool:
        """
        Check if web search is enabled in configuration.

        Args:
            config: Configuration dictionary.

        Returns:
            True if enable_web_search is set to True.
        """
        return config.get("enable_web_search", False)

    def get_tools(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get web search tool definition based on API format.

        Args:
            config: Configuration including api_format.

        Returns:
            List containing the web search tool definition.
        """
        api_format = config.get("api_format", "chat_completions")

        if api_format == "response":
            # Response API format (simpler)
            return [{"type": "web_search"}]

        elif api_format == "claude":
            # Claude native format
            return [
                {
                    "name": "web_search",
                    "description": "Search the web for current or factual information",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to send to the web",
                            },
                        },
                        "required": ["query"],
                    },
                },
            ]

        else:
            # Default Chat Completions format
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Search the web for current or factual information",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query to send to the web",
                                },
                            },
                            "required": ["query"],
                        },
                    },
                },
            ]
