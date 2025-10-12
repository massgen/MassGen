# -*- coding: utf-8 -*-
"""
Base adapter class for external agent agents.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from massgen.backend.base import StreamChunk
from massgen.utils import CoordinationStage


class AgentAdapter(ABC):
    """
    Abstract base class for external agent adapters.

    Adapters handle:
    - Message format conversion between MassGen and external agents
    - Tool/function conversion and mapping
    - Streaming simulation for non-streaming agents
    - State management for stateful agents
    """

    def __init__(self, **kwargs):
        """Initialize adapter with agent-specific configuration."""
        self.config = kwargs
        self._conversation_history = []
        self.coordination_stage = None

    @abstractmethod
    async def execute_streaming(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream response with tool support.

        This method must:
        1. Convert MassGen messages to agent format
        2. Convert MassGen tools to agent format
        3. Call the agent
        4. Convert response back to MassGen format
        5. Simulate streaming if agent doesn't support it

        Args:
            messages: MassGen format messages
            tools: MassGen format tools
            **kwargs: Additional parameters

        Yields:
            StreamChunk: Standardized response chunks

        """

    async def simulate_streaming(
        self,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        delay: float = 0.01,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Simulate streaming for agents that don't support it natively.

        Args:
            content: Complete response content
            tool_calls: Tool calls to include
            delay: Delay between chunks (seconds)

        Yields:
            StreamChunk: Simulated streaming chunks
        """
        # Stream content in chunks
        if content:
            words = content.split()
            for i, word in enumerate(words):
                chunk_text = word + (" " if i < len(words) - 1 else "")
                yield StreamChunk(type="content", content=chunk_text)
                await asyncio.sleep(delay)

        # Send tool calls if any
        if tool_calls:
            yield StreamChunk(type="tool_calls", tool_calls=tool_calls)

        # Send completion signals
        complete_message = {
            "role": "assistant",
            "content": content or "",
        }
        if tool_calls:
            complete_message["tool_calls"] = tool_calls

        yield StreamChunk(type="complete_message", complete_message=complete_message)
        yield StreamChunk(type="done")

    @staticmethod
    def _get_tool_name(tool: Dict[str, Any]) -> str:
        """
        Extract tool name from tool schema.

        Supports both formats:
        - {"type": "function", "function": {"name": "tool_name", ...}}
        - {"name": "tool_name", ...}
        """
        if "function" in tool:
            return tool["function"].get("name", "")
        return tool.get("name", "")

    def convert_messages_from_massgen(
        self,
        messages: List[Dict[str, Any]],
    ) -> Any:
        """
        Convert MassGen messages to agent-specific format.

        Override this method for agent-specific conversion.

        Args:
            messages: List of MassGen format messages

        Returns:
            agent-specific message format
        """
        return messages

    def convert_response_to_massgen(
        self,
        response: Any,
    ) -> Dict[str, Any]:
        """
        Convert agent response to MassGen format.

        Override this method for agent-specific conversion.

        Args:
            response: agent-specific response

        Returns:
            MassGen format response with content and optional tool_calls
        """
        return {
            "content": str(response),
            "tool_calls": None,
        }

    def convert_tools_from_massgen(
        self,
        tools: List[Dict[str, Any]],
    ) -> Any:
        """
        Convert MassGen tools to agent-specific format.

        Override this method for agent-specific conversion.

        Args:
            tools: List of MassGen format tools

        Returns:
            agent-specific tool format
        """
        return tools

    def is_stateful(self) -> bool:
        """
        Check if this adapter maintains conversation state.

        Override if your agent is stateless.
        """
        return False

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation_history.clear()

    def reset_state(self) -> None:
        """Reset adapter state."""
        self.clear_history()
        # Override to add agent-specific reset logic

    def set_stage(self, stage: CoordinationStage) -> None:
        """Set the coordination stage for the adapter, if applicable."""
        self.coordination_stage = stage
