"""
Base classes for backend implementations.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, AsyncGenerator
from dataclasses import dataclass
import time
from ..chat_agent import StreamChunk


@dataclass
class TokenUsage:
    """Token usage and cost tracking."""
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    model: Optional[str] = None
    provider: Optional[str] = None
    timestamp: Optional[float] = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = time.time()
    
    def add_usage(self, input_tokens: int, output_tokens: int, cost: float = 0.0) -> None:
        """Add token usage to the current totals."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.estimated_cost += cost
    
    def get_total_tokens(self) -> int:
        """Get total tokens used."""
        return self.input_tokens + self.output_tokens


class AgentBackend(ABC):
    """Abstract base class for agent LLM providers."""
    
    def __init__(self, **kwargs):
        """
        Initialize the AgentBackend.
        
        Args:
            **kwargs: Configuration parameters including api_key, model, etc.
        """
        self.config = kwargs
        self.token_usage = TokenUsage()
    
    @abstractmethod
    async def stream_with_tools(self, 
                               messages: List[Dict[str, Any]], 
                               tools: Optional[List[Dict[str, Any]]] = None, 
                               **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream response with tool calling support.
        
        Args:
            messages: List of conversation messages
            tools: Optional list of tools available to the agent
            **kwargs: Additional parameters for the specific backend
            
        Yields:
            StreamChunk: Standardized streaming response chunks
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get provider name.
        
        Returns:
            str: Name of the provider (e.g., "anthropic", "google", "openai", "xai")
        """
        pass
    
    @abstractmethod
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """
        Calculate cost for token usage.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name used
            
        Returns:
            float: Estimated cost in USD
        """
        pass
    
    def get_token_usage(self) -> TokenUsage:
        """
        Get current token usage statistics.
        
        Returns:
            TokenUsage: Current usage statistics
        """
        return self.token_usage
    
    def reset_token_usage(self) -> None:
        """Reset token usage statistics."""
        self.token_usage = TokenUsage()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get backend status information.
        
        Returns:
            Dict containing backend status
        """
        return {
            "provider": self.get_provider_name(),
            "token_usage": {
                "input_tokens": self.token_usage.input_tokens,
                "output_tokens": self.token_usage.output_tokens,
                "total_tokens": self.token_usage.get_total_tokens(),
                "estimated_cost": self.token_usage.estimated_cost
            },
            "config": self.config
        }