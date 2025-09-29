# -*- coding: utf-8 -*-
"""
Inference backend supporting both vLLM and SGLang servers using OpenAI-compatible Chat Completions API.

Defaults are tailored for local inference servers:
- vLLM: base_url: http://localhost:8000/v1, api_key: "EMPTY"
- SGLang: base_url: http://localhost:30000/v1, api_key: "EMPTY"

This backend delegates most behavior to ChatCompletionsBackend, only
customizing provider naming, API key resolution, and backend-specific extra_body parameters.
"""
from __future__ import annotations

import os
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

from .base import StreamChunk
from .chat_completions import ChatCompletionsBackend
from .utils.api_params_handler._chat_completions_api_params_handler import (
    ChatCompletionsAPIParamsHandler,
)


class InferenceAPIParamsHandler(ChatCompletionsAPIParamsHandler):
    """API params handler for InferenceBackend that excludes backend-specific parameters."""

    def get_excluded_params(self) -> Set[str]:
        """Get parameters to exclude from Chat Completions API calls, including backend-specific ones."""
        return (
            super()
            .get_excluded_params()
            .union(
                {
                    "chat_template_kwargs",
                    "top_k",
                    "repetition_penalty",
                    "separate_reasoning",  # SGLang-specific parameter
                },
            )
        )


class InferenceBackend(ChatCompletionsBackend):
    """Backend for local inference servers (vLLM and SGLang).

    This backend connects to inference servers running with OpenAI-compatible API.
    It supports both vLLM and SGLang specific parameters like guided generation,
    thinking mode, and separate reasoning.
    """

    def __init__(self, backend_type: str = "vllm", api_key: Optional[str] = None, **kwargs):
        """Initialize inference backend.

        Args:
            backend_type: Type of backend ("vllm" or "sglang")
            api_key: API key (usually "EMPTY" for local servers)
            **kwargs: Additional arguments passed to parent
        """
        self._backend_type = backend_type.lower()

        # Set default base URLs based on backend type
        if "base_url" not in kwargs:
            if self._backend_type == "sglang":
                kwargs["base_url"] = "http://localhost:30000/v1"
            else:  # vllm
                kwargs["base_url"] = "http://localhost:8000/v1"

        # Determine API key based on backend type before calling parent
        if api_key is None:
            if self._backend_type == "sglang":
                api_key = os.getenv("SGLANG_API_KEY") or "EMPTY"
            else:  # vllm
                api_key = os.getenv("VLLM_API_KEY") or "EMPTY"

        # Initialize parent with the correct API key
        super().__init__(api_key, **kwargs)

        # Override the API params handler to exclude backend-specific parameters
        self.api_params_handler = InferenceAPIParamsHandler(self)

    def get_provider_name(self) -> str:
        """Get the provider name for this backend."""
        if self._backend_type == "sglang":
            return "SGLang"
        return "vLLM"

    def _build_extra_body(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Build backend-specific extra_body parameters and strip them from kwargs.

        Args:
            kwargs: Keyword arguments that may contain backend parameters

        Returns:
            Dictionary of backend-specific parameters for extra_body
        """
        extra_body: Dict[str, Any] = {}

        # Add vLLM and sglang specific parameters from kwargs while preventing them from reaching parent payload
        top_k = kwargs.pop("top_k", None)
        if top_k is not None:
            extra_body["top_k"] = top_k

        repetition_penalty = kwargs.pop("repetition_penalty", None)
        if repetition_penalty is not None:
            extra_body["repetition_penalty"] = repetition_penalty

        # Unified chat template handling for both vLLM and SGLang , Some models different way to add it
        chat_template_kwargs = kwargs.pop("chat_template_kwargs", None)
        if chat_template_kwargs is not None:
            extra_body["chat_template_kwargs"] = chat_template_kwargs

        # SGLang-specific parameters handling for separate reasoning
        if self._backend_type == "sglang":
            separate_reasoning = kwargs.pop("separate_reasoning", None)
            if separate_reasoning is not None:
                extra_body["separate_reasoning"] = separate_reasoning

        return extra_body

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI-compatible Chat Completions API with backend-specific parameters.

        Args:
            messages: List of messages
            tools: List of tool definitions
            **kwargs: Additional parameters including backend-specific ones

        Yields:
            StreamChunk objects
        """
        # Build backend-specific extra_body parameters
        extra_body = self._build_extra_body(kwargs)

        # Add extra_body to kwargs if we have backend-specific parameters
        if extra_body:
            # Add to existing extra_body if present
            if "extra_body" in kwargs:
                kwargs["extra_body"].update(extra_body)
            else:
                kwargs["extra_body"] = extra_body

        # Delegate to parent with backend-specific parameters in extra_body
        async for chunk in super().stream_with_tools(messages, tools, **kwargs):
            yield chunk

    def get_supported_builtin_tools(self) -> List[str]:
        """Return list of supported builtin tools.

        Local inference servers (vLLM/SGLang) do not provide provider-specific builtin tools.
        """
        return []
