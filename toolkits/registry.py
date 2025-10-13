# -*- coding: utf-8 -*-
"""
Tool registration system for managing builtin, workflow, and MCP toolkits.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ToolType(Enum):
    """Types of tools available in the system."""

    BUILTIN = "builtin"  # Built-in tools (e.g., web_search, code_interpreter)
    WORKFLOW = "workflow"  # Workflow tools (e.g., vote, new_answer)
    MCP = "mcp"  # MCP protocol tools


class BaseToolkit(ABC):
    """Abstract base class for all toolkits."""

    @property
    @abstractmethod
    def toolkit_id(self) -> str:
        """Unique identifier for the toolkit."""

    @property
    @abstractmethod
    def toolkit_type(self) -> ToolType:
        """Type of the toolkit."""

    @abstractmethod
    def get_tools(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get tool definitions based on configuration.

        Args:
            config: Configuration dictionary containing parameters like
                   api_format, enable flags, etc.

        Returns:
            List of tool definitions in the appropriate format.
        """

    @abstractmethod
    def is_enabled(self, config: Dict[str, Any]) -> bool:
        """
        Check if the toolkit is enabled based on configuration.

        Args:
            config: Configuration dictionary.

        Returns:
            True if the toolkit is enabled, False otherwise.
        """


class ToolkitRegistry:
    """Central registry for managing toolkits and their provider associations."""

    def __init__(self):
        """Initialize the registry."""
        self._toolkits: Dict[str, BaseToolkit] = {}
        self._provider_toolkits: Dict[str, Set[str]] = {}  # provider -> toolkit_ids
        self._toolkit_providers: Dict[str, Set[str]] = {}  # toolkit_id -> providers

    def register(self, toolkit: BaseToolkit, providers: Optional[List[str]] = None) -> None:
        """
        Register a toolkit with optional provider associations.

        Args:
            toolkit: The toolkit instance to register.
            providers: Optional list of provider names that support this toolkit.
        """
        toolkit_id = toolkit.toolkit_id

        # If already registered, just add new provider support
        if toolkit_id in self._toolkits:
            if providers:
                for provider in providers:
                    self.add_provider_support(toolkit_id, provider)
            logger.debug(f"Toolkit {toolkit_id} already registered, updated provider support")
            return

        # Register new toolkit
        self._toolkits[toolkit_id] = toolkit
        self._toolkit_providers[toolkit_id] = set()
        logger.info(f"Registered toolkit: {toolkit_id} (type: {toolkit.toolkit_type.value})")

        # Add provider associations
        if providers:
            for provider in providers:
                self.add_provider_support(toolkit_id, provider)

    def unregister(self, toolkit_id: str) -> None:
        """
        Unregister a toolkit completely.

        Args:
            toolkit_id: ID of the toolkit to unregister.
        """
        if toolkit_id not in self._toolkits:
            logger.warning(f"Attempted to unregister non-existent toolkit: {toolkit_id}")
            return

        # Remove from all providers
        providers = list(self._toolkit_providers.get(toolkit_id, set()))
        for provider in providers:
            self.remove_provider_support(toolkit_id, provider)

        # Remove toolkit itself
        del self._toolkits[toolkit_id]
        del self._toolkit_providers[toolkit_id]
        logger.info(f"Unregistered toolkit: {toolkit_id}")

    def add_provider_support(self, toolkit_id: str, provider: str) -> None:
        """
        Add provider support for an existing toolkit.

        Args:
            toolkit_id: ID of the toolkit.
            provider: Name of the provider to add support for.
        """
        if toolkit_id not in self._toolkits:
            raise ValueError(f"Toolkit {toolkit_id} not registered")

        if provider not in self._provider_toolkits:
            self._provider_toolkits[provider] = set()

        self._provider_toolkits[provider].add(toolkit_id)
        self._toolkit_providers[toolkit_id].add(provider)
        logger.debug(f"Added {provider} support for toolkit {toolkit_id}")

    def remove_provider_support(self, toolkit_id: str, provider: str) -> None:
        """
        Remove provider support for a toolkit.

        Args:
            toolkit_id: ID of the toolkit.
            provider: Name of the provider to remove support for.
        """
        if provider in self._provider_toolkits:
            self._provider_toolkits[provider].discard(toolkit_id)

        if toolkit_id in self._toolkit_providers:
            self._toolkit_providers[toolkit_id].discard(provider)

        logger.debug(f"Removed {provider} support for toolkit {toolkit_id}")

    def is_registered(self, toolkit_id: str) -> bool:
        """
        Check if a toolkit is registered.

        Args:
            toolkit_id: ID of the toolkit to check.

        Returns:
            True if registered, False otherwise.
        """
        return toolkit_id in self._toolkits

    def get_toolkit(self, toolkit_id: str) -> Optional[BaseToolkit]:
        """
        Get a specific toolkit by ID.

        Args:
            toolkit_id: ID of the toolkit.

        Returns:
            The toolkit instance or None if not found.
        """
        return self._toolkits.get(toolkit_id)

    def get_provider_toolkits(self, provider: str) -> List[str]:
        """
        Get all toolkit IDs supported by a provider.

        Args:
            provider: Name of the provider.

        Returns:
            List of toolkit IDs.
        """
        return list(self._provider_toolkits.get(provider, set()))

    def get_toolkit_providers(self, toolkit_id: str) -> List[str]:
        """
        Get all providers that support a specific toolkit.

        Args:
            toolkit_id: ID of the toolkit.

        Returns:
            List of provider names.
        """
        return list(self._toolkit_providers.get(toolkit_id, set()))

    def get_provider_tools(self, provider: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get all enabled tools for a specific provider.

        Args:
            provider: Name of the provider.
            config: Configuration dictionary.

        Returns:
            List of tool definitions from all enabled toolkits.
        """
        tools = []

        # Get all toolkit IDs for this provider
        toolkit_ids = self.get_provider_toolkits(provider)

        for toolkit_id in toolkit_ids:
            toolkit = self._toolkits.get(toolkit_id)
            if toolkit and toolkit.is_enabled(config):
                try:
                    toolkit_tools = toolkit.get_tools(config)
                    tools.extend(toolkit_tools)
                    logger.debug(f"Added {len(toolkit_tools)} tools from toolkit {toolkit_id}")
                except Exception as e:
                    logger.error(f"Error getting tools from toolkit {toolkit_id}: {e}")

        return tools

    def list_all_toolkits(self) -> Dict[str, Dict[str, Any]]:
        """
        List all registered toolkits with their metadata.

        Returns:
            Dictionary mapping toolkit IDs to their metadata.
        """
        return {
            toolkit_id: {
                "type": toolkit.toolkit_type.value,
                "providers": self.get_toolkit_providers(toolkit_id),
            }
            for toolkit_id, toolkit in self._toolkits.items()
        }


# Global singleton instance
toolkit_registry = ToolkitRegistry()
