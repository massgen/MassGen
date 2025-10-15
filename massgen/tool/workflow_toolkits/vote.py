# -*- coding: utf-8 -*-
"""
Vote toolkit for MassGen workflow coordination.
"""

from typing import Any, Dict, List, Optional

from .base import BaseToolkit, ToolType


class VoteToolkit(BaseToolkit):
    """Vote toolkit for agent coordination workflows."""

    def __init__(self, valid_agent_ids: Optional[List[str]] = None, template_overrides: Optional[Dict[str, Any]] = None):
        """
        Initialize the Vote toolkit.

        Args:
            valid_agent_ids: List of valid agent IDs for voting
            template_overrides: Optional template overrides for customization
        """
        self.valid_agent_ids = valid_agent_ids
        self._template_overrides = template_overrides or {}

    @property
    def toolkit_id(self) -> str:
        """Unique identifier for vote toolkit."""
        return "vote"

    @property
    def toolkit_type(self) -> ToolType:
        """Type of this toolkit."""
        return ToolType.WORKFLOW

    def is_enabled(self, config: Dict[str, Any]) -> bool:
        """
        Check if vote is enabled in configuration.

        Args:
            config: Configuration dictionary.

        Returns:
            True if workflow tools are enabled or not explicitly disabled.
        """
        # Enable by default for workflow, unless explicitly disabled
        return config.get("enable_workflow_tools", True)

    def set_valid_agent_ids(self, agent_ids: List[str]):
        """
        Update the valid agent IDs for voting.

        Args:
            agent_ids: List of valid agent IDs
        """
        self.valid_agent_ids = agent_ids

    def get_tools(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get vote tool definition based on API format.

        Args:
            config: Configuration including api_format and potentially valid_agent_ids.

        Returns:
            List containing the vote tool definition.
        """
        # Check for template override
        if "vote_tool" in self._template_overrides:
            override = self._template_overrides["vote_tool"]
            if callable(override):
                return [override(self.valid_agent_ids)]
            return [override]

        # Get valid agent IDs from config if not set
        valid_ids = config.get("valid_agent_ids", self.valid_agent_ids)

        api_format = config.get("api_format", "chat_completions")

        if api_format == "claude":
            # Claude native format
            tool_def = {
                "name": "vote",
                "description": "Vote for the best agent to present final answer",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Anonymous agent ID to vote for (e.g., 'agent1', 'agent2')",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief reason why this agent has the best answer",
                        },
                    },
                    "required": ["agent_id", "reason"],
                },
            }

            # Add enum constraint for valid agent IDs
            if valid_ids:
                anon_agent_ids = [f"agent{i}" for i in range(1, len(valid_ids) + 1)]
                tool_def["input_schema"]["properties"]["agent_id"]["enum"] = anon_agent_ids

            return [tool_def]

        elif api_format == "response":
            # Response API format
            tool_def = {
                "type": "function",
                "function": {
                    "name": "vote",
                    "description": "Vote for the best agent to present final answer",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent_id": {
                                "type": "string",
                                "description": "Anonymous agent ID to vote for (e.g., 'agent1', 'agent2')",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Brief reason why this agent has the best answer",
                            },
                        },
                        "required": ["agent_id", "reason"],
                    },
                },
            }

            # Add enum constraint for valid agent IDs
            if valid_ids:
                anon_agent_ids = [f"agent{i}" for i in range(1, len(valid_ids) + 1)]
                tool_def["function"]["parameters"]["properties"]["agent_id"]["enum"] = anon_agent_ids

            return [tool_def]

        else:
            # Default Chat Completions format
            tool_def = {
                "type": "function",
                "function": {
                    "name": "vote",
                    "description": "Vote for the best agent to present final answer",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent_id": {
                                "type": "string",
                                "description": "Anonymous agent ID to vote for (e.g., 'agent1', 'agent2')",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Brief reason why this agent has the best answer",
                            },
                        },
                        "required": ["agent_id", "reason"],
                    },
                },
            }

            # Add enum constraint for valid agent IDs
            if valid_ids:
                anon_agent_ids = [f"agent{i}" for i in range(1, len(valid_ids) + 1)]
                tool_def["function"]["parameters"]["properties"]["agent_id"]["enum"] = anon_agent_ids

            return [tool_def]