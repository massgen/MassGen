# -*- coding: utf-8 -*-
"""
Grok/xAI backend is using the chat_completions backend for streaming.
It overrides methods for Grok-specific features (Grok Live Search).

✅ TESTED: Backend works correctly with architecture
- ✅ Grok API integration working (through chat_completions)
- ✅ Streaming functionality working correctly
- ✅ SingleAgent integration working
- ✅ Error handling and pricing calculations implemented
- ✅ Web search is working through Grok Live Search
- ✅ MCP is working

TODO for future releases:
- Test multi-agent orchestrator integration
- Validate advanced Grok-specific features
"""
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from ..logger_config import log_stream_chunk
from .chat_completions import ChatCompletionsBackend

logger = logging.getLogger(__name__)


class GrokBackend(ChatCompletionsBackend):
    """Grok backend using xAI's OpenAI-compatible API."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        self.base_url = "https://api.x.ai/v1"

    def _create_client(self, **kwargs) -> AsyncOpenAI:
        """Create OpenAI client configured for xAI's Grok API."""
        import openai

        return openai.AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    def _add_grok_search_params(self, api_params: Dict[str, Any], all_params: Dict[str, Any]) -> Dict[str, Any]:
        """Add Grok Live Search parameters to API params if web search is enabled."""
        enable_web_search = all_params.get("enable_web_search", False)

        if enable_web_search:
            # Check for conflict with manually specified search_parameters
            existing_extra = api_params.get("extra_body", {})
            if isinstance(existing_extra, dict) and "search_parameters" in existing_extra:
                error_message = "Conflict: Cannot use both 'enable_web_search: true' and manual 'extra_body.search_parameters'. Use one or the other."
                log_stream_chunk("backend.grok", "error", error_message, self.agent_id)
                raise ValueError(error_message)

            # Merge search_parameters into existing extra_body
            search_params = {"mode": "auto", "return_citations": True}
            merged_extra = existing_extra.copy() if existing_extra else {}
            merged_extra["search_parameters"] = search_params
            api_params["extra_body"] = merged_extra

        return api_params

    async def _stream_with_custom_and_mcp_tools(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ):
        """Override to add Grok-specific search parameters before API call."""
        # Build API params using parent method
        all_params = {**self.config, **kwargs}
        api_params = await self.api_params_handler.build_api_params(current_messages, tools, all_params)

        # Add provider tools (web search, code interpreter) if enabled
        # Note: For Grok, get_provider_tools() won't add web_search function tool
        provider_tools = self.api_params_handler.get_provider_tools(all_params)

        if provider_tools:
            if "tools" not in api_params:
                api_params["tools"] = []
            api_params["tools"].extend(provider_tools)

        # Add Grok-specific web search parameters via extra_body
        api_params = self._add_grok_search_params(api_params, all_params)

        # Start streaming
        stream = await client.chat.completions.create(**api_params)

        # Delegate to parent's stream processing
        async for chunk in super()._process_stream(stream, all_params, self.agent_id):
            yield chunk

    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "Grok"

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Grok."""
        return ["web_search"]
