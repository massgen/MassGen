from __future__ import annotations

"""
Base class for backends using OpenAI Chat Completions API format.
Handles common message processing, tool conversion, and streaming patterns.

Supported Providers and Environment Variables:
- OpenAI: OPENAI_API_KEY
- Cerebras AI: CEREBRAS_API_KEY
- Together AI: TOGETHER_API_KEY
- Fireworks AI: FIREWORKS_API_KEY
- Groq: GROQ_API_KEY
- Nebius AI Studio: NEBIUS_API_KEY
- OpenRouter: OPENROUTER_API_KEY
"""


# Standard library imports
import asyncio
import os
from dataclasses import dataclass
from typing import Dict, List, Any, AsyncGenerator, Optional, Tuple
from urllib.parse import urlparse

# Third-party imports
import openai
from openai import AsyncOpenAI
import logging

# Local imports

from .base import LLMBackend, StreamChunk

# Set up logger
logger = logging.getLogger(__name__)


class ChatCompletionsBackend(LLMBackend):
    """Complete OpenAI-compatible Chat Completions API backend.
    
    Can be used directly with any OpenAI-compatible provider by setting provider name.
    Supports Cerebras AI, Together AI, Fireworks AI, DeepInfra, and other compatible providers.
    
    Environment Variables:
        Provider-specific API keys are automatically detected based on provider name.
        See ProviderRegistry.PROVIDERS for the complete list.
    
    """

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)

    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        # Check if provider name was explicitly set in config
        if 'provider' in self.config:
            return self.config['provider']
        elif 'provider_name' in self.config:
            return self.config['provider_name']
        
        # Try to infer from base_url
        base_url = self.config.get('base_url', '')
        if 'openai.com' in base_url:
            return 'OpenAI'
        elif 'cerebras.ai' in base_url:
            return 'Cerebras AI'
        elif 'together.ai' in base_url:
            return 'Together AI'
        elif 'fireworks.ai' in base_url:
            return 'Fireworks AI'
        elif 'groq.com' in base_url:
            return 'Groq'
        elif 'openrouter.ai' in base_url:
            return 'OpenRouter'
        elif 'z.ai' in base_url:
            return 'ZAI'
        else:
            return 'LMStudio'

    def convert_tools_to_chat_completions_format(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert tools from Response API format to Chat Completions format if needed.

        Response API format: {"type": "function", "name": ..., "description": ..., "parameters": ...}
        Chat Completions format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        """
        if not tools:
            return tools

        converted_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                if "function" in tool:
                    # Already in Chat Completions format
                    converted_tools.append(tool)
                elif "name" in tool and "description" in tool:
                    # Response API format - convert to Chat Completions format
                    converted_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool["name"],
                                "description": tool["description"],
                                "parameters": tool.get("parameters", {}),
                            },
                        }
                    )
                else:
                    # Unknown format - keep as-is
                    converted_tools.append(tool)
            else:
                # Non-function tool - keep as-is
                converted_tools.append(tool)

        return converted_tools

    async def handle_chat_completions_stream(
        self, stream, enable_web_search: bool = False
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle standard Chat Completions API streaming format."""
        import json

        content = ""
        current_tool_calls = {}
        search_sources_used = 0

        async for chunk in stream:
            try:
                if hasattr(chunk, "choices") and chunk.choices:
                    choice = chunk.choices[0]

                    # Handle content delta
                    if hasattr(choice, "delta") and choice.delta:
                        delta = choice.delta

                        # Plain text content
                        if getattr(delta, "content", None):
                            # handle reasoning first
                            reasoning_active_key = f"_reasoning_active"
                            if hasattr(self, reasoning_active_key):
                                if getattr(self, reasoning_active_key) == True:
                                    setattr(self, reasoning_active_key, False)
                                    yield StreamChunk(
                                        type="reasoning_done",
                                        content=""
                                    )
                            content_chunk = delta.content
                            content += content_chunk
                            yield StreamChunk(type="content", content=content_chunk)

                        # Provider-specific reasoning/thinking streams (non-standard OpenAI fields)
                        if getattr(delta, "reasoning_content", None):
                            reasoning_active_key = f"_reasoning_active"
                            setattr(self, reasoning_active_key, True)
                            thinking_delta = getattr(delta, "reasoning_content")
                            if thinking_delta:
                                yield StreamChunk(
                                    type="reasoning",
                                    content=thinking_delta,
                                    reasoning_delta=thinking_delta,
                                )
                        
                        # Tool calls streaming (OpenAI-style)
                        if getattr(delta, "tool_calls", None):
                            # handle reasoning first
                            reasoning_active_key = f"_reasoning_active"
                            if hasattr(self, reasoning_active_key):
                                if getattr(self, reasoning_active_key) == True:
                                    setattr(self, reasoning_active_key, False)
                                    yield StreamChunk(
                                        type="reasoning_done",
                                        content=""
                                    )

                            for tool_call_delta in delta.tool_calls:
                                index = getattr(tool_call_delta, "index", 0)

                                if index not in current_tool_calls:
                                    current_tool_calls[index] = {
                                        "id": "",
                                        "function": {
                                            "name": "",
                                            "arguments": "",
                                        },
                                    }

                                # Accumulate id
                                if getattr(tool_call_delta, "id", None):
                                    current_tool_calls[index]["id"] = tool_call_delta.id

                                # Function name
                                if (
                                    hasattr(tool_call_delta, "function")
                                    and tool_call_delta.function
                                ):
                                    if getattr(tool_call_delta.function, "name", None):
                                        current_tool_calls[index]["function"][
                                            "name"
                                        ] = tool_call_delta.function.name

                                    # Accumulate arguments (as string chunks)
                                    if getattr(tool_call_delta.function, "arguments", None):
                                        current_tool_calls[index]["function"][
                                            "arguments"
                                        ] += tool_call_delta.function.arguments

                    # Handle finish reason
                    if getattr(choice, "finish_reason", None):
                        # handle reasoning first
                        reasoning_active_key = f"_reasoning_active"
                        if hasattr(self, reasoning_active_key):
                            if getattr(self, reasoning_active_key) == True:
                                setattr(self, reasoning_active_key, False)
                                yield StreamChunk(
                                    type="reasoning_done",
                                    content=""
                                )

                        if choice.finish_reason == "tool_calls" and current_tool_calls:

                            final_tool_calls = []

                            for index in sorted(current_tool_calls.keys()):
                                call = current_tool_calls[index]
                                function_name = call["function"]["name"]
                                arguments_str = call["function"]["arguments"]

                                try:
                                    arguments_obj = (
                                        json.loads(arguments_str)
                                        if arguments_str.strip()
                                        else {}
                                    )
                                except json.JSONDecodeError:
                                    arguments_obj = {}

                                final_tool_calls.append(
                                    {
                                        "id": call["id"] or f"toolcall_{index}",
                                        "type": "function",
                                        "function": {
                                            "name": function_name,
                                            "arguments": arguments_obj,
                                        },
                                    }
                                )

                            yield StreamChunk(
                                type="tool_calls", tool_calls=final_tool_calls
                            )

                            complete_message = {
                                "role": "assistant",
                                "content": content.strip(),
                                "tool_calls": final_tool_calls,
                            }

                            yield StreamChunk(
                                type="complete_message",
                                complete_message=complete_message,
                            )
                            yield StreamChunk(type="done")
                            return

                        elif choice.finish_reason in ["stop", "length"]:
                            if search_sources_used > 0:
                                yield StreamChunk(
                                    type="content",
                                    content=f"\n✅ [Live Search Complete] Used {search_sources_used} sources\n",
                                )

                            # Handle citations if present
                            if hasattr(chunk, "citations") and chunk.citations:
                                if enable_web_search:
                                    citation_text = "\n📚 **Citations:**\n"
                                    for i, citation in enumerate(chunk.citations, 1):
                                        citation_text += f"{i}. {citation}\n"
                                    yield StreamChunk(
                                        type="content", content=citation_text
                                    )

                            # Return final message
                            complete_message = {
                                "role": "assistant",
                                "content": content.strip(),
                            }
                            yield StreamChunk(
                                type="complete_message",
                                complete_message=complete_message,
                            )
                            yield StreamChunk(type="done")
                            return

                # Optionally handle usage metadata
                if hasattr(chunk, "usage") and chunk.usage:
                    if getattr(chunk.usage, "num_sources_used", 0) > 0:
                        search_sources_used = chunk.usage.num_sources_used
                        if enable_web_search:
                            yield StreamChunk(
                                type="content",
                                content=f"\n📊 [Live Search] Using {search_sources_used} sources for real-time data\n",
                            )

            except Exception as chunk_error:
                yield StreamChunk(
                    type="error", error=f"Chunk processing error: {chunk_error}"
                )
                continue

        # Fallback in case stream ends without finish_reason
        yield StreamChunk(type="done")


    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI-compatible Chat Completions API."""
        try:  

                import openai

                # Merge constructor config with stream kwargs (stream kwargs take priority)
                all_params = {**self.config, **kwargs}
                
                # Get base_url from config or use OpenAI default
                base_url = all_params.get("base_url", "https://api.openai.com/v1")
                
                client = openai.AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=base_url
                )
                
                # Extract framework-specific parameters
                enable_web_search = all_params.get("enable_web_search", False)
                enable_code_interpreter = all_params.get("enable_code_interpreter", False)

                # Convert tools to Chat Completions format
                converted_tools = (
                    self.convert_tools_to_chat_completions_format(tools) if tools else None
                )

                # Chat Completions API parameters
                api_params = {
                    "messages": messages,
                    "stream": True,
                }

                # Add tools if provided
                if converted_tools:
                    api_params["tools"] = converted_tools

                # Direct passthrough of all parameters except those handled separately
                excluded_params = {"enable_web_search", "enable_code_interpreter", "base_url", "agent_id", "session_id", "type"}
                for key, value in all_params.items():
                    if key not in excluded_params and value is not None:
                        api_params[key] = value


                # Add provider tools (web search, code interpreter) if enabled
                provider_tools = []
                if enable_web_search:
                    provider_tools.append({
                        "type": "function",
                        "function": {
                        "name": "web_search",
                        "description": "Search the web for current or factual information",
                        "parameters": {
                            "type": "object",
                            "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to send to the web"
                            }
                            },
                            "required": ["query"]
                        }
                        }
                    })

                if enable_code_interpreter:
                    provider_tools.append(
                        {"type": "code_interpreter", "container": {"type": "auto"}}
                    )

                if provider_tools:
                    if "tools" not in api_params:
                        api_params["tools"] = []
                    api_params["tools"].extend(provider_tools)

                # create stream
                stream = await client.chat.completions.create(**api_params)

                # Use existing streaming handler with enhanced error handling
                async for chunk in self.handle_chat_completions_stream(
                    stream, enable_web_search
                ):
                    yield chunk

        except Exception as e:
                yield StreamChunk(type="error", error=f"Chat Completions API error: {str(e)}")


    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (rough approximation)."""
        # Simple approximation: ~1.3 tokens per word
        return int(len(text.split()) * 1.3)

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Calculate cost for token usage based on OpenAI pricing (default fallback)."""
        model_lower = model.lower()
        
        # OpenAI GPT-4o pricing (most common)
        if "gpt-4o" in model_lower:
            if "mini" in model_lower:
                input_cost = (input_tokens / 1_000_000) * 0.15
                output_cost = (output_tokens / 1_000_000) * 0.60
            else:
                input_cost = (input_tokens / 1_000_000) * 2.50
                output_cost = (output_tokens / 1_000_000) * 10.00
        # GPT-4 pricing
        elif "gpt-4" in model_lower:
            if "turbo" in model_lower:
                input_cost = (input_tokens / 1_000_000) * 10.00
                output_cost = (output_tokens / 1_000_000) * 30.00
            else:
                input_cost = (input_tokens / 1_000_000) * 30.00
                output_cost = (output_tokens / 1_000_000) * 60.00
        # GPT-3.5 pricing
        elif "gpt-3.5" in model_lower:
            input_cost = (input_tokens / 1_000_000) * 0.50
            output_cost = (output_tokens / 1_000_000) * 1.50
        else:
            # Generic fallback pricing (moderate cost estimate)
            input_cost = (input_tokens / 1_000_000) * 1.00
            output_cost = (output_tokens / 1_000_000) * 3.00

        return input_cost + output_cost

    def extract_tool_name(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool name from Chat Completions format."""
        return tool_call.get("function", {}).get("name", "unknown")

    def extract_tool_arguments(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tool arguments from Chat Completions format."""
        arguments = tool_call.get("function", {}).get("arguments", {})
        if isinstance(arguments, str):
            try:
                import json
                return json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return {}
        return arguments

    def extract_tool_call_id(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool call ID from Chat Completions format."""
        return tool_call.get("id", "")

    def create_tool_result_message(
        self, tool_call: Dict[str, Any], result_content: str
    ) -> Dict[str, Any]:
        """Create tool result message for Chat Completions format."""
        tool_call_id = self.extract_tool_call_id(tool_call)
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result_content,
        }

    def extract_tool_result_content(self, tool_result_message: Dict[str, Any]) -> str:
        """Extract content from Chat Completions tool result message."""
        return tool_result_message.get("content", "")

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by this provider."""
        # Chat Completions API doesn't typically support builtin tools like web_search
        # But some providers might - this can be overridden in subclasses
        return []
