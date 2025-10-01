# -*- coding: utf-8 -*-
"""
Toolkit manager providing high-level operations for toolkit management.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, List, Optional, Type

from .registry import BaseToolkit, toolkit_registry

logger = logging.getLogger(__name__)


class ToolkitManager:
    """Manager class for toolkit operations."""

    @staticmethod
    def register_custom_toolkit(toolkit: BaseToolkit, providers: Optional[List[str]] = None) -> None:
        """
        Register a custom toolkit dynamically.

        Args:
            toolkit: The toolkit instance to register.
            providers: Optional list of providers that support this toolkit.
        """
        toolkit_registry.register(toolkit, providers)
        logger.info(f"Registered custom toolkit: {toolkit.toolkit_id}")

    @staticmethod
    def register_from_config(toolkit_config: Dict[str, Any], default_provider: Optional[str] = None) -> None:
        """
        Register a toolkit from configuration.

        Args:
            toolkit_config: Configuration dictionary with 'class' and optional 'params'.
            default_provider: Default provider to associate with the toolkit.
        """
        toolkit_class_path = toolkit_config.get("class")
        if not toolkit_class_path:
            logger.error("Toolkit configuration missing 'class' field")
            return

        try:
            # Dynamic import and instantiation
            module_path, class_name = toolkit_class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            toolkit_cls: Type[BaseToolkit] = getattr(module, class_name)

            # Instantiate with parameters
            params = toolkit_config.get("params", {})
            toolkit = toolkit_cls(**params)

            # Register with providers
            providers = toolkit_config.get("providers", [])
            if default_provider and default_provider not in providers:
                providers.append(default_provider)

            toolkit_registry.register(toolkit, providers if providers else None)
            logger.info(f"Registered toolkit from config: {toolkit.toolkit_id}")

        except Exception as e:
            logger.error(f"Failed to register toolkit from config: {e}")

    @staticmethod
    def unregister_toolkit(toolkit_id: str) -> None:
        """
        Unregister a toolkit.

        Args:
            toolkit_id: ID of the toolkit to unregister.
        """
        toolkit_registry.unregister(toolkit_id)

    @staticmethod
    def list_toolkits(provider: Optional[str] = None) -> List[str]:
        """
        List registered toolkits.

        Args:
            provider: Optional provider to filter toolkits by.

        Returns:
            List of toolkit IDs.
        """
        if provider:
            return toolkit_registry.get_provider_toolkits(provider)
        return list(toolkit_registry.list_all_toolkits().keys())

    @staticmethod
    def get_toolkit(toolkit_id: str) -> Optional[BaseToolkit]:
        """
        Get a specific toolkit.

        Args:
            toolkit_id: ID of the toolkit.

        Returns:
            The toolkit instance or None if not found.
        """
        return toolkit_registry.get_toolkit(toolkit_id)

    @staticmethod
    def get_toolkit_info(toolkit_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a toolkit.

        Args:
            toolkit_id: ID of the toolkit.

        Returns:
            Dictionary with toolkit information or None if not found.
        """
        toolkit = toolkit_registry.get_toolkit(toolkit_id)
        if not toolkit:
            return None

        return {
            "id": toolkit.toolkit_id,
            "type": toolkit.toolkit_type.value,
            "providers": toolkit_registry.get_toolkit_providers(toolkit_id),
        }

    @staticmethod
    def get_provider_tools(provider: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get all tools for a provider based on configuration.

        Args:
            provider: Name of the provider.
            config: Configuration dictionary.

        Returns:
            List of tool definitions.
        """
        return toolkit_registry.get_provider_tools(provider, config)
