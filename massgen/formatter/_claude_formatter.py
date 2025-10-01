# -*- coding: utf-8 -*-
"""
Claude formatter implementation.
Handles formatting for Anthropic Claude Messages API format.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ._formatter_base import FormatterBase


class ClaudeFormatter(FormatterBase):
    """Formatter for Claude API format."""

    def format_messages(self, messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
        """
        Convert messages to Claude's expected format.

        Handle different tool message formats and extract system message:
        - Chat Completions tool message: {"role": "tool", "tool_call_id": "...", "content": "..."}
        - Response API tool message: {"type": "function_call_output", "call_id": "...", "output": "..."}
        - System messages: Extract and return separately for top-level system parameter

        Returns:
            tuple: (converted_messages, system_message)
        """
        converted_messages = []
        system_message = ""

        for message in messages:
            if message.get("role") == "system":
                # Extract system message for top-level parameter
                system_message = message.get("content", "")
            elif message.get("role") == "tool":
                # Chat Completions tool message -> Claude tool result
                converted_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.get("tool_call_id"),
                                "content": message.get("content", ""),
                            },
                        ],
                    },
                )
            elif message.get("type") == "function_call_output":
                # Response API tool message -> Claude tool result
                converted_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.get("call_id"),
                                "content": message.get("output", ""),
                            },
                        ],
                    },
                )
            elif message.get("role") == "assistant" and "tool_calls" in message:
                # Assistant message with tool calls - convert to Claude format
                content = []

                # Add text content if present
                if message.get("content"):
                    content.append({"type": "text", "text": message["content"]})

                # Convert tool calls to Claude tool use format
                for tool_call in message["tool_calls"]:
                    tool_name = self.extract_tool_name(tool_call)
                    tool_args = self.extract_tool_arguments(tool_call)
                    tool_id = self.extract_tool_call_id(tool_call)

                    content.append(
                        {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": tool_name,
                            "input": tool_args,
                        },
                    )

                converted_messages.append({"role": "assistant", "content": content})
            elif message.get("role") in ["user", "assistant"]:
                # Keep user and assistant messages, skip system
                converted_message = dict(message)
                if isinstance(converted_message.get("content"), str):
                    # Claude expects content to be text for simple messages
                    pass
                converted_messages.append(converted_message)

        return converted_messages, system_message

    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert tools to Claude's expected format.

        Input formats supported:
        - Response API format: {"type": "function", "name": ..., "description": ..., "parameters": ...}
        - Chat Completions format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

        Claude format: {"type": "custom", "name": ..., "description": ..., "input_schema": ...}
        """
        if not tools:
            return tools

        converted_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                if "function" in tool:
                    # Chat Completions format -> Claude custom tool
                    func = tool["function"]
                    converted_tools.append(
                        {
                            "type": "custom",
                            "name": func["name"],
                            "description": func["description"],
                            "input_schema": func.get("parameters", {}),
                        },
                    )
                elif "name" in tool and "description" in tool:
                    # Response API format -> Claude custom tool
                    converted_tools.append(
                        {
                            "type": "custom",
                            "name": tool["name"],
                            "description": tool["description"],
                            "input_schema": tool.get("parameters", {}),
                        },
                    )
                else:
                    # Unknown format - keep as-is
                    converted_tools.append(tool)
            else:
                # Non-function tool (builtin tools) - keep as-is
                converted_tools.append(tool)

        return converted_tools

    def format_mcp_tools(self, mcp_functions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert MCP tools to Claude's custom tool format."""
        if not mcp_functions:
            return []

        converted_tools = []
        for mcp_function in mcp_functions.values():
            if hasattr(mcp_function, "to_claude_format"):
                tool = mcp_function.to_claude_format()
            else:
                # Fallback format for Claude
                tool = {
                    "type": "custom",
                    "name": getattr(mcp_function, "name", "unknown"),
                    "description": getattr(mcp_function, "description", ""),
                    "input_schema": getattr(mcp_function, "input_schema", {}),
                }
            converted_tools.append(tool)

        return converted_tools
