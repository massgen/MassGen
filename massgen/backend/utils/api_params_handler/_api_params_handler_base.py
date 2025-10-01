# -*- coding: utf-8 -*-
"""
Base class for API parameters handlers.
Provides common functionality for building API parameters across different backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set

from ....toolkits import toolkit_registry


class APIParamsHandlerBase(ABC):
    """Abstract base class for API parameter handlers."""

    def __init__(self, backend_instance: Any):
        """Initialize the API params handler.

        Args:
            backend_instance: The backend instance containing necessary formatters and config
        """
        self.backend = backend_instance
        self.formatter = backend_instance.formatter

    @abstractmethod
    async def build_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build API parameters for the specific backend.

        Args:
            messages: List of messages in framework format
            tools: List of tools in framework format
            all_params: All parameters including config and runtime params

        Returns:
            Dictionary of API parameters ready for the backend
        """

    @abstractmethod
    def get_excluded_params(self) -> Set[str]:
        """Get backend-specific parameters to exclude from API calls."""

    @abstractmethod
    def get_api_format(self) -> str:
        """Get the API format for this handler (e.g., 'chat_completions', 'response', 'claude')."""

    def get_provider_tools(self, all_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get provider-specific tools based on parameters using the toolkit registry.

        Args:
            all_params: All parameters including config and runtime params.

        Returns:
            List of tool definitions from enabled toolkits.
        """
        provider = self.backend.get_provider_name()

        # Add API format to config for toolkit formatting
        config = dict(all_params)
        config["api_format"] = self.get_api_format()

        # Get tools from registry
        return toolkit_registry.get_provider_tools(provider, config)

    def get_base_excluded_params(self) -> Set[str]:
        """Get common parameters to exclude across all backends."""
        return {
            # Filesystem manager parameters (handled by base class)
            "cwd",
            "agent_temporary_workspace",
            "context_paths",
            "context_write_access_enabled",
            # Backend identification (handled by orchestrator)
            "type",
            "agent_id",
            "session_id",
            # MCP configuration (handled by base class for MCP backends)
            "mcp_servers",
        }

    def build_base_api_params(
        self,
        messages: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build base API parameters common to most backends."""
        api_params = {"stream": True}

        # Add filtered parameters
        excluded = self.get_excluded_params()
        for key, value in all_params.items():
            if key not in excluded and value is not None:
                api_params[key] = value

        return api_params

    def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Get MCP tools from backend if available."""
        if hasattr(self.backend, "_mcp_functions") and self.backend._mcp_functions:
            if hasattr(self.backend, "get_mcp_tools_formatted"):
                return self.backend.get_mcp_tools_formatted()
        return []
