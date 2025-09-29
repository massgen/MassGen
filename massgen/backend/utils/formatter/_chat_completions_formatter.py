# -*- coding: utf-8 -*-
"""
Chat Completions formatter implementation.
Handles formatting for OpenAI Chat Completions API format.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ._formatter_base import FormatterBase


class ChatCompletionsFormatter(FormatterBase):
    """Formatter for Chat Completions API format."""

    def format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert messages for Chat Completions API compatibility.

        Chat Completions API expects tool call arguments as JSON strings in conversation history,
        but they may be passed as objects from other parts of the system.
        """
        converted_messages = []

        for message in messages:
            # Create a copy to avoid modifying the original
            converted_msg = dict(message)

            # Convert tool_calls arguments from objects to JSON strings
            if message.get("role") == "assistant" and "tool_calls" in message:
                converted_tool_calls = []
                for tool_call in message["tool_calls"]:
                    converted_call = dict(tool_call)
                    if "function" in converted_call:
                        converted_function = dict(converted_call["function"])
                        arguments = converted_function.get("arguments")

                        # Convert arguments to JSON string if it's an object
                        if isinstance(arguments, dict):
                            converted_function["arguments"] = json.dumps(arguments)
                        elif arguments is None:
                            converted_function["arguments"] = "{}"
                        elif not isinstance(arguments, str):
                            # Handle other non-string types
                            converted_function["arguments"] = self._serialize_tool_arguments(arguments)
                        # If it's already a string, keep it as-is

                        converted_call["function"] = converted_function
                    converted_tool_calls.append(converted_call)
                converted_msg["tool_calls"] = converted_tool_calls

            converted_messages.append(converted_msg)

        return converted_messages

    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert tools to Chat Completions format if needed.

        Response API format: {"type": "function", "name": ..., "description": ..., "parameters": ...}
        Chat Completions format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        """
        if not tools:
            return tools

        converted_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                if "function" in tool:
                    # Already in Chat Completions format
                    converted_tools.append(tool)
                elif "name" in tool and "description" in tool:
                    # Response API format - convert to Chat Completions format
                    converted_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool["name"],
                                "description": tool["description"],
                                "parameters": tool.get("parameters", {}),
                            },
                        },
                    )
                else:
                    # Unknown format - keep as-is
                    converted_tools.append(tool)
            else:
                # Non-function tool - keep as-is
                converted_tools.append(tool)

        return converted_tools

    def format_mcp_tools(self, mcp_functions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert MCP tools to Chat Completions format."""
        if not mcp_functions:
            return []

        converted_tools = []
        for mcp_function in mcp_functions.values():
            if hasattr(mcp_function, "to_chat_completions_format"):
                tool = mcp_function.to_chat_completions_format()
            elif hasattr(mcp_function, "to_openai_format"):
                tool = mcp_function.to_openai_format()
            else:
                # Fallback format
                tool = {
                    "type": "function",
                    "function": {
                        "name": getattr(mcp_function, "name", "unknown"),
                        "description": getattr(mcp_function, "description", ""),
                        "parameters": getattr(mcp_function, "input_schema", {}),
                    },
                }
            converted_tools.append(tool)

        return converted_tools
