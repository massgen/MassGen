from __future__ import annotations

"""
Grok/xAI backend implementation using OpenAI-compatible API.
Clean implementation with only Grok-specific features.

✅ TESTED: Backend works correctly with v3 architecture
- ✅ Grok API integration working
- ✅ Tool message conversion compatible with Chat Completions format
- ✅ Streaming functionality working correctly  
- ✅ SingleAgent integration working
- ✅ Error handling and pricing calculations implemented

TODO for future releases:
- Test multi-agent orchestrator integration
- Test web search capabilities with tools
- Validate advanced Grok-specific features
"""

import os
from typing import Dict, List, Any, AsyncGenerator, Optional
from .chat_completions_backend import ChatCompletionsBackend
from .base import StreamChunk


class GrokBackend(ChatCompletionsBackend):
    """Grok backend using xAI's OpenAI-compatible API."""
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        self.base_url = "https://api.x.ai/v1"
    
    async def stream_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], 
                              **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using xAI's OpenAI-compatible API."""
        try:
            import openai
            
            # Use OpenAI client with xAI base URL
            client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            
            # Extract parameters
            model = kwargs.get("model", "grok-3-mini")
            max_tokens = kwargs.get("max_tokens", None)
            temperature = kwargs.get("temperature", None)
            enable_web_search = kwargs.get("enable_web_search", False)
            
            # Convert tools to Chat Completions format
            converted_tools = self.convert_tools_to_chat_completions_format(tools) if tools else None
            
            # Chat Completions API parameters
            api_params = {
                "model": model,
                "messages": messages,
                "tools": converted_tools,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True
            }
            
            # Add Live Search parameters if enabled (Grok-specific)
            if enable_web_search:
                search_params_kwargs = {"mode": "auto", "return_citations": True}
                
                # Allow override of search parameters from backend params
                max_results = kwargs.get("max_search_results")
                if max_results is not None:
                    search_params_kwargs["max_search_results"] = max_results
                
                search_mode = kwargs.get("search_mode")
                if search_mode is not None:
                    search_params_kwargs["mode"] = search_mode
                
                return_citations = kwargs.get("return_citations")
                if return_citations is not None:
                    search_params_kwargs["return_citations"] = return_citations
                
                # Use extra_body to pass search_parameters to xAI API
                api_params["extra_body"] = {
                    "search_parameters": search_params_kwargs
                }
            
            # Create stream
            stream = await client.chat.completions.create(**api_params)
            
            # Use base class streaming handler
            async for chunk in self.handle_chat_completions_stream(stream, enable_web_search):
                yield chunk
            
        except Exception as e:
            yield StreamChunk(type="error", error=f"Grok API error: {e}")
    
    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "Grok"
    
    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Grok."""
        return ["web_search"]
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (rough approximation)."""
        return int(len(text.split()) * 1.3)
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost for token usage."""
        model_lower = model.lower()
        
        # Handle -mini models with lower costs
        if "grok-2" in model_lower:
            if "mini" in model_lower:
                input_cost = (input_tokens / 1_000_000) * 1.0   # Lower cost for mini
                output_cost = (output_tokens / 1_000_000) * 5.0
            else:
                input_cost = (input_tokens / 1_000_000) * 2.0
                output_cost = (output_tokens / 1_000_000) * 10.0
        elif "grok-3" in model_lower:
            if "mini" in model_lower:
                input_cost = (input_tokens / 1_000_000) * 2.5   # Lower cost for mini
                output_cost = (output_tokens / 1_000_000) * 7.5
            else:
                input_cost = (input_tokens / 1_000_000) * 5.0
                output_cost = (output_tokens / 1_000_000) * 15.0
        elif "grok-4" in model_lower:
            if "mini" in model_lower:
                input_cost = (input_tokens / 1_000_000) * 4.0   # Lower cost for mini
                output_cost = (output_tokens / 1_000_000) * 10.0
            else:
                input_cost = (input_tokens / 1_000_000) * 8.0
                output_cost = (output_tokens / 1_000_000) * 20.0
        else:
            # Default fallback (assume grok-3 pricing)
            input_cost = (input_tokens / 1_000_000) * 5.0
            output_cost = (output_tokens / 1_000_000) * 15.0
        
        return input_cost + output_cost