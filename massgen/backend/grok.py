from __future__ import annotations

"""
Grok/xAI backend implementation using OpenAI-compatible API.
Clean implementation with only Grok-specific features.

✅ TESTED: Backend works correctly with architecture
- ✅ Grok API integration working
- ✅ Tool message conversion compatible with Chat Completions format
- ✅ Streaming functionality working correctly  
- ✅ SingleAgent integration working
- ✅ Error handling and pricing calculations implemented

TODO for future releases:
- Test multi-agent orchestrator integration
- Test web search capabilities with tools
- Validate advanced Grok-specific features
"""

import os
from typing import Dict, List, Any, AsyncGenerator, Optional
from .chat_completions import ChatCompletionsBackend
from .base import StreamChunk


class GrokBackend(ChatCompletionsBackend):
    """Grok backend using xAI's OpenAI-compatible API."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        self.base_url = "https://api.x.ai/v1"

    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using xAI's OpenAI-compatible API."""

        # Convert messages for Grok API compatibility
        grok_messages = self._convert_messages_for_grok(messages)

        try:
            import openai

            # Use OpenAI client with xAI base URL
            client = openai.AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

            # Merge constructor config with stream kwargs (stream kwargs take priority)
            all_params = {**self.config, **kwargs}

            # Extract framework-specific parameters
            enable_web_search = all_params.get("enable_web_search", False)

            # Convert tools to Chat Completions format
            converted_tools = (
                self.convert_tools_to_chat_completions_format(tools) if tools else None
            )

            # Chat Completions API parameters
            api_params = {
                "messages": grok_messages,
                "tools": converted_tools,
                "stream": True,
            }

            # Direct passthrough of all parameters except those handled separately
            excluded_params = {"enable_web_search", "agent_id", "session_id"}
            for key, value in all_params.items():
                if key not in excluded_params and value is not None:
                    api_params[key] = value

            # Add Live Search parameters if enabled (Grok-specific)
            if enable_web_search:
                # Check for conflict with manually specified search_parameters
                existing_extra = api_params.get("extra_body", {})
                if (
                    isinstance(existing_extra, dict)
                    and "search_parameters" in existing_extra
                ):
                    yield StreamChunk(
                        type="error",
                        error="Conflict: Cannot use both 'enable_web_search: true' and manual 'extra_body.search_parameters'. Use one or the other.",
                    )
                    return

                # Merge search_parameters into existing extra_body
                search_params = {"mode": "auto", "return_citations": True}
                merged_extra = existing_extra.copy()
                merged_extra["search_parameters"] = search_params
                api_params["extra_body"] = merged_extra

            # Create stream
            stream = await client.chat.completions.create(**api_params)

            # Use base class streaming handler
            async for chunk in self.handle_chat_completions_stream(
                stream, enable_web_search
            ):
                yield chunk

        except Exception as e:
            yield StreamChunk(type="error", error=f"Grok API error: {e}")

    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "Grok"

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Grok."""
        return ["web_search"]

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (rough approximation)."""
        return int(len(text.split()) * 1.3)

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Calculate cost for token usage."""
        model_lower = model.lower()

        # Handle -mini models with lower costs
        if "grok-2" in model_lower:
            if "mini" in model_lower:
                input_cost = (input_tokens / 1_000_000) * 1.0  # Lower cost for mini
                output_cost = (output_tokens / 1_000_000) * 5.0
            else:
                input_cost = (input_tokens / 1_000_000) * 2.0
                output_cost = (output_tokens / 1_000_000) * 10.0
        elif "grok-3" in model_lower:
            if "mini" in model_lower:
                input_cost = (input_tokens / 1_000_000) * 2.5  # Lower cost for mini
                output_cost = (output_tokens / 1_000_000) * 7.5
            else:
                input_cost = (input_tokens / 1_000_000) * 5.0
                output_cost = (output_tokens / 1_000_000) * 15.0
        elif "grok-4" in model_lower:
            if "mini" in model_lower:
                input_cost = (input_tokens / 1_000_000) * 4.0  # Lower cost for mini
                output_cost = (output_tokens / 1_000_000) * 10.0
            else:
                input_cost = (input_tokens / 1_000_000) * 8.0
                output_cost = (output_tokens / 1_000_000) * 20.0
        else:
            # Default fallback (assume grok-3 pricing)
            input_cost = (input_tokens / 1_000_000) * 5.0
            output_cost = (output_tokens / 1_000_000) * 15.0

        return input_cost + output_cost

    def _convert_messages_for_grok(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert messages for Grok API compatibility.

        Grok expects tool call arguments as JSON strings in conversation history,
        but returns them as objects in responses.
        """
        import json

        converted_messages = []

        for message in messages:
            # Create a copy to avoid modifying the original
            converted_msg = dict(message)

            # Convert tool_calls arguments from objects to JSON strings
            if message.get("role") == "assistant" and "tool_calls" in message:
                converted_tool_calls = []
                for tool_call in message["tool_calls"]:
                    converted_call = dict(tool_call)
                    if "function" in converted_call:
                        converted_function = dict(converted_call["function"])
                        arguments = converted_function.get("arguments")

                        # Convert arguments to JSON string if it's an object
                        if isinstance(arguments, dict):
                            converted_function["arguments"] = json.dumps(arguments)
                        elif arguments is None:
                            converted_function["arguments"] = "{}"
                        # If it's already a string, keep it as-is

                        converted_call["function"] = converted_function
                    converted_tool_calls.append(converted_call)
                converted_msg["tool_calls"] = converted_tool_calls

            converted_messages.append(converted_msg)

        return converted_messages
