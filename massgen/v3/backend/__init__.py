"""
MassGen v3 Backend System - Multi-Provider LLM Integration

Supports multiple LLM providers with standardized StreamChunk interface:
- OpenAI (Response API with tool support)
- Grok/xAI (Chat Completions API compatible)
- Claude (Messages API with multi-tool support)
- Gemini (research/documentation phase)
"""

from .base import LLMBackend, StreamChunk, TokenUsage
from .openai_backend import OpenAIBackend
from .grok_backend import GrokBackend
from .claude_backend import ClaudeBackend

__all__ = [
    "LLMBackend",
    "StreamChunk", 
    "TokenUsage",
    "OpenAIBackend",
    "GrokBackend",
    "ClaudeBackend"
]