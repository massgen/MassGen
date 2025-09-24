# -*- coding: utf-8 -*-
"""
Message formatter for different LLM APIs.
Handles conversion between OpenAI, Claude, and Response API formats.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..logger_config import logger


class MCPToolFormatter:
    """
    Convert messages between different API formats.
    Supports bidirectional conversion between all major formats.
    """

    @staticmethod
    def to_chat_completions_format(mcp_functions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert MCP tools (stdio + streamable-http) to Chat Completions format."""
        if not mcp_functions:
            return []

        converted_tools = []
        for mcp_function in mcp_functions.values():
            tool = mcp_function.to_chat_completions_format()
            converted_tools.append(tool)

        logger.info(f"Converted {len(converted_tools)} MCP tools (stdio + streamable-http) to Chat Completions format")
        return converted_tools

    @staticmethod
    def to_claude_format(mcp_functions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert MCP tools to Claude's custom tool format."""
        if not mcp_functions:
            return []
        converted: List[Dict[str, Any]] = []
        for mcp_function in mcp_functions.values():
            try:
                converted.append(mcp_function.to_claude_format())
            except Exception as e:
                logger.warning(f"Failed to convert MCP function to Claude format: {e}")
                continue
        logger.debug(f"Converted {len(converted)} MCP tools to Claude format")
        return converted

    @staticmethod
    def to_response_api_format(mcp_functions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert MCP tools (stdio + streamable-http) to OpenAI function declarations."""
        if not mcp_functions:
            return []

        converted_tools = []
        for mcp_function in mcp_functions.values():
            converted_tools.append(mcp_function.to_openai_format())

        logger.debug(f"Converted {len(converted_tools)} MCP tools (stdio + streamable-http) to OpenAI format")
        return converted_tools

    @staticmethod
    def convert_between_formats(mcp_functions: Dict[str, Any], source_format: str, target_format: str) -> List[Dict[str, Any]]:
        """
        Convert MCP functions from one format to another.

        Args:
            mcp_functions: Dictionary of MCP Function objects
            source_format: Source format (not used for MCP functions as they have built-in converters)
            target_format: One of "chat_completions", "claude", "response_api"

        Returns:
            Tools in target format
        """
        if not mcp_functions:
            return []

        # MCP functions have built-in conversion methods
        if target_format == "chat_completions":
            return MCPToolFormatter.to_chat_completions_format(mcp_functions)
        elif target_format == "claude":
            return MCPToolFormatter.to_claude_format(mcp_functions)
        elif target_format == "response_api":
            return MCPToolFormatter.to_response_api_format(mcp_functions)

        raise ValueError(f"Unsupported target format for MCP functions: {target_format}")
