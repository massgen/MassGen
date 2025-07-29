"""
OpenAI Chat Completions backend implementation.
"""

import os
import warnings
from typing import Dict, List, Optional, Any, AsyncGenerator
from .base import AgentBackend
from ..chat_agent import StreamChunk


class OpenAIChatCompletionsBackend(AgentBackend):
    """OpenAI Chat Completions API backend implementation."""
    
    def __init__(self, **kwargs):
        """
        Initialize OpenAI Chat Completions API backend.
        
        Args:
            **kwargs: Configuration including model, api_key, temperature, max_tokens, etc.
        """
        super().__init__(**kwargs)
        self.model = self.config.get("model", "gpt-4o-mini")
        
        # Import OpenAI client here to avoid import issues
        try:
            from openai import AsyncOpenAI
            
            # Get API key from config or environment
            api_key_val = self.config.get("api_key") or os.getenv("OPENAI_API_KEY")
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
        Stream response using OpenAI Chat Completions API.
        
        Args:
            messages: List of conversation messages
            tools: Optional list of tools
            **kwargs: Additional parameters
            
        Yields:
            StreamChunk: Streaming response chunks
        """
        try:
            # Prepare parameters for OpenAI Chat Completions API
            params = {
                "model": self.model,
                "messages": messages,
                "stream": True,
            }
            
            # Add tools if provided
            if tools:
                params["tools"] = tools
                params["tool_choice"] = "auto"
            
            # Add optional parameters from config
            temperature = self.config.get("temperature")
            max_tokens = self.config.get("max_tokens")
            
            if temperature is not None:
                params["temperature"] = temperature
            if max_tokens is not None:
                params["max_tokens"] = max_tokens
            
            # Make the API call
            response = await self.client.chat.completions.create(**params)
            
            # Stream the response
            text_content = ""
            tool_calls = []
            input_tokens = 0
            output_tokens = 0
            
            async for chunk in response:
                if hasattr(chunk, "choices") and chunk.choices:
                    choice = chunk.choices[0]
                    
                    if hasattr(choice, "delta"):
                        delta = choice.delta
                        
                        # Handle content
                        if hasattr(delta, "content") and delta.content:
                            text_content += delta.content
                            yield StreamChunk(
                                type="content",
                                content=delta.content,
                                source="openai"
                            )
                        
                        # Handle tool calls
                        if hasattr(delta, "tool_calls") and delta.tool_calls:
                            # Process tool calls
                            for tool_call_delta in delta.tool_calls:
                                if hasattr(tool_call_delta, "function"):
                                    tool_calls.append({
                                        "id": getattr(tool_call_delta, "id", ""),
                                        "type": "function",
                                        "function": {
                                            "name": getattr(tool_call_delta.function, "name", ""),
                                            "arguments": getattr(tool_call_delta.function, "arguments", "")
                                        }
                                    })
                            
                            yield StreamChunk(
                                type="tool_calls",
                                content=tool_calls,
                                source="openai"
                            )
                    
                    # Check if finished
                    if hasattr(choice, "finish_reason") and choice.finish_reason:
                        # Update token usage if available
                        if hasattr(chunk, "usage") and chunk.usage:
                            input_tokens = getattr(chunk.usage, "prompt_tokens", 0)
                            output_tokens = getattr(chunk.usage, "completion_tokens", 0)
                        
                        # Calculate cost and update usage
                        cost = self.calculate_cost(input_tokens, output_tokens, self.model)
                        self.token_usage.add_usage(input_tokens, output_tokens, cost)
                        
                        yield StreamChunk(
                            type="done",
                            source="openai",
                            status="completed"
                        )
                        break
        
        except Exception as e:
            yield StreamChunk(
                type="error",
                error=str(e),
                source="openai"
            )
    
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
        # OpenAI pricing (as of 2025)
        pricing = {
            "gpt-4o": {"input": 0.0025, "output": 0.01},  # per 1K tokens  
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
            "o1": {"input": 0.015, "output": 0.06},
            "o1-mini": {"input": 0.003, "output": 0.012},
            "o3-mini": {"input": 0.003, "output": 0.012},  # 2025 model
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
            # Configurable fallback pricing for unknown models
            fallback_input_rate = float(os.getenv("FALLBACK_INPUT_RATE", "0.0025"))
            fallback_output_rate = float(os.getenv("FALLBACK_OUTPUT_RATE", "0.01"))
            
            warnings.warn(
                f"Using fallback pricing for unknown model '{model}'. "
                f"Rates may be outdated. Input: ${fallback_input_rate}/1K tokens, "
                f"Output: ${fallback_output_rate}/1K tokens. "
                f"Set FALLBACK_INPUT_RATE and FALLBACK_OUTPUT_RATE env vars to override.",
                UserWarning
            )
            
            return (input_tokens / 1000) * fallback_input_rate + (output_tokens / 1000) * fallback_output_rate