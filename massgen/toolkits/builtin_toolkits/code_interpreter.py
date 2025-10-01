# -*- coding: utf-8 -*-
"""
Code interpreter toolkit for executing code.
"""

from typing import Any, Dict, List

from ..registry import BaseToolkit, ToolType


class CodeInterpreterToolkit(BaseToolkit):
    """Code interpreter toolkit implementation."""

    @property
    def toolkit_id(self) -> str:
        """Unique identifier for code interpreter toolkit."""
        return "code_interpreter"

    @property
    def toolkit_type(self) -> ToolType:
        """Type of this toolkit."""
        return ToolType.BUILTIN

    def is_enabled(self, config: Dict[str, Any]) -> bool:
        """
        Check if code interpreter is enabled in configuration.

        Args:
            config: Configuration dictionary.

        Returns:
            True if enable_code_interpreter is set to True.
        """
        return config.get("enable_code_interpreter", False)

    def get_tools(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get code interpreter tool definition based on API format.

        Args:
            config: Configuration including api_format.

        Returns:
            List containing the code interpreter tool definition.
        """
        api_format = config.get("api_format", "chat_completions")

        # Both Response API and Chat Completions use the same format for code_interpreter
        if api_format in ["response", "chat_completions"]:
            return [
                {
                    "type": "code_interpreter",
                    "container": {"type": "auto"},
                },
            ]

        elif api_format == "claude":
            # Claude might use a different format or not support it directly
            # Return empty for now as Claude typically uses MCP for code execution
            return []

        else:
            # Default format
            return [
                {
                    "type": "code_interpreter",
                    "container": {"type": "auto"},
                },
            ]
