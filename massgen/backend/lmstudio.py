from __future__ import annotations

"""
LM Studio backend using an OpenAI-compatible Chat Completions API.

Defaults are tailored for a local LM Studio server:
- base_url: http://localhost:1234/v1
- api_key:  "lm-studio" (LM Studio accepts any non-empty key)

This backend delegates most behavior to ChatCompletionsBackend, only
customizing provider naming, API key resolution, and cost calculation.
"""

from typing import Optional, List, Dict, Any, AsyncGenerator

from .chat_completions import ChatCompletionsBackend
from .base import StreamChunk


class LMStudioBackend(ChatCompletionsBackend):
    """LM Studio backend (OpenAI-compatible, local server)."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        # Ensure LM Studio defaults
        base_url = kwargs.get("base_url") or "http://localhost:1234/v1"
        # Pass through with our resolved key and base_url
        resolved_api_key = (api_key.strip() if api_key and api_key.strip() else "lm-studio")
        super().__init__(resolved_api_key, base_url=base_url, **kwargs)

    # Override to avoid environment-variable enforcement; LM Studio accepts any key
    def _resolve_api_key(self, provided_key: Optional[str], provider_name: str) -> str:  # type: ignore[override]
        return (provided_key.strip() if provided_key and provided_key.strip() else "lm-studio")

    def get_provider_name(self) -> str:
        return "LM Studio"

    # Local server usage is typically free; report zero cost
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:  # type: ignore[override]
        return 0.0

    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI-compatible Chat Completions API.

        LM Studio does not require special message conversions; this delegates to
        the generic ChatCompletions implementation while preserving our defaults.
        """
        async for chunk in super().stream_with_tools(messages, tools, **kwargs):
            yield chunk

    def get_supported_builtin_tools(self) -> List[str]:  # type: ignore[override]
        # LM Studio (local OpenAI-compatible) does not provide provider-builtins
        return []

    def estimate_tokens(self, text: str) -> int:  # type: ignore[override]
        # Simple heuristic consistent with ChatCompletionsBackend
        return int(len(text.split()) * 1.3)


