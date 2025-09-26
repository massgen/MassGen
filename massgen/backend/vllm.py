"""
vLLM backend using an OpenAI-compatible Chat Completions API.

Defaults are tailored for a local vLLM server:
- base_url: http://localhost:8000/v1 (or custom base URL)
- api_key:  "EMPTY" (vLLM accepts this as default)

This backend delegates most behavior to ChatCompletionsBackend, only
customizing provider naming, API key resolution, cost calculation, and
vLLM-specific extra_body parameters.
"""
from __future__ import annotations

import os
from typing import Optional, List, Dict, Any, AsyncGenerator
from .chat_completions import ChatCompletionsBackend
from .base import StreamChunk


class VLLMBackend(ChatCompletionsBackend):
    """vLLM backend (OpenAI-compatible, local server)."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        # Ensure vLLM defaults are in kwargs
        base_url = kwargs.get("base_url", "http://localhost:8000/v1")
        kwargs["base_url"] = base_url

        # Override to avoid environment-variable enforcement; vLLM accepts "EMPTY" as default
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("VLLM_API_KEY") or "EMPTY"

    def get_provider_name(self) -> str:
        """Return the provider name for this backend."""
        return "vLLM"
        
    def _build_vllm_extra_body(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Build vLLM-specific extra_body parameters and strip them from kwargs."""
        extra_body: Dict[str, Any] = {}

        # Add vLLM parameters from kwargs while preventing them from reaching parent payload
        top_k = kwargs.pop("top_k", None)
        if top_k is not None:
            extra_body["top_k"] = top_k

        repetition_penalty = kwargs.pop("repetition_penalty", None)
        if repetition_penalty is not None:
            extra_body["repetition_penalty"] = repetition_penalty

        enable_thinking = kwargs.pop("enable_thinking", None)
        if enable_thinking is not None:
            extra_body["chat_template_kwargs"] = {"enable_thinking": enable_thinking}

        return extra_body

    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI-compatible Chat Completions API with vLLM-specific parameters.
        vLLM supports additional parameters through extra_body for features like
        top_k sampling and enable_thinking mode.
        """
        # Build vLLM extra_body parameters
        extra_body = self._build_vllm_extra_body(kwargs)

        # Add extra_body to kwargs if we have vLLM-specific parameters
        if extra_body:
            kwargs["extra_body"] = extra_body

        # Delegate to parent with vLLM-specific parameters in extra_body
        async for chunk in super().stream_with_tools(messages, tools, **kwargs):
            yield chunk

    def get_supported_builtin_tools(self) -> List[str]:  # type: ignore[override]
        """Return list of supported builtin tools.
        
        vLLM (local OpenAI-compatible) does not provide provider-specific builtin tools.
        """
        return []