# -*- coding: utf-8 -*-
"""
Base class for backends using OpenAI Chat Completions API format.
Handles common message processing, tool conversion, and streaming patterns.

Supported Providers and Environment Variables:
- OpenAI: OPENAI_API_KEY
- Cerebras AI: CEREBRAS_API_KEY
- Together AI: TOGETHER_API_KEY
- Fireworks AI: FIREWORKS_API_KEY
- Groq: GROQ_API_KEY
- Kimi/Moonshot: MOONSHOT_API_KEY or KIMI_API_KEY
- Nebius AI Studio: NEBIUS_API_KEY
- OpenRouter: OPENROUTER_API_KEY
- ZAI: ZAI_API_KEY
- POE: POE_API_KEY
- Qwen: QWEN_API_KEY
"""

from __future__ import annotations

# Standard library imports
from typing import Any, AsyncGenerator, Dict, List, Optional

# Third-party imports
from openai import AsyncOpenAI

from ..api_params_handler import ChatCompletionsAPIParamsHandler
from ..formatter import ChatCompletionsFormatter
from ..logger_config import log_backend_agent_message, log_stream_chunk, logger

# Local imports
from .base import FilesystemSupport, StreamChunk
from .base_with_custom_tool_and_mcp import CustomToolAndMCPBackend


