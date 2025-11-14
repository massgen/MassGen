# -*- coding: utf-8 -*-
"""
Builtin Tool Translator.

Converts between NLIP messages and MassGen builtin tool format.
"""

from typing import Any, Dict

from ..schema import NLIPToolCall, NLIPToolResult
from .base import ProtocolTranslator


class BuiltinToolTranslator(ProtocolTranslator):
    """
    Translator for built-in MassGen tools (vote, new_answer, etc.).
    """

    async def nlip_to_native_call(
        self,
        nlip_call: NLIPToolCall,
    ) -> Dict[str, Any]:
        """
        Convert NLIP tool call to built-in tool format.
        """
        return {
            "tool_name": nlip_call.tool_name,
            "parameters": nlip_call.parameters,
            "options": {
                "require_confirmation": nlip_call.require_confirmation,
            },
        }

    async def native_to_nlip_result(
        self,
        tool_id: str,
        tool_name: str,
        native_result: Any,
    ) -> NLIPToolResult:
        """Convert built-in tool result to NLIP format."""
        return NLIPToolResult(
            tool_id=tool_id,
            tool_name=tool_name,
            status="success",
            result=native_result,
            metadata={
                "protocol": "builtin",
                "tool_category": "massgen_builtin",
            },
        )

    async def nlip_to_native_params(
        self,
        nlip_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Built-in tools use same parameter structure."""
        return nlip_params
