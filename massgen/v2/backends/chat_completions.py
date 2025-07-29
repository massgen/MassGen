"""
ChatCompletions backend for OpenAI-compatible APIs.
"""

from typing import Dict, List, Optional, Any, AsyncGenerator
from .base import AgentBackend


class ChatCompletionsBackend(AgentBackend):
    """Base class for standard chat completions APIs (OpenAI-compatible)."""
    
    def __init__(self, **kwargs):
        """
        Initialize ChatCompletionsBackend.
        
        Args:
            **kwargs: Configuration including model, api_key, base_url, etc.
        """
        super().__init__(**kwargs)
    
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
                # TODO: Handle other tool formats as needed
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
        # TODO: Use a more accurate tokenizer if available
        return len(text) // 4