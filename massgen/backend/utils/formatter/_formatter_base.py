# -*- coding: utf-8 -*-
"""
Base class for API parameters handlers.
Provides common functionality for building API parameters across different backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class FormatterBase(ABC):
    """Abstract base class for API parameter handlers."""

    def __init__(self) -> None:
        """Initialize the API params handler.

        Args:
            backend_instance: The backend instance containing necessary formatters and config
        """
        return None

    @abstractmethod
    def format_messages(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def format_tools(
        self,
        tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def format_mcp_tools(
        self,
        mcp_functions: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        pass

    @staticmethod
    def extract_tool_name(tool_call: Dict[str, Any]) -> str:
        """
        Extract tool name from a tool call (handles multiple formats).

        Supports:
        - Chat Completions format: {"function": {"name": "...", ...}}
        - Response API format: {"name": "..."}
        - Claude native format: {"name": "..."}

        Args:
            tool_call: Tool call data structure from any backend

        Returns:
            Tool name string
        """
        # Chat Completions format
        if "function" in tool_call:
            return tool_call.get("function", {}).get("name", "unknown")
        # Response API / Claude native format
        elif "name" in tool_call:
            return tool_call.get("name", "unknown")
        # Fallback
        return "unknown"

    @staticmethod
    def extract_tool_arguments(tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract tool arguments from a tool call (handles multiple formats).

        Supports:
        - Chat Completions format: {"function": {"arguments": ...}}
        - Response API format: {"arguments": ...}
        - Claude native format: {"input": ...}

        Args:
            tool_call: Tool call data structure from any backend

        Returns:
            Tool arguments dictionary (parsed from JSON string if needed)
        """
        import json

        # Chat Completions format
        if "function" in tool_call:
            args = tool_call.get("function", {}).get("arguments", {})
        # Claude native format
        elif "input" in tool_call:
            args = tool_call.get("input", {})
        # Response API format
        elif "arguments" in tool_call:
            args = tool_call.get("arguments", {})
        else:
            args = {}

        # Parse JSON string if needed
        if isinstance(args, str):
            try:
                return json.loads(args) if args.strip() else {}
            except (json.JSONDecodeError, ValueError):
                return {}
        return args if isinstance(args, dict) else {}

    @staticmethod
    def extract_tool_call_id(tool_call: Dict[str, Any]) -> str:
        """
        Extract tool call ID from a tool call (handles multiple formats).

        Supports:
        - Chat Completions format: {"id": "..."}
        - Response API format: {"call_id": "..."}
        - Claude native format: {"id": "..."}

        Args:
            tool_call: Tool call data structure from any backend

        Returns:
            Tool call ID string
        """
        # Try multiple possible ID fields
        return tool_call.get("id") or tool_call.get("call_id") or ""

    @staticmethod
    def _serialize_tool_arguments(arguments) -> str:
        """Safely serialize tool call arguments to JSON string.

        Args:
            arguments: Tool arguments (can be string, dict, or other types)

        Returns:
            JSON string representation of arguments
        """
        import json

        if isinstance(arguments, str):
            # If already a string, validate it's valid JSON
            try:
                json.loads(arguments)  # Validate JSON
                return arguments
            except (json.JSONDecodeError, ValueError):
                # If not valid JSON, treat as plain string and wrap in quotes
                return json.dumps(arguments)
        elif arguments is None:
            return "{}"
        else:
            # Convert to JSON string
            try:
                return json.dumps(arguments)
            except (TypeError, ValueError) as e:
                # Logger not imported at module level, use print for warning
                print(f"Warning: Failed to serialize tool arguments: {e}, arguments: {arguments}")
                return "{}"
