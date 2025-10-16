# -*- coding: utf-8 -*-
"""
Base classes for workflow toolkits.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List


class ToolType(Enum):
    """Types of tools available in the system."""

    BUILTIN = "builtin"
    WORKFLOW = "workflow"
    MCP = "mcp"


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
