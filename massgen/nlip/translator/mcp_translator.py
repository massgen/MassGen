"""
MCP Protocol Translator.

Converts between NLIP messages and MCP (Model Context Protocol) format.
"""

from typing import Dict, Any
from .base import ProtocolTranslator
from ..schema import NLIPToolCall, NLIPToolResult


class MCPTranslator(ProtocolTranslator):
    """
    Translator for MCP (Model Context Protocol) tools.
    Converts between NLIP and MCP message formats.
    """

    async def nlip_to_native_call(
        self,
        nlip_call: NLIPToolCall
    ) -> Dict[str, Any]:
        """
        Convert NLIP tool call to MCP format.

        MCP format:
        {
            "type": "tool_use",
            "id": "tool_id",
            "name": "tool_name",
            "input": {...}
        }
        """
        return {
            "type": "tool_use",
            "id": nlip_call.tool_id,
            "name": nlip_call.tool_name,
            "input": nlip_call.parameters,
            "parameters": nlip_call.parameters  # For compatibility
        }

    async def native_to_nlip_result(
        self,
        tool_id: str,
        tool_name: str,
        native_result: Any
    ) -> NLIPToolResult:
        """
        Convert MCP tool result to NLIP format.

        MCP result format:
        {
            "type": "tool_result",
            "tool_use_id": "...",
            "content": [...]
        }
        """
        # Extract content from MCP result
        if isinstance(native_result, dict):
            status = "success" if "error" not in native_result else "error"
            result_data = native_result.get("content") or native_result
            error = native_result.get("error")
        else:
            status = "success"
            result_data = native_result
            error = None

        return NLIPToolResult(
            tool_id=tool_id,
            tool_name=tool_name,
            status=status,
            result=result_data,
            error=error,
            metadata={
                "protocol": "mcp",
                "original_format": "mcp_tool_result"
            }
        )

    async def nlip_to_native_params(
        self,
        nlip_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """MCP uses same parameter structure as NLIP."""
        return nlip_params
