"""
Common utilities and classes shared across backend implementations.
"""
from __future__ import annotations

from typing import Dict, Any, Callable


class Function:
    """Function wrapper for MCP tools that can be called by OpenAI-compatible APIs."""

    def __init__(self, name: str, description: str, parameters: Dict[str, Any], entrypoint: Callable[[str], Any]) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.entrypoint = entrypoint

    async def call(self, input_str: str) -> Any:
        """Call the function with input string."""
        return await self.entrypoint(input_str)

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert function to OpenAI tool format."""
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
