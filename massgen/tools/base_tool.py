# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    """Base class for all tools"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name for OpenRouter function calling"""

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for OpenRouter"""

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """OpenRouter function parameters schema"""

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute the tool with given parameters"""
