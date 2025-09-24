# -*- coding: utf-8 -*-
"""
Chat Completions API parameters handler.
Handles parameter building for OpenAI Chat Completions API format.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from ._api_params_handler_base import APIParamsHandlerBase


class ChatCompletionsAPIParamsHandler(APIParamsHandlerBase):
    """Handler for Chat Completions API parameters."""

    def get_excluded_params(self) -> Set[str]:
        """Get parameters to exclude from Chat Completions API calls."""
        return self.get_base_excluded_params().union(
            {
                "base_url",  # Used for client initialization, not API calls
                "enable_web_search",
                "enable_code_interpreter",
                "allowed_tools",
                "exclude_tools",
            },
        )

    def get_provider_tools(self, all_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get provider tools for Chat Completions format."""
        provider_tools = []

        if all_params.get("enable_web_search", False):
            provider_tools.append(
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
            )

        if all_params.get("enable_code_interpreter", False):
            provider_tools.append(
                {
                    "type": "code_interpreter",
                    "container": {"type": "auto"},
                },
            )

        return provider_tools

    def build_base_api_params(self, messages: List[Dict[str, Any]], all_params: Dict[str, Any]) -> Dict[str, Any]:
        """Build base API parameters for Chat Completions requests."""
        # Sanitize: remove trailing assistant tool_calls without corresponding tool results
        sanitized_messages = self._sanitize_messages_for_api(messages)
        # Convert messages to ensure tool call arguments are properly serialized
        converted_messages = self.formatter.format_messages(sanitized_messages)

        api_params = {
            "messages": converted_messages,
            "stream": True,
        }

        # Direct passthrough of all parameters except those handled separately
        for key, value in all_params.items():
            if key not in self.EXCLUDED_API_PARAMS and value is not None:
                api_params[key] = value

        return api_params

    async def build_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build Chat Completions API parameters."""
        # Sanitize messages if needed
        if hasattr(self.backend, "_sanitize_messages_for_api"):
            messages = self.backend._sanitize_messages_for_api(messages)

        # Convert messages to Chat Completions format
        converted_messages = self.formatter.format_messages(messages)

        # Build base parameters
        api_params = {
            "messages": converted_messages,
            "stream": True,
        }

        # Add filtered parameters
        excluded = self.get_excluded_params()
        for key, value in all_params.items():
            if key not in excluded and value is not None:
                api_params[key] = value

        # Combine all tools
        combined_tools = []

        # Server-side tools (provider tools) go first
        provider_tools = self.get_provider_tools(all_params)
        if provider_tools:
            combined_tools.extend(provider_tools)

        # User-defined tools
        if tools:
            converted_tools = self.formatter.format_tools(tools)
            combined_tools.extend(converted_tools)

        # MCP tools
        mcp_tools = self.get_mcp_tools()
        if mcp_tools:
            combined_tools.extend(mcp_tools)

        if combined_tools:
            api_params["tools"] = combined_tools

        return api_params
