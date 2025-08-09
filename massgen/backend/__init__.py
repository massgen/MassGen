"""
MassGen Backend System - Multi-Provider LLM Integration
MassGen Backend System - Multi-Provider LLM Integration

Supports multiple LLM providers with standardized StreamChunk interface:
- ChatCompletions (OpenAI-compatible for Cerebras AI, etc.)
- Claude (Messages API with multi-tool support)
- Gemini (structured output for coordination)
- Claude Code CLI (command-line interface integration)
- Claude Code Stream (claude-code-sdk streaming integration)
- Gemini CLI (command-line interface integration)
"""

from .base import LLMBackend, StreamChunk, TokenUsage
from .chat_completions import ChatCompletionsBackend
from .response import ResponseBackend
from .grok import GrokBackend
from .lmstudio import LMStudioBackend
from .claude import ClaudeBackend
from .gemini import GeminiBackend
from .cli_base import CLIBackend
from .claude_code_cli import ClaudeCodeCLIBackend
from .claude_code_cli_stream import ClaudeCodeStreamBackend
from .gemini_cli import GeminiCLIBackend

__all__ = [
    "LLMBackend",
    "StreamChunk",
    "TokenUsage",
    "ChatCompletionsBackend",
    "ResponseBackend",
    "GrokBackend",
    "LMStudioBackend",
    "ClaudeBackend",
    "GeminiBackend",
    "CLIBackend",
    "ClaudeCodeCLIBackend",
    "ClaudeCodeStreamBackend",
    "GeminiCLIBackend",
]
