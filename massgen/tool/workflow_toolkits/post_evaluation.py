# -*- coding: utf-8 -*-
"""
Post-evaluation toolkit for MassGen orchestration restart feature.

This toolkit provides tools for post-evaluation phase where the winning agent
evaluates its own answer and decides whether to submit or restart with improvements.
"""

from typing import Any, Dict, List, Optional

from .base import BaseToolkit, ToolType


class PostEvaluationToolkit(BaseToolkit):
    """Post-evaluation toolkit for orchestration restart feature."""

    def __init__(self, template_overrides: Optional[Dict[str, Any]] = None):
        """
        Initialize the PostEvaluation toolkit.

        Args:
            template_overrides: Optional template overrides for customization
        """
        self._template_overrides = template_overrides or {}

    @property
    def toolkit_id(self) -> str:
        """Unique identifier for post-evaluation toolkit."""
        return "post_evaluation"

    @property
    def toolkit_type(self) -> ToolType:
        """Type of this toolkit."""
        return ToolType.WORKFLOW

    def is_enabled(self, config: Dict[str, Any]) -> bool:
        """
        Check if post-evaluation is enabled in configuration.

        Args:
            config: Configuration dictionary.

        Returns:
            True if post-evaluation tools are enabled.
        """
        return config.get("enable_post_evaluation_tools", True)

    def get_tools(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get post-evaluation tool definitions based on API format.

        Args:
            config: Configuration including api_format.

        Returns:
            List containing submit and restart_orchestration tool definitions.
        """
        api_format = config.get("api_format", "chat_completions")

        if api_format == "claude":
            # Claude native format
            return self._get_claude_tools()
        elif api_format == "response":
            # Response API format
            return self._get_response_tools()
        else:
            # Default Chat Completions format
            return self._get_chat_completions_tools()

    def _get_claude_tools(self) -> List[Dict[str, Any]]:
        """Get Claude native format tools."""
        submit_tool = {
            "name": "submit",
            "description": "Confirm that the final answer fully addresses the original task and submit it to the user. Use this when the answer is complete, accurate, and satisfactory.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "confirmed": {
                        "type": "boolean",
                        "description": "Set to true to confirm the answer is satisfactory",
                        "enum": [True],
                    },
                },
                "required": ["confirmed"],
            },
        }

        restart_tool = {
            "name": "restart_orchestration",
            "description": "Restart the orchestration process with specific guidance for improvement. Use this when the answer is incomplete, incorrect, or does not fully address the original task.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Clear explanation of why the answer is insufficient (e.g., 'The task required descriptions of two Beatles, but only John Lennon was described')",
                    },
                    "instructions": {
                        "type": "string",
                        "description": (
                            "Detailed, actionable guidance for agents on the next attempt "
                            "(e.g., 'Provide two descriptions (John Lennon AND Paul McCartney). "
                            "Each should include: birth year, role in band, notable songs, impact on music. "
                            "Use 4-6 sentences per person.')"
                        ),
                    },
                },
                "required": ["reason", "instructions"],
            },
        }

        return [submit_tool, restart_tool]

    def _get_response_tools(self) -> List[Dict[str, Any]]:
        """Get Response API format tools."""
        submit_tool = {
            "type": "function",
            "function": {
                "name": "submit",
                "description": "Confirm that the final answer fully addresses the original task and submit it to the user. Use this when the answer is complete, accurate, and satisfactory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirmed": {
                            "type": "boolean",
                            "description": "Set to true to confirm the answer is satisfactory",
                            "enum": [True],
                        },
                    },
                    "required": ["confirmed"],
                },
            },
        }

        restart_tool = {
            "type": "function",
            "function": {
                "name": "restart_orchestration",
                "description": (
                    "Restart the orchestration process with specific guidance for improvement. " "Use this when the answer is incomplete, incorrect, or does not fully address the original task."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Clear explanation of why the answer is insufficient (e.g., 'The task required descriptions of two Beatles, but only John Lennon was described')",
                        },
                        "instructions": {
                            "type": "string",
                            "description": (
                                "Detailed, actionable guidance for agents on the next attempt "
                                "(e.g., 'Provide two descriptions (John Lennon AND Paul McCartney). "
                                "Each should include: birth year, role in band, notable songs, impact on music. "
                                "Use 4-6 sentences per person.')"
                            ),
                        },
                    },
                    "required": ["reason", "instructions"],
                },
            },
        }

        return [submit_tool, restart_tool]

    def _get_chat_completions_tools(self) -> List[Dict[str, Any]]:
        """Get Chat Completions format tools."""
        submit_tool = {
            "type": "function",
            "function": {
                "name": "submit",
                "description": "Confirm that the final answer fully addresses the original task and submit it to the user. Use this when the answer is complete, accurate, and satisfactory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirmed": {
                            "type": "boolean",
                            "description": "Set to true to confirm the answer is satisfactory",
                            "enum": [True],
                        },
                    },
                    "required": ["confirmed"],
                },
            },
        }

        restart_tool = {
            "type": "function",
            "function": {
                "name": "restart_orchestration",
                "description": (
                    "Restart the orchestration process with specific guidance for improvement. " "Use this when the answer is incomplete, incorrect, or does not fully address the original task."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Clear explanation of why the answer is insufficient (e.g., 'The task required descriptions of two Beatles, but only John Lennon was described')",
                        },
                        "instructions": {
                            "type": "string",
                            "description": (
                                "Detailed, actionable guidance for agents on the next attempt "
                                "(e.g., 'Provide two descriptions (John Lennon AND Paul McCartney). "
                                "Each should include: birth year, role in band, notable songs, impact on music. "
                                "Use 4-6 sentences per person.')"
                            ),
                        },
                    },
                    "required": ["reason", "instructions"],
                },
            },
        }

        return [submit_tool, restart_tool]
