"""
AgentBackend Architecture - Issue #18: Implement AgentBackend Architecture

This module implements a comprehensive AgentBackend architecture with async streaming,
token tracking, and multi-provider support.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, AsyncGenerator, Callable
from dataclasses import dataclass
import asyncio
import time
try:
    from .chat_agent import StreamChunk
except ImportError:
    from chat_agent import StreamChunk


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
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """
        Initialize the AgentBackend.
        
        Args:
            api_key: API key for the provider (if None, uses environment variable)
            **kwargs: Additional configuration parameters
        """
        self.api_key = api_key
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
            str: Name of the provider (e.g., "openai", "anthropic", "grok")
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


class ChatCompletionsBackend(AgentBackend):
    """Base class for standard chat completions APIs (OpenAI-compatible)."""
    
    def __init__(self, 
                 model: str, 
                 api_key: Optional[str] = None, 
                 base_url: Optional[str] = None,
                 **kwargs):
        """
        Initialize ChatCompletionsBackend.
        
        Args:
            model: Model name to use
            api_key: API key for the provider
            base_url: Base URL for the API
            **kwargs: Additional configuration
        """
        super().__init__(api_key, **kwargs)
        self.model = model
        self.base_url = base_url
    
    def format_tools_for_api(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format tools for the specific API format.
        
        Args:
            tools: List of tool definitions
            
        Returns:
            List of formatted tools
        """
        # Default implementation - can be overridden by specific backends
        formatted_tools = []
        for tool in tools:
            if isinstance(tool, dict):
                formatted_tools.append(tool)
            else:
                # Handle other tool formats as needed
                formatted_tools.append(tool)
        return formatted_tools
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            int: Estimated token count
        """
        # Simple estimation: ~4 characters per token
        return len(text) // 4


class OpenAIResponseBackend(AgentBackend):
    """OpenAI Response API backend implementation."""
    
    def __init__(self, 
                 model: str = "gpt-4o", 
                 api_key: Optional[str] = None,
                 temperature: Optional[float] = None,
                 max_tokens: Optional[int] = None,
                 **kwargs):
        """
        Initialize OpenAI Response API backend.
        
        Args:
            model: OpenAI model to use
            api_key: OpenAI API key
            temperature: Temperature for generation
            max_tokens: Maximum tokens in response
            **kwargs: Additional configuration
        """
        super().__init__(api_key, **kwargs)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Import OpenAI client here to avoid import issues
        try:
            from openai import AsyncOpenAI
            import os
            
            # Get API key from environment if not provided
            api_key_val = api_key or os.getenv("OPENAI_API_KEY")
            if not api_key_val:
                raise ValueError("OpenAI API key not found")
            
            self.client = AsyncOpenAI(api_key=api_key_val)
        except ImportError as e:
            raise ImportError("OpenAI package not installed. Install with: pip install openai") from e
    
    async def stream_with_tools(self, 
                               messages: List[Dict[str, Any]], 
                               tools: Optional[List[Dict[str, Any]]] = None, 
                               **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream response using OpenAI Response API.
        
        Args:
            messages: List of conversation messages
            tools: Optional list of tools
            **kwargs: Additional parameters
            
        Yields:
            StreamChunk: Streaming response chunks
        """
        try:
            # Prepare parameters for OpenAI Response API
            params = {
                "model": self.model,
                "stream": True,
            }
            
            # Extract system instructions and input messages
            instructions = ""
            input_messages = []
            
            for message in messages:
                if message.get("role") == "system":
                    instructions = message["content"]
                else:
                    input_messages.append(message)
            
            if instructions:
                params["instructions"] = instructions
            
            params["input"] = input_messages
            
            # Add tools if provided
            if tools:
                formatted_tools = self._format_tools_for_response_api(tools)
                if formatted_tools:
                    params["tools"] = formatted_tools
            
            # Add optional parameters
            if self.temperature is not None and not self.model.startswith("o"):
                params["temperature"] = self.temperature
            if self.max_tokens is not None:
                params["max_output_tokens"] = self.max_tokens
            
            # Handle reasoning effort for o-series models
            if self.model.startswith("o"):
                effort = "low"  # default
                if self.model.endswith("-low"):
                    effort = "low"
                    params["model"] = self.model.replace("-low", "")
                elif self.model.endswith("-medium"):
                    effort = "medium"
                    params["model"] = self.model.replace("-medium", "")
                elif self.model.endswith("-high"):
                    effort = "high"
                    params["model"] = self.model.replace("-high", "")
                
                params["reasoning"] = {"effort": effort}
            
            # Make the API call
            response = await self.client.responses.create(**params)
            
            # Stream the response
            text_content = ""
            input_tokens = 0
            output_tokens = 0
            
            async for chunk in response:
                if hasattr(chunk, "type"):
                    if chunk.type == "response.output_text.delta":
                        if hasattr(chunk, "delta") and chunk.delta:
                            text_content += chunk.delta
                            yield StreamChunk(
                                type="content",
                                content=chunk.delta,
                                source="openai"
                            )
                    
                    elif chunk.type == "response.function_call_output.delta":
                        yield StreamChunk(
                            type="tool_calls",
                            content=chunk.delta if hasattr(chunk, "delta") else None,
                            source="openai"
                        )
                    
                    elif chunk.type == "response.completed":
                        # Final chunk - update token usage
                        if hasattr(chunk, "usage"):
                            input_tokens = getattr(chunk.usage, "input_tokens", 0)
                            output_tokens = getattr(chunk.usage, "output_tokens", 0)
                        
                        # Calculate cost and update usage
                        cost = self.calculate_cost(input_tokens, output_tokens, self.model)
                        self.token_usage.add_usage(input_tokens, output_tokens, cost)
                        
                        yield StreamChunk(
                            type="done",
                            source="openai",
                            status="completed"
                        )
        
        except Exception as e:
            yield StreamChunk(
                type="error",
                error=str(e),
                source="openai"
            )
    
    def _format_tools_for_response_api(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format tools for OpenAI Response API."""
        formatted_tools = []
        
        for tool in tools:
            if isinstance(tool, dict):
                if tool.get("type") == "function":
                    # Standard function tool
                    formatted_tools.append(tool)
                elif tool == {"type": "web_search_preview"}:
                    # Built-in web search
                    formatted_tools.append({"type": "web_search_preview"})
                elif tool == {"type": "code_interpreter"}:
                    # Built-in code interpreter
                    formatted_tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
                else:
                    formatted_tools.append(tool)
        
        return formatted_tools
    
    def get_provider_name(self) -> str:
        """Get provider name."""
        return "openai"
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """
        Calculate cost for OpenAI models.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name
            
        Returns:
            float: Estimated cost in USD
        """
        # OpenAI pricing (approximate, as of 2024)
        pricing = {
            "gpt-4o": {"input": 0.005, "output": 0.015},  # per 1K tokens
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
            "o1": {"input": 0.015, "output": 0.06},
            "o1-mini": {"input": 0.003, "output": 0.012},
        }
        
        # Get base model name (remove suffixes like -low, -medium, -high)
        base_model = model
        for suffix in ["-low", "-medium", "-high"]:
            if base_model.endswith(suffix):
                base_model = base_model.replace(suffix, "")
                break
        
        if base_model in pricing:
            rates = pricing[base_model]
            input_cost = (input_tokens / 1000) * rates["input"]
            output_cost = (output_tokens / 1000) * rates["output"]
            return input_cost + output_cost
        else:
            # Default pricing for unknown models
            return (input_tokens / 1000) * 0.005 + (output_tokens / 1000) * 0.015


# Factory function for creating backends
def create_backend(provider: str, model: str, **kwargs) -> AgentBackend:
    """
    Create an agent backend based on provider.
    
    Args:
        provider: Provider name ("openai", "anthropic", "grok", etc.)
        model: Model name
        **kwargs: Additional configuration
        
    Returns:
        AgentBackend: Initialized backend instance
    """
    if provider.lower() == "openai":
        return OpenAIResponseBackend(model=model, **kwargs)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


# Utility function to detect provider from model name
def get_provider_from_model(model: str) -> str:
    """
    Detect provider from model name.
    
    Args:
        model: Model name
        
    Returns:
        str: Provider name
    """
    model_lower = model.lower()
    
    if any(prefix in model_lower for prefix in ["gpt", "o1", "o3"]):
        return "openai"
    elif any(prefix in model_lower for prefix in ["claude"]):
        return "anthropic"
    elif any(prefix in model_lower for prefix in ["grok"]):
        return "grok"
    elif any(prefix in model_lower for prefix in ["gemini"]):
        return "google"
    else:
        # Default to OpenAI for unknown models
        return "openai"