# -*- coding: utf-8 -*-
"""
New Answer toolkit for MassGen workflow coordination.
"""

from typing import Any, Dict, List, Optional

from ..registry import BaseToolkit, ToolType


class NewAnswerToolkit(BaseToolkit):
    """New Answer toolkit for agent coordination workflows."""

    def __init__(self, template_overrides: Optional[Dict[str, Any]] = None):
        """
        Initialize the New Answer toolkit.

        Args:
            template_overrides: Optional template overrides for customization
        """
        self._template_overrides = template_overrides or {}

    @property
    def toolkit_id(self) -> str:
        """Unique identifier for new answer toolkit."""
        return "new_answer"

    @property
    def toolkit_type(self) -> ToolType:
        """Type of this toolkit."""
        return ToolType.WORKFLOW

    def is_enabled(self, config: Dict[str, Any]) -> bool:
        """
        Check if new answer is enabled in configuration.

        Args:
            config: Configuration dictionary.

        Returns:
            True if workflow tools are enabled or not explicitly disabled.
        """
        # Enable by default for workflow, unless explicitly disabled
        return config.get("enable_workflow_tools", True)

    def get_tools(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get new answer tool definition based on API format.

        Args:
            config: Configuration including api_format.

        Returns:
            List containing the new answer tool definition.
        """
        # Check for template override
        if "new_answer_tool" in self._template_overrides:
            override = self._template_overrides["new_answer_tool"]
            if callable(override):
                return [override()]
            return [override]

        api_format = config.get("api_format", "chat_completions")

        if api_format == "claude":
            # Claude native format
            return [
                {
                    "name": "new_answer",
                    "description": "Submit a new and improved answer",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Your improved answer. If any builtin tools like search or code execution were used, mention how they are used here.",
                            },
                        },
                        "required": ["content"],
                    },
                },
            ]

        elif api_format == "response":
            # Response API format (OpenAI-style but simpler)
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "new_answer",
                        "description": "Submit a new and improved answer",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "Your improved answer. If any builtin tools like search or code execution were used, mention how they are used here.",
                                },
                            },
                            "required": ["content"],
                        },
                    },
                },
            ]

        else:
            # Default Chat Completions format
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "new_answer",
                        "description": "Submit a new and improved answer",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "Your improved answer. If any builtin tools like search or code execution were used, mention how they are used here.",
                                },
                            },
                            "required": ["content"],
                        },
                    },
                },
            ]
