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

    def format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        formatted, _ = self.format_messages_and_system(messages)
        return formatted

    def format_messages_and_system(
        self,
        messages: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], str]:
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
                elif isinstance(converted_message.get("content"), list):
                    converted_message = self._convert_multimodal_content(converted_message)
                converted_messages.append(converted_message)

        return converted_messages, system_message

    def _convert_multimodal_content(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize multimodal content blocks to Claude's nested source structure."""

        content = message.get("content")
        if not isinstance(content, list):
            return message

        # Formatter handles generic multimodal content; upload_files-sourced items already preprocessed in backend.
        converted_items: List[Dict[str, Any]] = []

        for item in content:
            if not isinstance(item, dict):
                converted_items.append(item)
                continue

            item_type = item.get("type")

            if item_type in {"tool_result", "tool_use", "text", "file_pending_upload"}:
                converted_items.append(item)
                continue

            if item_type not in {"image", "document"}:
                converted_items.append(item)
                continue

            if isinstance(item.get("source"), dict):
                converted_items.append(item)
                continue

            if "file_id" in item:
                normalized = {key: value for key, value in item.items() if key != "file_id"}
                normalized["source"] = {
                    "type": "file",
                    "file_id": item["file_id"],
                }
                converted_items.append(normalized)
                continue

            if "base64" in item:
                media_type = item.get("mime_type") or item.get("media_type")
                normalized = {key: value for key, value in item.items() if key not in {"base64", "mime_type", "media_type"}}
                normalized["source"] = {
                    "type": "base64",
                    "media_type": media_type,
                    "data": item["base64"],
                }
                converted_items.append(normalized)
                continue

            if "url" in item:
                normalized = {key: value for key, value in item.items() if key != "url"}
                normalized["source"] = {
                    "type": "url",
                    "url": item["url"],
                }
                converted_items.append(normalized)
                continue

            converted_items.append(item)

        message["content"] = converted_items
        return message

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

    def format_custom_tools(self, custom_tools: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Convert custom tools from RegisteredToolEntry format to Claude's custom tool format.

        Custom tools are provided as a dictionary where:
        - Keys are tool names (str)
        - Values are RegisteredToolEntry objects with:
          - tool_name: str
          - schema_def: dict with structure {"type": "function", "function": {...}}
          - get_extended_schema: property that returns the schema with extensions

        Claude expects: {"type": "custom", "name": ..., "description": ..., "input_schema": ...}

        Args:
            custom_tools: Dictionary of tool_name -> RegisteredToolEntry objects

        Returns:
            List of tools in Claude's custom tool format
        """
        if not custom_tools:
            return []

        converted_tools = []

        # Handle dictionary format: {tool_name: RegisteredToolEntry, ...}
        if isinstance(custom_tools, dict):
            for tool_name, tool_entry in custom_tools.items():
                # Check if it's a RegisteredToolEntry object with schema_def
                if hasattr(tool_entry, "schema_def"):
                    tool_schema = tool_entry.schema_def

                    # Extract function details from Chat Completions format
                    if tool_schema.get("type") == "function" and "function" in tool_schema:
                        func = tool_schema["function"]
                        converted_tools.append(
                            {
                                "type": "custom",
                                "name": func.get("name", tool_entry.tool_name if hasattr(tool_entry, "tool_name") else tool_name),
                                "description": func.get("description", ""),
                                "input_schema": func.get("parameters", {}),
                            },
                        )
                    elif tool_schema.get("type") == "function":
                        # Response API format - already has name, description, parameters at top level
                        converted_tools.append(
                            {
                                "type": "custom",
                                "name": tool_schema.get("name", tool_entry.tool_name if hasattr(tool_entry, "tool_name") else tool_name),
                                "description": tool_schema.get("description", ""),
                                "input_schema": tool_schema.get("parameters", {}),
                            },
                        )
                    else:
                        # Unknown format, try to extract what we can
                        converted_tools.append(
                            {
                                "type": "custom",
                                "name": tool_entry.tool_name if hasattr(tool_entry, "tool_name") else tool_name,
                                "description": tool_schema.get("description", ""),
                                "input_schema": tool_schema.get("parameters", {}),
                            },
                        )
                # Handle direct schema format (for backward compatibility)
                elif isinstance(tool_entry, dict):
                    if tool_entry.get("type") == "function" and "function" in tool_entry:
                        # Chat Completions format
                        func = tool_entry["function"]
                        converted_tools.append(
                            {
                                "type": "custom",
                                "name": func.get("name", tool_name),
                                "description": func.get("description", ""),
                                "input_schema": func.get("parameters", {}),
                            },
                        )
                    elif tool_entry.get("type") == "function":
                        # Response API format
                        converted_tools.append(
                            {
                                "type": "custom",
                                "name": tool_entry.get("name", tool_name),
                                "description": tool_entry.get("description", ""),
                                "input_schema": tool_entry.get("parameters", {}),
                            },
                        )
                    else:
                        # Already in Claude format or unknown
                        converted_tools.append(tool_entry)

        # Handle list format (if custom_tools is already a list)
        elif isinstance(custom_tools, list):
            for tool in custom_tools:
                if isinstance(tool, dict):
                    if tool.get("type") == "function" and "function" in tool:
                        # Chat Completions format
                        func = tool["function"]
                        converted_tools.append(
                            {
                                "type": "custom",
                                "name": func.get("name", ""),
                                "description": func.get("description", ""),
                                "input_schema": func.get("parameters", {}),
                            },
                        )
                    elif tool.get("type") == "function":
                        # Response API format
                        converted_tools.append(
                            {
                                "type": "custom",
                                "name": tool.get("name", ""),
                                "description": tool.get("description", ""),
                                "input_schema": tool.get("parameters", {}),
                            },
                        )
                    else:
                        # Already in Claude format or unknown
                        converted_tools.append(tool)

        return converted_tools
