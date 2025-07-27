"""
ChatAgent Interface - Issue #17: Implement ChatAgent Interface

This module implements the unified ChatAgent interface as the foundation 
for all agent interactions with async streaming support.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, AsyncGenerator
from dataclasses import dataclass
import uuid
import time


@dataclass
class StreamChunk:
    """Standardized chunk format for streaming responses."""
    type: str  # "content", "tool_calls", "complete_message", "done", "error", "agent_status"
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    complete_message: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    source: Optional[str] = None  # agent_id or "orchestrator"
    status: Optional[str] = None
    timestamp: Optional[float] = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = time.time()


class ChatAgent(ABC):
    """Abstract base class defining the unified chat interface."""
    
    def __init__(self, session_id: Optional[str] = None):
        """
        Initialize the ChatAgent with session management.
        
        Args:
            session_id: Optional session ID for conversation tracking
        """
        self.session_id = session_id or f"chat_session_{uuid.uuid4().hex[:8]}"
        self.conversation_history: List[Dict[str, Any]] = []
    
    @abstractmethod
    async def chat(self, 
                   messages: List[Dict[str, Any]], 
                   tools: Optional[List[Dict[str, Any]]] = None, 
                   reset_chat: bool = False, 
                   clear_history: bool = False) -> AsyncGenerator[StreamChunk, None]:
        """
        Enhanced chat interface supporting tool calls and streaming.
        
        Args:
            messages: List of conversation messages in OpenAI format
            tools: Optional list of tools available to the agent
            reset_chat: If True, replace conversation history with provided messages
            clear_history: If True, clear conversation history before processing
            
        Yields:
            StreamChunk: Standardized streaming response chunks
        """
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        Get current agent status and state.
        
        Returns:
            Dict containing agent status information
        """
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """Reset agent state for new conversation."""
        pass
    
    # Conversation management utilities
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """
        Get a copy of the conversation history.
        
        Returns:
            List of conversation messages
        """
        return self.conversation_history.copy()
    
    def add_to_history(self, role: str, content: str, **kwargs) -> None:
        """
        Add a message to conversation history.
        
        Args:
            role: Message role (user, assistant, system, etc.)
            content: Message content
            **kwargs: Additional message fields
        """
        message = {"role": role, "content": content}
        message.update(kwargs)
        self.conversation_history.append(message)
    
    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.conversation_history = []
    
    def get_session_info(self) -> Dict[str, Any]:
        """
        Get session information.
        
        Returns:
            Dict containing session details
        """
        return {
            "session_id": self.session_id,
            "conversation_length": len(self.conversation_history),
            "created_at": getattr(self, 'created_at', None)
        }