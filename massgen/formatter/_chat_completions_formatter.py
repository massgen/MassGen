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

            # Normalize multimodal content (text/image/audio/video)
            converted_msg = self._convert_multimodal_content(converted_msg)

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

    def _convert_multimodal_content(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert multimodal content to Chat Completions API format.
        """
        content = message.get("content")

        # If content is not a list, no conversion needed
        if not isinstance(content, list):
            return message

        converted_content = []
        for item in content:
            if not isinstance(item, dict):
                # If item is a string, treat as text
                converted_content.append({"type": "text", "text": str(item)})
                continue

            item_type = item.get("type")

            if item_type == "text":
                # Text items pass through as-is
                converted_content.append(item)

            elif item_type == "image":
                # Convert image item to image_url format
                converted_item = self._convert_image_content(item)
                if converted_item:
                    converted_content.append(converted_item)

            elif item_type == "audio":
                # Convert audio item to input_audio format (base64)
                converted_item = self._convert_audio_content(item)
                if converted_item:
                    converted_content.append(converted_item)

            elif item_type == "video":
                # Convert video item to video_url format (base64 data URL)
                converted_item = self._convert_video_content(item)
                if converted_item:
                    converted_content.append(converted_item)

            elif item_type == "video_url":
                # Convert video URL to video_url format
                converted_item = self._convert_video_url_content(item)
                if converted_item:
                    converted_content.append(converted_item)

            elif item_type == "file_pending_upload":
                continue
            elif item_type in ["image_url", "input_audio", "video_url"]:
                # Already in Chat Completions API format
                converted_content.append(item)

            else:
                # Unknown type, pass through
                converted_content.append(item)

        message["content"] = converted_content
        return message

    def _convert_image_content(self, image_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert image content item to Chat Completions API format.

        Supports:
        - URL format: {"type": "image", "url": "https://..."}
        - Base64 format: {"type": "image", "base64": "...", "mime_type": "image/jpeg"}

        Returns Chat Completions format: {"type": "image_url", "image_url": {"url": "..."}}
        """
        # Handle URL format
        if "url" in image_item:
            return {
                "type": "image_url",
                "image_url": {"url": image_item["url"]},
            }

        # Handle base64 format
        if "base64" in image_item:
            mime_type = image_item.get("mime_type", "image/jpeg")
            base64_data = image_item["base64"]

            # Create data URL
            data_url = f"data:{mime_type};base64,{base64_data}"
            return {
                "type": "image_url",
                "image_url": {"url": data_url},
            }

        # No valid image data found
        return None

    def _convert_audio_content(self, audio_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert audio content item to Chat Completions API format.

        Supports base64 format: {"type": "audio", "base64": "...", "mime_type": "audio/wav"}

        Returns Chat Completions format: {"type": "input_audio", "input_audio": {"data": "...", "format": "wav"}}
        """
        if "base64" not in audio_item:
            return None

        base64_data = audio_item["base64"]
        mime_type = audio_item.get("mime_type", "audio/wav")

        # Extract format from MIME type (e.g., "audio/wav" → "wav")
        audio_format = mime_type.split("/")[-1] if "/" in mime_type else "wav"

        # Map common MIME types to OpenAI audio formats
        format_mapping = {
            "mpeg": "mp3",
            "x-wav": "wav",
            "wave": "wav",
        }
        audio_format = format_mapping.get(audio_format, audio_format)

        return {
            "type": "input_audio",
            "input_audio": {
                "data": base64_data,
                "format": audio_format,
            },
        }

    def _convert_video_content(self, video_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert video content item to Chat Completions API format.

        Supports base64 format: {"type": "video", "base64": "...", "mime_type": "video/mp4"}

        Returns format: {"type": "video_url", "video_url": {"url": "data:video/...;base64,..."}}
        """
        if "base64" not in video_item:
            return None

        base64_data = video_item["base64"]
        mime_type = video_item.get("mime_type", "video/mp4")

        # Create data URL
        data_url = f"data:{mime_type};base64,{base64_data}"

        return {
            "type": "video_url",
            "video_url": {"url": data_url},
        }

    def _convert_video_url_content(self, video_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert video URL content item to Chat Completions API format.

        Supports URL format: {"type": "video_url", "url": "https://..."}

        Returns format: {"type": "video_url", "video_url": {"url": "..."}}
        """
        if "url" not in video_item:
            return None

        return {
            "type": "video_url",
            "video_url": {"url": video_item["url"]},
        }

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

    def format_custom_tools(self, custom_tools: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Convert custom tools from RegisteredToolEntry format to Chat Completions API format.

        Custom tools are provided as a dictionary where:
        - Keys are tool names (str)
        - Values are RegisteredToolEntry objects with:
          - tool_name: str
          - schema_def: dict with structure {"type": "function", "function": {...}}
          - get_extended_schema: property that returns the schema with extensions

        Chat Completions API expects: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

        Args:
            custom_tools: Dictionary of tool_name -> RegisteredToolEntry objects

        Returns:
            List of tools in Chat Completions API format
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

                    # Schema may already be in Chat Completions format
                    if tool_schema.get("type") == "function" and "function" in tool_schema:
                        # Already in correct format, just append
                        converted_tools.append(tool_schema)
                    elif tool_schema.get("type") == "function":
                        # Response API format, need to wrap in function object
                        converted_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool_schema.get("name", tool_entry.tool_name if hasattr(tool_entry, "tool_name") else tool_name),
                                "description": tool_schema.get("description", ""),
                                "parameters": tool_schema.get("parameters", {}),
                            }
                        })
                # Check if it has get_extended_schema property
                elif hasattr(tool_entry, "get_extended_schema"):
                    tool_schema = tool_entry.get_extended_schema

                    if tool_schema.get("type") == "function" and "function" in tool_schema:
                        # Already in correct format
                        converted_tools.append(tool_schema)
                    elif tool_schema.get("type") == "function":
                        # Response API format, need to wrap
                        converted_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool_schema.get("name", tool_entry.tool_name if hasattr(tool_entry, "tool_name") else tool_name),
                                "description": tool_schema.get("description", ""),
                                "parameters": tool_schema.get("parameters", {}),
                            }
                        })
        # Handle list format for backward compatibility
        elif isinstance(custom_tools, list):
            for tool in custom_tools:
                if hasattr(tool, "schema_def"):
                    tool_schema = tool.schema_def

                    if tool_schema.get("type") == "function" and "function" in tool_schema:
                        converted_tools.append(tool_schema)
                    elif tool_schema.get("type") == "function":
                        converted_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool_schema.get("name", tool.tool_name),
                                "description": tool_schema.get("description", ""),
                                "parameters": tool_schema.get("parameters", {}),
                            }
                        })
                elif hasattr(tool, "get_extended_schema"):
                    tool_schema = tool.get_extended_schema

                    if tool_schema.get("type") == "function" and "function" in tool_schema:
                        converted_tools.append(tool_schema)
                    elif tool_schema.get("type") == "function":
                        converted_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool_schema.get("name", tool.tool_name),
                                "description": tool_schema.get("description", ""),
                                "parameters": tool_schema.get("parameters", {}),
                            }
                        })

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
