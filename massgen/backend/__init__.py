"""
MassGen Backend System - Multi-Provider LLM Integration

Supports multiple LLM providers with standardized StreamChunk interface:
- ChatCompletions (OpenAI-compatible for Cerebras AI, etc.)
- Claude (Messages API with multi-tool support)
- Gemini (structured output for coordination)
- Grok/xAI (Chat Completions API compatible)
- Response API (standard format with tool support)
"""

from .base import LLMBackend, StreamChunk, TokenUsage
from .chat_completions import ChatCompletionsBackend
from .response import ResponseBackend
from .grok import GrokBackend
from .claude import ClaudeBackend
from .gemini import GeminiBackend

__all__ = [
    "LLMBackend",
    "StreamChunk",
    "TokenUsage",
    "ChatCompletionsBackend",
    "ResponseBackend",
    "GrokBackend",
    "ClaudeBackend",
    "GeminiBackend",
]
