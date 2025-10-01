# -*- coding: utf-8 -*-
"""
Claude API parameters handler.
Handles parameter building for Anthropic Claude Messages API format.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from ._api_params_handler_base import APIParamsHandlerBase


class ClaudeAPIParamsHandler(APIParamsHandlerBase):
    """Handler for Claude API parameters."""

    def get_excluded_params(self) -> Set[str]:
        """Get parameters to exclude from Claude API calls."""
        return self.get_base_excluded_params().union(
            {
                "enable_web_search",
                "enable_code_execution",
                "allowed_tools",
                "exclude_tools",
                "custom_toolkits",  # Handled by backend initialization
            },
        )

    def get_api_format(self) -> str:
        """Get the API format for Claude."""
        return "claude"

    def get_provider_tools(self, all_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get provider tools for Claude format (server-side tools).
        Note: Claude has special format for server-side tools.
        """
        # Use base implementation to get tools from registry
        tools = super().get_provider_tools(all_params)

        # Claude-specific transformations for server-side tools
        claude_tools = []
        for tool in tools:
            # Check if it's a web_search tool
            if tool.get("name") == "web_search" or (tool.get("function", {}).get("name") == "web_search"):
                claude_tools.append(
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                    },
                )
            # Check if it's a code execution tool
            elif tool.get("name") == "code_execution" or tool.get("type") == "code_interpreter":
                if all_params.get("enable_code_execution", False):
                    claude_tools.append(
                        {
                            "type": "code_execution_20250522",
                            "name": "code_execution",
                        },
                    )

        return claude_tools

    async def build_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build Claude API parameters."""
        # Convert messages to Claude format and extract system message
        converted_messages, system_message = self.formatter.format_messages(messages)

        # Build base parameters
        api_params: Dict[str, Any] = {
            "messages": converted_messages,
            "stream": True,
        }

        # Add filtered parameters
        excluded = self.get_excluded_params()
        for key, value in all_params.items():
            if key not in excluded and value is not None:
                api_params[key] = value

        # Claude API requires max_tokens - add default if not provided
        if "max_tokens" not in api_params:
            api_params["max_tokens"] = 4096

        if all_params.get("enable_code_execution"):
            api_params["betas"] = ["code-execution-2025-05-22"]

        # Add system message if present
        if system_message:
            api_params["system"] = system_message

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
