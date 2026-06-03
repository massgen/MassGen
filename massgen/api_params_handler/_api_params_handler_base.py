"""
Base class for API parameters handlers.
Provides common functionality for building API parameters across different backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..backend._excluded_params import BASE_EXCLUDED_CONFIG_PARAMS


class APIParamsHandlerBase(ABC):
    """Abstract base class for API parameter handlers."""

    def __init__(self, backend_instance: Any):
        """Initialize the API params handler.

        Args:
            backend_instance: The backend instance containing necessary formatters and config
        """
        self.backend = backend_instance
        self.formatter = backend_instance.formatter
        self.custom_tool_manager = backend_instance.custom_tool_manager

    @abstractmethod
    async def build_api_params(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        all_params: dict[str, Any],
    ) -> dict[str, Any]:
        """Build API parameters for the specific backend.

        Args:
            messages: List of messages in framework format
            tools: List of tools in framework format
            all_params: All parameters including config and runtime params

        Returns:
            Dictionary of API parameters ready for the backend
        """

    @abstractmethod
    def get_excluded_params(self) -> set[str]:
        """Get backend-specific parameters to exclude from API calls."""

    @abstractmethod
    def get_provider_tools(self, all_params: dict[str, Any]) -> list[dict[str, Any]]:
        """Get provider-specific tools based on parameters."""

    def get_base_excluded_params(self) -> set[str]:
        """Get common parameters to exclude across all backends."""
        # Single source of truth (see backend._excluded_params); apih also
        # excludes upload_files (handled before the provider call).
        return set(BASE_EXCLUDED_CONFIG_PARAMS) | {"upload_files"}

    def build_base_api_params(
        self,
        messages: list[dict[str, Any]],
        all_params: dict[str, Any],
    ) -> dict[str, Any]:
        """Build base API parameters common to most backends."""
        api_params = {"stream": True}

        # Add filtered parameters
        excluded = self.get_excluded_params()
        for key, value in all_params.items():
            if key not in excluded and value is not None:
                api_params[key] = value

        return api_params

    def get_mcp_tools(self) -> list[dict[str, Any]]:
        """Get MCP tools from backend if available."""
        if hasattr(self.backend, "_mcp_functions") and self.backend._mcp_functions:
            if hasattr(self.backend, "get_mcp_tools_formatted"):
                return self.backend.get_mcp_tools_formatted()
        return []

    def get_custom_tools(self) -> list[dict[str, Any]]:
        """Get custom tools, preferring backend-provided full schemas when available.

        Backends that inherit CustomToolAndMCPBackend expose
        `_get_custom_tools_schemas()`, which includes internal background lifecycle
        management tools in addition to user custom tools. Falling back to
        `custom_tool_manager.registered_tools` keeps compatibility for handlers
        instantiated with mocked backends in tests.
        """
        if hasattr(self.backend, "_get_custom_tools_schemas"):
            try:
                custom_schemas = self.backend._get_custom_tools_schemas()
            except Exception:  # noqa: BLE001
                custom_schemas = []
            if not isinstance(custom_schemas, list):
                custom_schemas = []

            if custom_schemas:
                normalized_schemas: list[dict[str, Any]] = []
                for schema in custom_schemas:
                    if schema.get("type") == "function" and "function" in schema:
                        function_block = dict(schema.get("function", {}))
                        function_block.setdefault("description", "")
                        normalized_schema = dict(schema)
                        normalized_schema["function"] = function_block
                        normalized_schemas.append(normalized_schema)
                    else:
                        normalized_schemas.append(schema)

                if hasattr(self.formatter, "format_tools"):
                    return self.formatter.format_tools(normalized_schemas)
                return normalized_schemas

        custom_tools = getattr(self.custom_tool_manager, "registered_tools", None)
        if custom_tools:
            return self.formatter.format_custom_tools(custom_tools)

        return []
