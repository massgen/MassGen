"""
MassGen Backend System - Multi-Provider LLM Integration

Supports multiple LLM providers with standardized StreamChunk interface:
- ChatCompletions (OpenAI-compatible for Cerebras AI, etc.)
- Response API (OpenAI Response API with reasoning support)
- Grok (xAI API with live search capabilities)
- Claude (Messages API with multi-tool support)
- Gemini (structured output for coordination)
- Claude Code (claude-code-sdk streaming integration)
TODO - Gemini CLI (command-line interface integration)
TODO - Clean up StreamChunk design (too many optional fields for reasoning/provider features)
"""

from .base import LLMBackend, StreamChunk, TokenUsage
from .chat_completions import ChatCompletionsBackend
from .response import ResponseBackend
from .grok import GrokBackend
from .claude import ClaudeBackend
from .gemini import GeminiBackend
from .cli_base import CLIBackend
# from .claude_code_cli import ClaudeCodeCLIBackend  # File removed
from .claude_code import ClaudeCodeBackend
# from .gemini_cli import GeminiCLIBackend

__all__ = [
    "LLMBackend",
    "StreamChunk",
    "TokenUsage",
    "ChatCompletionsBackend",
    "ResponseBackend",
    "GrokBackend",
    "ClaudeBackend",
    "GeminiBackend",
    "CLIBackend",
    "ClaudeCodeBackend",
    # "GeminiCLIBackend",
]
