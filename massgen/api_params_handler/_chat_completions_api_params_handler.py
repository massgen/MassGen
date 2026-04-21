"""
Chat Completions API parameters handler.
Handles parameter building for OpenAI Chat Completions API format.
"""

from __future__ import annotations

from typing import Any

from ._api_params_handler_base import APIParamsHandlerBase


class ChatCompletionsAPIParamsHandler(APIParamsHandlerBase):
    """Handler for Chat Completions API parameters."""

    def get_excluded_params(self) -> set[str]:
        """Get parameters to exclude from Chat Completions API calls."""
        return self.get_base_excluded_params().union(
            {
                "base_url",  # Used for client initialization, not API calls
                "enable_web_search",
                "engine",  # OpenRouter web search engine option (native/exa) - only used when enable_web_search=true
                "max_results",  # OpenRouter web search max results option - only used when enable_web_search=true
                "search_prompt",  # OpenRouter web search custom prompt - only used when enable_web_search=true
                "search_context_size",  # OpenRouter web search context size (low/medium/high) - only used when enable_web_search=true
                "enable_code_interpreter",
                "allowed_tools",
                "exclude_tools",
                "custom_tools",  # Custom tools configuration (processed separately)
                "enable_file_generation",  # Internal flag for file generation (used in system messages only)
                "enable_image_generation",  # Internal flag for image generation (used in system messages only)
                "enable_audio_generation",  # Internal flag for audio generation (used in system messages only)
                "enable_video_generation",  # Internal flag for video generation (used in system messages only)
                "reasoning",  # OpenRouter reasoning config - handled via extra_body in configure_openrouter_extra_body()
                "provider_order",  # OpenRouter provider routing order - handled via extra_body.provider.order in configure_openrouter_extra_body()
            },
        )

    def get_provider_tools(self, all_params: dict[str, Any]) -> list[dict[str, Any]]:
        """Get provider tools for Chat Completions format."""
        provider_tools = []

        # Check if this is Grok backend - Grok uses extra_body.search_parameters instead of function tools
        backend_provider = getattr(self.backend, "get_provider_name", lambda: "")()
        is_grok = backend_provider.lower() == "grok"

        # Check if this is OpenRouter - OpenRouter uses plugins array instead of function tools
        base_url = all_params.get("base_url", "")
        is_openrouter = "openrouter.ai" in base_url

        # Add web_search function tool for non-Grok and non-OpenRouter backends
        # Grok handles web search via extra_body.search_parameters (set in grok.py)
        # OpenRouter handles web search via plugins array (set in chat_completions.py)
        if all_params.get("enable_web_search", False) and not is_grok and not is_openrouter:
            provider_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Search the web for current or factual information",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query to send to the web",
                                },
                            },
                            "required": ["query"],
                        },
                    },
                },
            )

        if all_params.get("enable_code_interpreter", False):
            provider_tools.append(
                {
                    "type": "code_interpreter",
                    "container": {"type": "auto"},
                },
            )

        return provider_tools

    def build_base_api_params(self, messages: list[dict[str, Any]], all_params: dict[str, Any]) -> dict[str, Any]:
        """Build base API parameters for Chat Completions requests."""
        # Sanitize: remove trailing assistant tool_calls without corresponding tool results
        sanitized_messages = self._sanitize_messages_for_api(messages)
        # Convert messages to ensure tool call arguments are properly serialized
        converted_messages = self.formatter.format_messages(sanitized_messages)

        api_params = {
            "messages": converted_messages,
            "stream": True,
        }

        # Direct passthrough of all parameters except those handled separately
        # Also filter out internal parameters (starting with _)
        for key, value in all_params.items():
            if key not in self.get_excluded_params() and not key.startswith("_") and value is not None:
                api_params[key] = value

        return api_params

    async def build_api_params(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        all_params: dict[str, Any],
    ) -> dict[str, Any]:
        """Build Chat Completions API parameters."""
        # Sanitize messages if needed
        if hasattr(self.backend, "_sanitize_messages_for_api"):
            messages = self._sanitize_messages_for_api(messages)

        # Convert messages to Chat Completions format
        converted_messages = self.formatter.format_messages(messages)

        # Build base parameters
        api_params = {
            "messages": converted_messages,
            "stream": True,
        }

        # Add filtered parameters
        # Also filter out internal parameters (starting with _)
        excluded = self.get_excluded_params()
        for key, value in all_params.items():
            if key not in excluded and not key.startswith("_") and value is not None:
                api_params[key] = value

        # Combine all tools
        combined_tools = []

        # Server-side tools (provider tools) go first
        provider_tools = self.get_provider_tools(all_params)
        if provider_tools:
            combined_tools.extend(provider_tools)

        # Workflow tools
        if tools:
            converted_tools = self.formatter.format_tools(tools)
            combined_tools.extend(converted_tools)

        # Add custom tools (includes internal background lifecycle helpers when available)
        custom_tools = self.get_custom_tools()
        if custom_tools:
            combined_tools.extend(custom_tools)

        # MCP tools
        mcp_tools = self.get_mcp_tools()
        if mcp_tools:
            combined_tools.extend(mcp_tools)

        if combined_tools:
            api_params["tools"] = combined_tools

        return api_params

    def _sanitize_messages_for_api(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Ensure assistant tool_calls are valid per OpenAI Chat Completions rules:
        - For any assistant message with tool_calls, each tool_call.id must have a following
          tool message with matching tool_call_id in the subsequent history.
        - Remove any tool_calls lacking matching tool results; drop the whole assistant message
          if no valid tool_calls remain and it has no useful content.
        This prevents 400 wrong_api_format errors.
        """
        try:
            sanitized: list[dict[str, Any]] = []
            len(messages)
            for i, msg in enumerate(messages):
                if msg.get("role") == "assistant" and "tool_calls" in msg:
                    tool_calls = msg.get("tool_calls") or []
                    valid_tool_calls = []
                    for tc in tool_calls:
                        tc_id = tc.get("id")
                        if not tc_id:
                            continue
                        # Does a later tool message reference this id?
                        has_match = any((m.get("role") == "tool" and m.get("tool_call_id") == tc_id) for m in messages[i + 1 :])
                        if has_match:
                            # Normalize arguments to string
                            fn = dict(tc.get("function", {}))
                            fn["arguments"] = self.formatter._serialize_tool_arguments(fn.get("arguments"))
                            valid_tc = dict(tc)
                            valid_tc["function"] = fn
                            valid_tool_calls.append(valid_tc)
                    if valid_tool_calls:
                        new_msg = dict(msg)
                        new_msg["tool_calls"] = valid_tool_calls
                        sanitized.append(new_msg)
                    else:
                        # Keep as plain assistant if it has content; otherwise drop
                        if msg.get("content"):
                            new_msg = {k: v for k, v in msg.items() if k != "tool_calls"}
                            sanitized.append(new_msg)
                        else:
                            continue
                else:
                    sanitized.append(msg)
            return sanitized
        except Exception:
            return messages