class ChatCompletionsBackend(CustomToolAndMCPBackend):
    """Complete OpenAI-compatible Chat Completions API backend.

    Can be used directly with any OpenAI-compatible provider by setting provider name.
    Supports Cerebras AI, Together AI, Fireworks AI, DeepInfra, and other compatible providers.

    Environment Variables:
        Provider-specific API keys are automatically detected based on provider name.
        See ProviderRegistry.PROVIDERS for the complete list.

    """

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        # Backend name is already set in MCPBackend, but we may need to override it
        self.backend_name = self.get_provider_name()
        self.formatter = ChatCompletionsFormatter()
        self.api_params_handler = ChatCompletionsAPIParamsHandler(self)

    def supports_upload_files(self) -> bool:
        """Chat Completions backend supports upload_files preprocessing."""
        return True

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI Response API with unified MCP/non-MCP processing."""
        async for chunk in super().stream_with_tools(messages, tools, **kwargs):
            yield chunk

    async def _stream_with_custom_and_mcp_tools(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Recursively stream responses, executing custom and MCP tool calls as needed."""

        # Build API params for this iteration
        all_params = {**self.config, **kwargs}
        api_params = await self.api_params_handler.build_api_params(current_messages, tools, all_params)

        # Add provider tools (web search, code interpreter) if enabled
        provider_tools = self.api_params_handler.get_provider_tools(all_params)

        if provider_tools:
            if "tools" not in api_params:
                api_params["tools"] = []
            api_params["tools"].extend(provider_tools)

        # Start streaming
        stream = await client.chat.completions.create(**api_params)

        # Track function calls in this iteration
        captured_function_calls = []
        current_tool_calls = {}
        response_completed = False
        content = ""

        async for chunk in stream:
            try:
                if hasattr(chunk, "choices") and chunk.choices:
                    choice = chunk.choices[0]

                    # Handle content delta
                    if hasattr(choice, "delta") and choice.delta:
                        delta = choice.delta

                        # Plain text content
                        if getattr(delta, "content", None):
                            content_chunk = delta.content
                            content += content_chunk
                            yield StreamChunk(type="content", content=content_chunk)

                        # Tool calls streaming (OpenAI-style)
                        if getattr(delta, "tool_calls", None):
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
                                if hasattr(tool_call_delta, "function") and tool_call_delta.function:
                                    if getattr(tool_call_delta.function, "name", None):
                                        current_tool_calls[index]["function"]["name"] = tool_call_delta.function.name

                                    # Accumulate arguments (as string chunks)
                                    if getattr(tool_call_delta.function, "arguments", None):
                                        current_tool_calls[index]["function"]["arguments"] += tool_call_delta.function.arguments

                    # Handle finish reason
                    if getattr(choice, "finish_reason", None):
                        if choice.finish_reason == "tool_calls" and current_tool_calls:
                            final_tool_calls = []

                            for index in sorted(current_tool_calls.keys()):
                                call = current_tool_calls[index]
                                function_name = call["function"]["name"]
                                arguments_str = call["function"]["arguments"]

                                # Providers expect arguments to be a JSON string
                                arguments_str_sanitized = arguments_str if arguments_str.strip() else "{}"

                                final_tool_calls.append(
                                    {
                                        "id": call["id"],
                                        "type": "function",
                                        "function": {
                                            "name": function_name,
                                            "arguments": arguments_str_sanitized,
                                        },
                                    },
                                )

                            # Convert to captured format for processing (ensure arguments is a JSON string)
                            for tool_call in final_tool_calls:
                                args_value = tool_call["function"]["arguments"]
                                if not isinstance(args_value, str):
                                    args_value = self.formatter._serialize_tool_arguments(args_value)
                                captured_function_calls.append(
                                    {
                                        "call_id": tool_call["id"],
                                        "name": tool_call["function"]["name"],
                                        "arguments": args_value,
                                    },
                                )

                            yield StreamChunk(type="tool_calls", tool_calls=final_tool_calls)

                            response_completed = True
                            break  # Exit chunk loop to execute functions

                        elif choice.finish_reason in ["stop", "length"]:
                            response_completed = True
                            # No function calls, we're done (base case)
                            yield StreamChunk(type="done")
                            return

            except Exception as chunk_error:
                yield StreamChunk(type="error", error=f"Chunk processing error: {chunk_error}")
                continue

        # Execute any captured function calls
        if captured_function_calls and response_completed:
            # Categorize function calls
            mcp_calls = []
            custom_calls = []
            provider_calls = []

            for call in captured_function_calls:
                if call["name"] in self._mcp_functions:
                    mcp_calls.append(call)
                elif call["name"] in self._custom_tool_names:
                    custom_calls.append(call)
                else:
                    provider_calls.append(call)

            # If there are provider calls (non-MCP, non-custom), let API handle them
            if provider_calls:
                logger.info(f"Provider function calls detected: {[call['name'] for call in provider_calls]}. Ending local processing.")
                yield StreamChunk(type="done")
                return

            # Check circuit breaker status before executing MCP functions
            if mcp_calls and not await self._check_circuit_breaker_before_execution():
                logger.warning("All MCP servers blocked by circuit breaker")
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_blocked",
                    content="⚠️ [MCP] All servers blocked by circuit breaker",
                    source="circuit_breaker",
                )
                yield StreamChunk(type="done")
                return

            # Initialize for execution
            functions_executed = False
            updated_messages = current_messages.copy()
            processed_call_ids = set()  # Track processed calls

            # Check if planning mode is enabled - block MCP tool execution during planning
            if self.is_planning_mode_enabled():
                logger.info("[MCP] Planning mode enabled - blocking all MCP tool execution")
                yield StreamChunk(
                    type="mcp_status",
                    status="planning_mode_blocked",
                    content="🚫 [MCP] Planning mode active - MCP tools blocked during coordination",
                    source="planning_mode",
                )
                # Skip all MCP tool execution but still continue with workflow
                yield StreamChunk(type="done")
                return

            # Create single assistant message with all tool calls
            if captured_function_calls:
                # First add the assistant message with ALL tool_calls (both MCP and non-MCP)
                all_tool_calls = []
                for call in captured_function_calls:
                    all_tool_calls.append(
                        {
                            "id": call["call_id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": self.formatter._serialize_tool_arguments(call["arguments"]),
                            },
                        },
                    )

                # Add assistant message with all tool calls
                if all_tool_calls:
                    assistant_message = {
                        "role": "assistant",
                        "content": content.strip() if content.strip() else None,
                        "tool_calls": all_tool_calls,
                    }
                    updated_messages.append(assistant_message)

            # Execute custom tools first
            for call in custom_calls:
                try:
                    # Yield custom tool call status
                    yield StreamChunk(
                        type="custom_tool_status",
                        status="custom_tool_called",
                        content=f"🔧 [Custom Tool] Calling {call['name']}...",
                        source=f"custom_{call['name']}",
                    )

                    # Yield custom tool arguments
                    yield StreamChunk(
                        type="custom_tool_status",
                        status="function_call",
                        content=f"Arguments for Calling {call['name']}: {call['arguments']}",
                        source=f"custom_{call['name']}",
                    )

                    # Execute custom tool
                    result = await self._execute_custom_tool(call)

                    # Add function result to messages
                    function_output_msg = {
                        "role": "tool",
                        "tool_call_id": call["call_id"],
                        "content": str(result),
                    }
                    updated_messages.append(function_output_msg)

                    # Yield custom tool results
                    yield StreamChunk(
                        type="custom_tool_status",
                        status="function_call_output",
                        content=f"Results for Calling {call['name']}: {str(result)}",
                        source=f"custom_{call['name']}",
                    )

                    # Yield custom tool response status
                    yield StreamChunk(
                        type="custom_tool_status",
                        status="custom_tool_response",
                        content=f"✅ [Custom Tool] {call['name']} completed",
                        source=f"custom_{call['name']}",
                    )

                    processed_call_ids.add(call["call_id"])
                    functions_executed = True
                    logger.info(f"Executed custom tool: {call['name']}")

                except Exception as e:
                    logger.error(f"Error executing custom tool {call['name']}: {e}")
                    error_msg = f"Error executing {call['name']}: {str(e)}"

                    # Yield error with arguments shown
                    yield StreamChunk(
                        type="custom_tool_status",
                        status="function_call",
                        content=f"Arguments for Calling {call['name']}: {call['arguments']}",
                        source=f"custom_{call['name']}",
                    )

                    yield StreamChunk(
                        type="custom_tool_status",
                        status="custom_tool_error",
                        content=f"❌ [Custom Tool Error] {error_msg}",
                        source=f"custom_{call['name']}",
                    )

                    # Add error result to messages
                    error_output_msg = {
                        "role": "tool",
                        "tool_call_id": call["call_id"],
                        "content": error_msg,
                    }
                    updated_messages.append(error_output_msg)
                    processed_call_ids.add(call["call_id"])
                    functions_executed = True

            # Execute MCP function calls
            mcp_functions_executed = False
            for call in mcp_calls:
                function_name = call["name"]
                if function_name in self._mcp_functions:
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_tool_called",
                        content=f"🔧 [MCP Tool] Calling {function_name}...",
                        source=f"mcp_{function_name}",
                    )

                    # Yield detailed MCP status as StreamChunk
                    tools_info = f" ({len(self._mcp_functions)} tools available)" if self._mcp_functions else ""
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_tools_initiated",
                        content=f"MCP tool call initiated (call #{self._mcp_tool_calls_count}){tools_info}: {function_name}",
                        source=f"mcp_{function_name}",
                    )

                    try:
                        # Execute MCP function with retry and exponential backoff
                        result_str, result_obj = await self._execute_mcp_function_with_retry(function_name, call["arguments"])

                        # Check if function failed after all retries
                        if isinstance(result_str, str) and result_str.startswith("Error:"):
                            # Log failure but still create tool response
                            logger.warning(f"MCP function {function_name} failed after retries: {result_str}")

                            # Add error result to messages
                            function_output_msg = {
                                "role": "tool",
                                "tool_call_id": call["call_id"],
                                "content": result_str,
                            }
                            updated_messages.append(function_output_msg)

                            processed_call_ids.add(call["call_id"])
                            mcp_functions_executed = True
                            continue

                    except Exception as e:
                        # Only catch unexpected non-MCP system errors
                        logger.error(f"Unexpected error in MCP function execution: {e}")
                        error_msg = f"Error executing {function_name}: {str(e)}"

                        # Add error result to messages
                        function_output_msg = {
                            "role": "tool",
                            "tool_call_id": call["call_id"],
                            "content": error_msg,
                        }
                        updated_messages.append(function_output_msg)

                        processed_call_ids.add(call["call_id"])
                        mcp_functions_executed = True
                        continue

                    # Yield function_call status
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call",
                        content=f"Arguments for Calling {function_name}: {call['arguments']}",
                        source=f"mcp_{function_name}",
                    )

                    # Add function output to messages and yield status chunk
                    function_output_msg = {
                        "role": "tool",
                        "tool_call_id": call["call_id"],
                        "content": str(result_str),
                    }
                    updated_messages.append(function_output_msg)

                    # Yield function_call_output status with preview
                    result_text = str(result_str)
                    if hasattr(result_obj, "content") and result_obj.content:
                        if isinstance(result_obj.content, list) and len(result_obj.content) > 0:
                            first_item = result_obj.content[0]
                            if hasattr(first_item, "text"):
                                result_text = first_item.text

                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call_output",
                        content=f"Results for Calling {function_name}: {result_text}",
                        source=f"mcp_{function_name}",
                    )

                    logger.info(f"Executed MCP function {function_name} (stdio/streamable-http)")
                    processed_call_ids.add(call["call_id"])

                    # Yield MCP tool response status
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_tool_response",
                        content=f"✅ [MCP Tool] {function_name} completed",
                        source=f"mcp_{function_name}",
                    )

                    mcp_functions_executed = True
                    functions_executed = True

            # Ensure all captured function calls have results to prevent hanging
            for call in captured_function_calls:
                if call["call_id"] not in processed_call_ids:
                    logger.warning(f"Tool call {call['call_id']} for function {call['name']} was not processed - adding error result")

                    # Add missing function call and error result to messages
                    error_output_msg = {
                        "role": "tool",
                        "tool_call_id": call["call_id"],
                        "content": f"Error: Tool call {call['call_id']} for function {call['name']} was not processed. This may indicate a validation or execution error.",
                    }
                    updated_messages.append(error_output_msg)
                    mcp_functions_executed = True

            # Trim history after function executions to bound memory usage
            if functions_executed or mcp_functions_executed:
                updated_messages = self._trim_message_history(updated_messages)

                # Recursive call with updated messages
                async for chunk in self._stream_with_custom_and_mcp_tools(updated_messages, tools, client, **kwargs):
                    yield chunk
            else:
                # No functions were executed, we're done
                yield StreamChunk(type="done")
                return

        elif response_completed:
            # Response completed with no function calls - we're done (base case)
            yield StreamChunk(
                type="mcp_status",
                status="mcp_session_complete",
                content="✅ [MCP] Session completed",
                source="mcp_session",
            )
            yield StreamChunk(type="done")
            return

    async def _process_stream(self, stream, all_params, agent_id) -> AsyncGenerator[StreamChunk, None]:
        """Handle standard Chat Completions API streaming format with logging."""

        content = ""
        current_tool_calls = {}
        search_sources_used = 0
        provider_name = self.get_provider_name()
        enable_web_search = all_params.get("enable_web_search", False)
        log_prefix = f"backend.{provider_name.lower().replace(' ', '_')}"

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
                            reasoning_chunk = self._handle_reasoning_transition(log_prefix, agent_id)
                            if reasoning_chunk:
                                yield reasoning_chunk
                            content_chunk = delta.content
                            content += content_chunk
                            log_backend_agent_message(
                                agent_id or "default",
                                "RECV",
                                {"content": content_chunk},
                                backend_name=provider_name,
                            )
                            log_stream_chunk(log_prefix, "content", content_chunk, agent_id)
                            yield StreamChunk(type="content", content=content_chunk)

                        # Provider-specific reasoning/thinking streams (non-standard OpenAI fields)
                        if getattr(delta, "reasoning_content", None):
                            reasoning_active_key = "_reasoning_active"
                            setattr(self, reasoning_active_key, True)
                            thinking_delta = getattr(delta, "reasoning_content")
                            if thinking_delta:
                                log_stream_chunk(log_prefix, "reasoning", thinking_delta, agent_id)
                                yield StreamChunk(
                                    type="reasoning",
                                    content=thinking_delta,
                                    reasoning_delta=thinking_delta,
                                )

                        # Tool calls streaming (OpenAI-style)
                        if getattr(delta, "tool_calls", None):
                            # handle reasoning first
                            reasoning_chunk = self._handle_reasoning_transition(log_prefix, agent_id)
                            if reasoning_chunk:
                                yield reasoning_chunk

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
                                if hasattr(tool_call_delta, "function") and tool_call_delta.function:
                                    if getattr(tool_call_delta.function, "name", None):
                                        current_tool_calls[index]["function"]["name"] = tool_call_delta.function.name

                                    # Accumulate arguments (as string chunks)
                                    if getattr(tool_call_delta.function, "arguments", None):
                                        current_tool_calls[index]["function"]["arguments"] += tool_call_delta.function.arguments

                    # Handle finish reason
                    if getattr(choice, "finish_reason", None):
                        # handle reasoning first
                        reasoning_chunk = self._handle_reasoning_transition(log_prefix, agent_id)
                        if reasoning_chunk:
                            yield reasoning_chunk

                        if choice.finish_reason == "tool_calls" and current_tool_calls:
                            final_tool_calls = []

                            for index in sorted(current_tool_calls.keys()):
                                call = current_tool_calls[index]
                                function_name = call["function"]["name"]
                                arguments_str = call["function"]["arguments"]

                                # Providers expect arguments to be a JSON string
                                arguments_str_sanitized = arguments_str if arguments_str.strip() else "{}"

                                final_tool_calls.append(
                                    {
                                        "id": call["id"],
                                        "type": "function",
                                        "function": {
                                            "name": function_name,
                                            "arguments": arguments_str_sanitized,
                                        },
                                    },
                                )

                            log_stream_chunk(log_prefix, "tool_calls", final_tool_calls, agent_id)
                            yield StreamChunk(type="tool_calls", tool_calls=final_tool_calls)

                            complete_message = {
                                "role": "assistant",
                                "content": content.strip(),
                                "tool_calls": final_tool_calls,
                            }

                            yield StreamChunk(
                                type="complete_message",
                                complete_message=complete_message,
                            )
                            log_stream_chunk(log_prefix, "done", None, agent_id)
                            yield StreamChunk(type="done")
                            return

                        elif choice.finish_reason in ["stop", "length"]:
                            if search_sources_used > 0:
                                search_complete_msg = f"\n✅ [Live Search Complete] Used {search_sources_used} sources\n"
                                log_stream_chunk(log_prefix, "content", search_complete_msg, agent_id)
                                yield StreamChunk(
                                    type="content",
                                    content=search_complete_msg,
                                )

                            # Handle citations if present
                            if hasattr(chunk, "citations") and chunk.citations:
                                if enable_web_search:
                                    citation_text = "\n📚 **Citations:**\n"
                                    for i, citation in enumerate(chunk.citations, 1):
                                        citation_text += f"{i}. {citation}\n"
                                    log_stream_chunk(log_prefix, "content", citation_text, agent_id)
                                    yield StreamChunk(type="content", content=citation_text)

                            # Return final message
                            complete_message = {
                                "role": "assistant",
                                "content": content.strip(),
                            }
                            yield StreamChunk(
                                type="complete_message",
                                complete_message=complete_message,
                            )
                            log_stream_chunk(log_prefix, "done", None, agent_id)
                            yield StreamChunk(type="done")
                            return

                # Optionally handle usage metadata
                if hasattr(chunk, "usage") and chunk.usage:
                    if getattr(chunk.usage, "num_sources_used", 0) > 0:
                        search_sources_used = chunk.usage.num_sources_used
                        if enable_web_search:
                            search_msg = f"\n📊 [Live Search] Using {search_sources_used} sources for real-time data\n"
                            log_stream_chunk(log_prefix, "content", search_msg, agent_id)
                            yield StreamChunk(
                                type="content",
                                content=search_msg,
                            )

            except Exception as chunk_error:
                error_msg = f"Chunk processing error: {chunk_error}"
                log_stream_chunk(log_prefix, "error", error_msg, agent_id)
                yield StreamChunk(type="error", error=error_msg)
                continue

        # Fallback in case stream ends without finish_reason
        log_stream_chunk(log_prefix, "done", None, agent_id)
        yield StreamChunk(type="done")

    def create_tool_result_message(self, tool_call: Dict[str, Any], result_content: str) -> Dict[str, Any]:
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

    def _convert_messages_for_mcp_chat_completions(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert messages for MCP Chat Completions format if needed."""
        # For Chat Completions, messages are already in the correct format
        # Just ensure tool result messages use the correct format
        converted_messages = []

        for message in messages:
            if message.get("type") == "function_call_output":
                # Convert Response API format to Chat Completions format
                converted_message = {
                    "role": "tool",
                    "tool_call_id": message.get("call_id"),
                    "content": message.get("output", ""),
                }
                converted_messages.append(converted_message)
            else:
                # Pass through other messages as-is
                converted_messages.append(message.copy())

        return converted_messages

    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        # Check if provider name was explicitly set in config
        if "provider" in self.config:
            return self.config["provider"]
        elif "provider_name" in self.config:
            return self.config["provider_name"]

        # Try to infer from base_url
        base_url = self.config.get("base_url", "")
        if "openai.com" in base_url:
            return "OpenAI"
        elif "cerebras.ai" in base_url:
            return "Cerebras AI"
        elif "together.xyz" in base_url:
            return "Together AI"
        elif "fireworks.ai" in base_url:
            return "Fireworks AI"
        elif "groq.com" in base_url:
            return "Groq"
        elif "openrouter.ai" in base_url:
            return "OpenRouter"
        elif "z.ai" in base_url or "bigmodel.cn" in base_url:
            return "ZAI"
        elif "nebius.com" in base_url:
            return "Nebius AI Studio"
        elif "moonshot.ai" in base_url or "moonshot.cn" in base_url:
            return "Kimi"
        elif "poe.com" in base_url:
            return "POE"
        elif "aliyuncs.com" in base_url:
            return "Qwen"
        else:
            return "ChatCompletion"

    def get_filesystem_support(self) -> FilesystemSupport:
        """Chat Completions supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by this provider."""
        # Chat Completions API doesn't typically support builtin tools like web_search
        # But some providers might - this can be overridden in subclasses
        return []

    def _create_client(self, **kwargs) -> AsyncOpenAI:
        """Create OpenAI client with consistent configuration."""
        import openai

        all_params = {**self.config, **kwargs}
        base_url = all_params.get("base_url", "https://api.openai.com/v1")
        return openai.AsyncOpenAI(api_key=self.api_key, base_url=base_url)

    def _handle_reasoning_transition(self, log_prefix: str, agent_id: Optional[str]) -> Optional[StreamChunk]:
        """Handle reasoning state transition and return StreamChunk if transition occurred."""
        reasoning_active_key = "_reasoning_active"
        if hasattr(self, reasoning_active_key):
            if getattr(self, reasoning_active_key) is True:
                setattr(self, reasoning_active_key, False)
                log_stream_chunk(log_prefix, "reasoning_done", "", agent_id)
                return StreamChunk(type="reasoning_done", content="")
        return None
