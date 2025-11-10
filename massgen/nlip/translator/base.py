"""
Base Protocol Translator Interface.

Defines the abstract interface that all protocol translators must implement
for converting between NLIP messages and native tool formats.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from ..schema import NLIPToolCall, NLIPToolResult


class ProtocolTranslator(ABC):
    """
    Base class for protocol translators.
    Converts between NLIP messages and native tool protocols.
    """

    @abstractmethod
    async def nlip_to_native_call(
        self,
        nlip_call: NLIPToolCall
    ) -> Dict[str, Any]:
        """
        Translate NLIP tool call to native tool format.

        Args:
            nlip_call: NLIP tool call

        Returns:
            Native tool call format
        """
        pass

    @abstractmethod
    async def native_to_nlip_result(
        self,
        tool_id: str,
        tool_name: str,
        native_result: Any
    ) -> NLIPToolResult:
        """
        Translate native tool result to NLIP format.

        Args:
            tool_id: Tool invocation ID
            tool_name: Name of the tool
            native_result: Result from native tool execution

        Returns:
            NLIP tool result
        """
        pass

    @abstractmethod
    async def nlip_to_native_params(
        self,
        nlip_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Translate NLIP parameters to native format.

        Args:
            nlip_params: Parameters in NLIP format

        Returns:
            Parameters in native format
        """
        pass
