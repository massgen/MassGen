"""
OpenAI backend implementation.
"""

import os
import warnings
from typing import Dict, List, Optional, Any, AsyncGenerator
from .base import AgentBackend
from ..chat_agent import StreamChunk


class OpenAIResponseBackend(AgentBackend):
    """OpenAI Response API backend implementation."""
    
    def __init__(self, **kwargs):
        """
        Initialize OpenAI Response API backend.
        
        Args:
            **kwargs: Configuration including model, api_key, temperature, max_tokens, etc.
        """
        super().__init__(**kwargs)
        self.model = self.config.get("model", "gpt-4o")
        
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
            
            # Add tools if provided (following v1 pattern)
            formatted_tools = []
            if tools:
                formatted_tools = self._format_tools_for_response_api(tools)
                
            params["tools"] = formatted_tools if formatted_tools else None
            
            # Add optional parameters from config
            temperature = self.config.get("temperature")
            max_tokens = self.config.get("max_tokens")
            
            if temperature is not None and not self.model.startswith("o"):
                params["temperature"] = temperature
            if max_tokens is not None:
                params["max_output_tokens"] = max_tokens
            
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
            
            # Buffer for function calls
            current_function_call = None
            current_function_args = ""
            
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
                    
                    elif chunk.type == "response.function_call_arguments.delta":
                        # Buffer function call arguments
                        if hasattr(chunk, "delta") and chunk.delta:
                            current_function_args += chunk.delta
                    
                    elif chunk.type == "response.output_item.added":
                        # Start of a new function call
                        if hasattr(chunk, "item") and hasattr(chunk.item, "type"):
                            if chunk.item.type == "function_call":
                                current_function_call = {
                                    "id": getattr(chunk.item, "call_id", ""),
                                    "type": "function",
                                    "function": {
                                        "name": getattr(chunk.item, "name", ""),
                                        "arguments": ""
                                    }
                                }
                                current_function_args = ""
                    
                    elif chunk.type == "response.output_item.done":
                        # Function call completed - send the buffered tool call
                        if current_function_call:
                            current_function_call["function"]["arguments"] = current_function_args
                            yield StreamChunk(
                                type="tool_calls",
                                content=[current_function_call],
                                source="openai"
                            )
                            # Reset buffers
                            current_function_call = None
                            current_function_args = ""
                    
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
        """Format tools for OpenAI Response API - uses flattened structure."""
        formatted_tools = []
        
        for tool in tools:
            if isinstance(tool, dict):
                if tool.get("type") == "function" and "function" in tool:
                    # Response API expects flattened structure (from MASS reference)
                    function_def = tool["function"]
                    formatted_tool = {
                        "type": "function",
                        "name": function_def["name"],
                        "description": function_def.get("description", ""),
                        "parameters": function_def.get("parameters", {})
                    }
                    formatted_tools.append(formatted_tool)
                elif tool.get("type") == "function" and "name" in tool:
                    # Already in Response API format
                    formatted_tools.append(tool)
                elif tool == {"type": "web_search_preview"}:
                    # Built-in web search
                    formatted_tools.append({"type": "web_search_preview"})
                elif tool == {"type": "code_interpreter"}:
                    # Built-in code interpreter
                    formatted_tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
                else:
                    formatted_tools.append(tool)
            elif callable(tool):
                # Convert function to JSON format (from v1 implementation)
                from massgen.utils import function_to_json
                formatted_tools.append(function_to_json(tool))
            elif tool == "live_search":
                formatted_tools.append({"type": "web_search_preview"})
            elif tool == "code_execution":
                formatted_tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
        
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