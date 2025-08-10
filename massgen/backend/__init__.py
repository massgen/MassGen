"""
MassGen Backend System - Multi-Provider LLM Integration
MassGen Backend System - Multi-Provider LLM Integration

Supports multiple LLM providers with standardized StreamChunk interface:
- ChatCompletions (OpenAI-compatible for Cerebras AI, etc.)
- Claude (Messages API with multi-tool support)
- Gemini (structured output for coordination)
- Claude Code CLI (command-line interface integration)
- Claude Code (claude-code-sdk streaming integration)
- Gemini CLI (command-line interface integration)
"""

from .base import LLMBackend, StreamChunk, TokenUsage
from .chat_completions import ChatCompletionsBackend
from .response import ResponseBackend
from .grok import GrokBackend
from .claude import ClaudeBackend
from .gemini import GeminiBackend
from .cli_base import CLIBackend
from .claude_code_cli import ClaudeCodeCLIBackend
from .claude_code import ClaudeCodeBackend
from .gemini_cli import GeminiCLIBackend

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
    "ClaudeCodeCLIBackend",
    "ClaudeCodeBackend",
    "GeminiCLIBackend",
]
