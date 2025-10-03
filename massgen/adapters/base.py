# -*- coding: utf-8 -*-
"""
Base adapter class for external agent frameworks.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from massgen.backend.base import StreamChunk


class AgentAdapter(ABC):
    """
    Abstract base class for external agent adapters.

    Adapters handle:
    - Message format conversion between MassGen and external frameworks
    - Tool/function conversion and mapping
    - Streaming simulation for non-streaming frameworks
    - State management for stateful frameworks
    """

    def __init__(self, **kwargs):
        """Initialize adapter with framework-specific configuration."""
        self.config = kwargs
        self._conversation_history = []

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
        1. Convert MassGen messages to framework format
        2. Convert MassGen tools to framework format
        3. Call the framework's agent
        4. Convert response back to MassGen format
        5. Simulate streaming if framework doesn't support it

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
        Simulate streaming for frameworks that don't support it natively.

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

    def convert_messages_from_massgen(
        self,
        messages: List[Dict[str, Any]],
    ) -> Any:
        """
        Convert MassGen messages to agent-specific format.

        Override this method for agent-specific conversion.

        Args:
            messages: MassGen format messages

        Returns:
            Agent-specific message format
        """
        return messages

    def convert_tools_from_massgen(
        self,
        tools: List[Dict[str, Any]],
    ) -> Any:
        """
        Convert MassGen tools to agent-specific format.

        Override this method for agent-specific conversion.

        Args:
            tools: MassGen format tools

        Returns:
            Agent-specific tool format
        """
        return tools

    def convert_response_to_massgen(
        self,
        response: Any,
    ) -> Dict[str, Any]:
        """
        Convert framework response to MassGen format.

        Override this method for framework-specific conversion.

        Args:
            response: Framework-specific response

        Returns:
            MassGen format response with content and optional tool_calls
        """
        return {
            "content": str(response),
            "tool_calls": None,
        }

    def is_stateful(self) -> bool:
        """
        Check if this adapter maintains conversation state.

        Override if your framework is stateless.
        """
        return False
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation_history.clear()

    def reset_state(self) -> None:
        """Reset adapter state."""
        self.clear_history()
        # Override to add framework-specific reset logic
