"""
MassGen v3 Backend System - Multi-Provider LLM Integration

Supports multiple LLM providers with standardized StreamChunk interface:
- Response API (standard format with tool support)
- Grok/xAI (Chat Completions API compatible)
- Claude (Messages API with multi-tool support)
- Gemini (structured output for coordination)
"""

from .base import LLMBackend, StreamChunk, TokenUsage
from .response import ResponseBackend
from .grok import GrokBackend
from .claude import ClaudeBackend
from .gemini import GeminiBackend

__all__ = [
    "LLMBackend",
    "StreamChunk",
    "TokenUsage",
    "ResponseBackend",
    "GrokBackend",
    "ClaudeBackend",
    "GeminiBackend",
]
