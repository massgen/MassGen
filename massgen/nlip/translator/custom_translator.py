"""
Custom Tool Translator.

Converts between NLIP messages and MassGen custom tool format.
"""

from typing import Dict, Any
from .base import ProtocolTranslator
from ..schema import NLIPToolCall, NLIPToolResult


class CustomToolTranslator(ProtocolTranslator):
    """
    Translator for custom MassGen tools.
    """

    async def nlip_to_native_call(
        self,
        nlip_call: NLIPToolCall
    ) -> Dict[str, Any]:
        """
        Convert NLIP tool call to custom tool format.

        Custom format matches MassGen's native format:
        {
            "function": {
                "name": "tool_name",
                "arguments": {...}
            }
        }
        """
        return {
            "function": {
                "name": nlip_call.tool_name,
                "arguments": nlip_call.parameters
            },
            "parameters": nlip_call.parameters,
            "options": {}
        }

    async def native_to_nlip_result(
        self,
        tool_id: str,
        tool_name: str,
        native_result: Any
    ) -> NLIPToolResult:
        """Convert custom tool result to NLIP format."""
        return NLIPToolResult(
            tool_id=tool_id,
            tool_name=tool_name,
            status="success",
            result=native_result,
            metadata={
                "protocol": "custom",
                "tool_type": "massgen_custom"
            }
        )

    async def nlip_to_native_params(
        self,
        nlip_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Custom tools use same parameter structure."""
        return nlip_params
