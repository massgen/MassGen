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
- Nvidia NIM: NGC_API_KEY
- Nebius AI Studio: NEBIUS_API_KEY
- OpenRouter: OPENROUTER_API_KEY
- ZAI: ZAI_API_KEY
- POE: POE_API_KEY
- Qwen: QWEN_API_KEY
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

# Standard library imports
from typing import Any

# Third-party imports
from openai import AsyncOpenAI

from ..api_params_handler import ChatCompletionsAPIParamsHandler
from ..formatter import ChatCompletionsFormatter
from ..logger_config import log_backend_agent_message, log_stream_chunk, logger
from ..stream_chunk import ChunkType
from ..structured_logging import trace_llm_api_call

# Local imports
from ._constants import configure_openrouter_extra_body
from ._context_errors import is_context_length_error
from ._streaming_buffer_mixin import StreamingBufferMixin
from .base import FilesystemSupport, StreamChunk
from .base_with_custom_tool_and_mcp import (
    CustomToolAndMCPBackend,
    CustomToolChunk,
    ToolExecutionConfig,
)
from .llm_circuit_breaker import (
    CircuitBreakerOpenError,
    LLMCircuitBreaker,
    LLMCircuitBreakerConfig,
)


class ChatCompletionsBackend(StreamingBufferMixin, CustomToolAndMCPBackend):
    """Complete OpenAI-compatible Chat Completions API backend.

    Can be used directly with any OpenAI-compatible provider by setting provider name.
    Supports Cerebras AI, Together AI, Fireworks AI, DeepInfra, and other compatible providers.

    Environment Variables:
        Provider-specific API keys are automatically detected based on provider name.
        See ProviderRegistry.PROVIDERS for the complete list.

    """

    def __init__(self, api_key: str | None = None, **kwargs):
        # Extract circuit breaker config before passing to super
        cb_config = self._build_circuit_breaker_config(kwargs)
        super().__init__(api_key, **kwargs)
        # Backend name is already set in MCPBackend, but we may need to override it
        self.backend_name = self.get_provider_name()
        self.formatter = ChatCompletionsFormatter()
        self.api_params_handler = ChatCompletionsAPIParamsHandler(self)

        # Track interrupted streams for token estimation
        # When a stream is cancelled (e.g., in multi-agent restart), we need to estimate tokens
        self._interrupted_stream_content: str = ""
        self._interrupted_stream_model: str = ""
        self._interrupted_stream_messages: list[dict[str, Any]] = []  # Track input for estimation
        self._stream_usage_received: bool = True  # True = no pending estimation needed
        # Track reasoning state for streaming (needed for reasoning_done transition)
        self._reasoning_active: bool = False
        self.circuit_breaker = LLMCircuitBreaker(
            config=cb_config,
            backend_name=self.get_provider_name(),
        )

    @staticmethod
    def _build_circuit_breaker_config(
        kwargs: dict[str, Any],
    ) -> LLMCircuitBreakerConfig:
        """Extract circuit breaker settings from kwargs and build config."""
        cb_kwargs: dict[str, Any] = {}
        prefix = "llm_circuit_breaker_"
        keys_to_pop: list[str] = []
        for key in kwargs:
            if key.startswith(prefix):
                param = key[len(prefix) :]
                cb_kwargs[param] = kwargs[key]
                keys_to_pop.append(key)
        for key in keys_to_pop:
            kwargs.pop(key)
        return LLMCircuitBreakerConfig(**cb_kwargs)

    def finalize_token_tracking(self) -> None:
        """Finalize token tracking by estimating tokens for any interrupted streams.

        Call this method after coordination completes to ensure interrupted streams
        (e.g., cancelled due to multi-agent restart_pending) get their tokens estimated.
        """
        if not self._stream_usage_received:
            # Estimate tokens for the interrupted stream
            # Use tracked messages for input estimation, content for output estimation
            messages = self._interrupted_stream_messages or []
            content = self._interrupted_stream_content or ""
            model = self._interrupted_stream_model or "gpt-4o"

            if messages or content:
                self._estimate_token_usage(messages, content, model)
                logger.info(
                    f"[{self.get_provider_name()}] Estimated tokens for interrupted stream: "
                    f"messages={len(messages)}, content_len={len(content)} -> "
                    f"in={self.token_usage.input_tokens}, out={self.token_usage.output_tokens}",
                )

            # Clear tracking
            self._interrupted_stream_content = ""
            self._interrupted_stream_messages = []
            self._stream_usage_received = True

    def supports_upload_files(self) -> bool:
        """Chat Completions backend supports upload_files preprocessing."""
        return True

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk]:
        """Stream response using OpenAI Response API with unified MCP/non-MCP processing."""
        # Clear streaming buffer at start (mixin respects _compression_retry)
        self._clear_streaming_buffer(**kwargs)
        agent_id = kwargs.get("agent_id", self.agent_id)

        try:
            async for chunk in super().stream_with_tools(messages, tools, **kwargs):
                yield chunk
        finally:
            # Save streaming buffer before cleanup
            self._finalize_streaming_buffer(agent_id=agent_id)

    def _append_tool_result_message(
        self,
        updated_messages: list[dict[str, Any]],
        call: dict[str, Any],
        result: Any,
        tool_type: str,
    ) -> None:
        """Append tool result to messages in Chat Completions format.

        Args:
            updated_messages: Message list to append to
            call: Tool call dictionary with call_id, name, arguments
            result: Tool execution result
            tool_type: "custom" or "mcp"
        """
        # Extract text from result - handle MCP CallToolResult objects properly
        if hasattr(result, "content") and not isinstance(result, (dict, str)):
            # MCP CallToolResult - extract text from content list
            extracted = self._extract_text_from_content(result.content)
            result_text = extracted if extracted is not None else str(result)
        else:
            result_text = getattr(result, "text", None) or str(result)

        function_output_msg = {
            "role": "tool",
            "tool_call_id": call.get("call_id", ""),
            "content": result_text,
        }
        updated_messages.append(function_output_msg)

        # Track tool result in streaming buffer for compression recovery
        tool_name = call.get("name", "unknown")
        self._append_tool_to_buffer(tool_name, result_text)

    def _append_tool_error_message(
        self,
        updated_messages: list[dict[str, Any]],
        call: dict[str, Any],
        error_msg: str,
        tool_type: str,
    ) -> None:
        """Append tool error to messages in Chat Completions format.

        Args:
            updated_messages: Message list to append to
            call: Tool call dictionary with call_id, name, arguments
            error_msg: Error message string
            tool_type: "custom" or "mcp"
        """
        error_output_msg = {
            "role": "tool",
            "tool_call_id": call.get("call_id", ""),
            "content": error_msg,
        }
        updated_messages.append(error_output_msg)

        # Track tool error in streaming buffer for compression recovery
        tool_name = call.get("name", "unknown")
        self._append_tool_to_buffer(tool_name, error_msg, is_error=True)

    async def _execute_custom_tool(self, call: dict[str, Any]) -> AsyncGenerator[CustomToolChunk]:
        """Execute custom tool with streaming support - async generator for base class.

        This method is called by _execute_tool_with_logging and yields CustomToolChunk
        objects for intermediate streaming output. The base class detects the async
        generator and streams intermediate results to users in real-time.

        Args:
            call: Tool call dictionary with name and arguments

        Yields:
            CustomToolChunk objects with streaming data

        Note:
            - Intermediate chunks (completed=False) are streamed to users in real-time
            - Final chunk (completed=True) contains the accumulated result for message history
            - The base class automatically handles extracting and displaying intermediate chunks
        """
        async for chunk in self.stream_custom_tool_execution(call):
            yield chunk

    def _customize_api_params(
        self,
        api_params: dict[str, Any],
        all_params: dict[str, Any],
    ) -> dict[str, Any]:
        """Hook for subclasses to modify API params before making the API call.

        Override this method to add provider-specific parameters to the API request.
        For example, GrokBackend uses this to add Grok Live Search parameters.

        Args:
            api_params: The API parameters built by the params handler
            all_params: All configuration parameters including backend config

        Returns:
            The modified api_params dict
        """
        return api_params

    def _deduplicate_tool_calls_in_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Deduplicate tool calls by ID to avoid 'duplicate tool_call id' errors in providers like Minimax.
        
        When recursively calling the API with updated_messages that contains assistant messages
        with tool_calls from prior iterations, we need to filter out tool_call IDs that were
        already seen in earlier messages to prevent the provider from seeing duplicate IDs.
        
        Args:
            messages: List of message dicts potentially containing tool_calls
            
        Returns:
            Messages with deduplicated tool_calls
        """
        if not messages:
            return messages
        
        seen_tool_call_ids = set()
        result_messages = []
        
        for msg in messages:
            # Make a copy to avoid modifying the original
            msg_copy = dict(msg)
            
            # If this message has tool_calls, filter out any IDs we've already seen
            if "tool_calls" in msg_copy and isinstance(msg_copy["tool_calls"], list):
                seen_before = []
                new_tool_calls = []
                
                for tool_call in msg_copy["tool_calls"]:
                    tool_call_id = tool_call.get("id")
                    if tool_call_id:
                        if tool_call_id in seen_tool_call_ids:
                            seen_before.append(tool_call_id)
                        else:
                            seen_tool_call_ids.add(tool_call_id)
                            new_tool_calls.append(tool_call)
                    else:
                        # Keep tool calls without IDs (shouldn't happen but be safe)
                        new_tool_calls.append(tool_call)
                
                # Log if we filtered any tool calls
                if seen_before:
                    logger.debug(
                        f"Filtered {len(seen_before)} duplicate tool_call IDs from assistant message: {seen_before}",
                    )
                
                # Only include tool_calls in the message if we have any left
                if new_tool_calls:
                    msg_copy["tool_calls"] = new_tool_calls
                else:
                    # Remove tool_calls key entirely if empty
                    msg_copy.pop("tool_calls", None)
            
            # Track tool_call_ids from tool result messages too
            if msg.get("role") == "tool" and "tool_call_id" in msg:
                seen_tool_call_ids.add(msg["tool_call_id"])
            
            result_messages.append(msg_copy)
        
        return result_messages


    async def _stream_with_custom_and_mcp_tools(
        self,
        current_messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        client,
        _compression_retry: bool = False,  # Prevents infinite loops on context errors
        **kwargs,
    ) -> AsyncGenerator[StreamChunk]:
        """Recursively stream responses, executing custom and MCP tool calls as needed.

        Args:
            current_messages: Messages to send to the API
            tools: Tool definitions
            client: OpenAI client
            _compression_retry: If True, this is a retry after compression (prevents loops)
            **kwargs: Additional parameters
        """

        # Build API params for this iteration
        # Internal parameters (starting with _) are filtered by the API params handler
        all_params = {**self.config, **kwargs}
        agent_id = kwargs.get("agent_id")
        api_params = await self.api_params_handler.build_api_params(current_messages, tools, all_params)

        # Enable usage tracking in streaming responses (required for token counting)
        if "stream" in api_params and api_params["stream"]:
            api_params["stream_options"] = {"include_usage": True}

        # OpenRouter: Enable cost tracking and web search plugin
        configure_openrouter_extra_body(api_params, all_params)

        # Add provider tools (web search, code interpreter) if enabled
        provider_tools = self.api_params_handler.get_provider_tools(all_params)

        if provider_tools:
            if "tools" not in api_params:
                api_params["tools"] = []
            api_params["tools"].extend(provider_tools)

        # Hook for subclasses to modify api_params before making the API call
        # Used by GrokBackend to add Grok Live Search parameters
        api_params = self._customize_api_params(api_params, all_params)

        # Start API call timing
        model = api_params.get("model", "unknown")
        provider = self.get_provider_name().lower()
        self.start_api_call_timing(model)

        # Wrap LLM API call with tracing for agent attribution
        with trace_llm_api_call(
            agent_id=agent_id or "unknown",
            provider=provider,
            model=model,
            operation="stream",
        ) as llm_span:
            # Start streaming - wrap with circuit breaker + context length handling
            try:

                async def _make_api_call():
                    return await client.chat.completions.create(**api_params)

                stream = await self.circuit_breaker.call_with_retry(
                    _make_api_call,
                    agent_id=agent_id,
                )
            except CircuitBreakerOpenError:
                self.end_api_call_timing(success=False, error="circuit_breaker_open")
                raise
            except Exception as e:
                if is_context_length_error(e) and not _compression_retry:
                    # Context length exceeded on initial request - compress and retry
                    llm_span.set_attribute("massgen.context_compression", True)
                    llm_span.set_attribute("massgen.compression_reason", "context_length_exceeded")
                    logger.warning(
                        f"[{self.get_provider_name()}] Context length exceeded on request, " f"triggering reactive compression: {e}",
                    )
                    self.end_api_call_timing(success=False, error=str(e))
                    yield StreamChunk(
                        type="status",
                        content="⚠️ Context limit reached, compressing conversation...",
                    )

                    # Compress messages and retry
                    compressed_messages = await self._compress_messages_for_context_recovery(
                        current_messages,
                        buffer_content=None,  # No partial response yet
                    )

                    # Retry with compressed messages (recursive call has its own trace)
                    async for chunk in self._stream_with_custom_and_mcp_tools(
                        compressed_messages,
                        tools,
                        client,
                        _compression_retry=True,  # Prevent infinite loops
                        **kwargs,
                    ):
                        yield chunk
                    return
                else:
                    self.end_api_call_timing(success=False, error=str(e))
                    raise  # Re-raise non-context errors or if already retried

        # Track function calls in this iteration
        captured_function_calls = []
        current_tool_calls = {}
        response_completed = False
        content = ""
        finish_reason_received = None  # Track finish reason to know when to expect usage
        usage_received_this_request = False  # Track if API returned usage for this specific request
        # Track reasoning_details for OpenRouter Gemini models
        reasoning_details = []

        async for chunk in stream:
            try:
                if hasattr(chunk, "choices") and chunk.choices:
                    choice = chunk.choices[0]

                    # Handle content delta
                    if hasattr(choice, "delta") and choice.delta:
                        delta = choice.delta

                        # Track if we've already captured reasoning this chunk to avoid duplicates
                        reasoning_captured_this_chunk = False

                        # Capture reasoning_details from delta (OpenRouter models)
                        # Check both direct attribute and model_extra (SDK may not parse custom fields)
                        delta_reasoning_details = getattr(delta, "reasoning_details", None)
                        if not delta_reasoning_details:
                            delta_extra = getattr(delta, "model_extra", None) or {}
                            delta_reasoning_details = delta_extra.get("reasoning_details")
                        if delta_reasoning_details:
                            reasoning_details.extend(delta_reasoning_details)
                            # Buffer reasoning details and yield as reasoning chunks
                            for detail in delta_reasoning_details:
                                # Handle both object and dict formats
                                # OpenRouter uses "summary" field, others use "text"
                                detail_text = None
                                if hasattr(detail, "text") and detail.text:
                                    detail_text = detail.text
                                elif hasattr(detail, "summary") and detail.summary:
                                    detail_text = detail.summary
                                elif isinstance(detail, dict):
                                    detail_text = detail.get("text") or detail.get("summary")
                                if detail_text:
                                    self._reasoning_active = True
                                    self._append_reasoning_to_buffer(detail_text)
                                    yield StreamChunk(
                                        type="reasoning",
                                        content=detail_text,
                                        reasoning_delta=detail_text,
                                    )
                                    reasoning_captured_this_chunk = True

                        # Capture reasoning_content from delta (DeepSeek, Qwen, Grok models via OpenRouter)
                        # Skip if we already captured reasoning_details to avoid duplicates
                        if not reasoning_captured_this_chunk and getattr(delta, "reasoning_content", None):
                            self._reasoning_active = True
                            reasoning_chunk = delta.reasoning_content
                            if reasoning_chunk:
                                self._append_reasoning_to_buffer(reasoning_chunk)
                                yield StreamChunk(
                                    type="reasoning",
                                    content=reasoning_chunk,
                                    reasoning_delta=reasoning_chunk,
                                )
                                reasoning_captured_this_chunk = True

                        # Capture reasoning field from delta (OpenRouter with include_reasoning=true)
                        # This is different from reasoning_content - used by DeepSeek R1 models
                        # Skip if we already captured reasoning to avoid duplicates
                        if not reasoning_captured_this_chunk:
                            delta_reasoning = getattr(delta, "reasoning", None)
                            if not delta_reasoning:
                                delta_extra = getattr(delta, "model_extra", None) or {}
                                delta_reasoning = delta_extra.get("reasoning")
                            if delta_reasoning:
                                self._reasoning_active = True
                                self._append_reasoning_to_buffer(delta_reasoning)
                                yield StreamChunk(
                                    type="reasoning",
                                    content=delta_reasoning,
                                    reasoning_delta=delta_reasoning,
                                )

                        # Plain text content
                        if getattr(delta, "content", None):
                            self.record_first_token()  # Record TTFT on first content
                            # Handle reasoning transition when content starts after reasoning
                            reasoning_chunk = self._handle_reasoning_transition()
                            if reasoning_chunk:
                                yield reasoning_chunk
                            content_chunk = delta.content
                            content += content_chunk
                            # Track content in streaming buffer for compression recovery
                            self._append_to_streaming_buffer(content_chunk)
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
                        finish_reason_received = choice.finish_reason
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

                            final_tool_calls = self._deduplicate_standard_tool_calls(
                                final_tool_calls,
                                source="chat_completions.streaming_finish_reason",
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

                            self._append_tool_call_to_buffer(final_tool_calls)
                            yield StreamChunk(type="tool_calls", tool_calls=final_tool_calls)

                            response_completed = True
                            # DON'T break yet - continue to capture usage chunk

                        elif choice.finish_reason in ["stop", "length"]:
                            response_completed = True
                            # DON'T return yet - continue to capture usage chunk

                # Handle usage metadata (comes after finish_reason)
                if hasattr(chunk, "usage") and chunk.usage:
                    usage_received_this_request = True
                    # Use standardized helper for comprehensive token tracking
                    self._update_token_usage_from_api_response(
                        chunk.usage,
                        all_params.get("model"),
                    )
                    # Now we can safely exit or continue based on finish reason
                    if finish_reason_received in ["stop", "length"]:
                        self.end_api_call_timing(success=True)
                        yield StreamChunk(type="done")
                        return
                    elif finish_reason_received == "tool_calls":
                        self.end_api_call_timing(success=True)
                        break  # Exit to execute functions

            except Exception as chunk_error:
                yield StreamChunk(type="error", error=f"Chunk processing error: {chunk_error}")
                continue

        # Fallback: if we exited the loop without getting usage (some providers don't send it)
        # Handle the "stop"/"length" case that might have been missed
        if finish_reason_received in ["stop", "length"] and response_completed:
            # Estimate tokens if API didn't return usage data for this request
            # (e.g., Grok, some OpenAI-compatible providers that don't support stream_options)
            if not usage_received_this_request and content:
                self._estimate_token_usage(
                    current_messages,
                    content,
                    all_params.get("model", "unknown"),
                )
            self.end_api_call_timing(success=True)
            yield StreamChunk(type="done")
            return

        # Execute any captured function calls
        if captured_function_calls and response_completed:
            captured_function_calls = self._deduplicate_captured_tool_calls(
                captured_function_calls,
                source="chat_completions.recursive_execution",
            )

            # Categorize function calls using base helper
            mcp_calls, custom_calls, provider_calls = self._categorize_tool_calls(captured_function_calls)

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
                # Skip MCP tool execution but continue with custom tools
                mcp_calls = []

            # Initialize for execution
            functions_executed = False
            updated_messages = current_messages.copy()
            processed_call_ids = set()  # Track processed calls

            # Check if planning mode is enabled - selectively block MCP tool execution during planning
            if self.is_planning_mode_enabled():
                blocked_tools = self.get_planning_mode_blocked_tools()

                if not blocked_tools:
                    # Empty set means block ALL MCP tools (backward compatible)
                    logger.info("[ChatCompletions] Planning mode enabled - blocking ALL MCP tool execution")
                    yield StreamChunk(
                        type="mcp_status",
                        status="planning_mode_blocked",
                        content="🚫 [MCP] Planning mode active - all MCP tools blocked during coordination",
                        source="planning_mode",
                    )
                    # Skip all MCP tool execution but still continue with workflow
                    mcp_calls = []
                else:
                    # Selective blocking - log but continue to check each tool individually
                    logger.info(f"[ChatCompletions] Planning mode enabled - selective blocking of {len(blocked_tools)} tools")

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
                    # Preserve reasoning_details for OpenRouter Gemini models
                    if reasoning_details:
                        assistant_message["reasoning_details"] = reasoning_details
                    updated_messages.append(assistant_message)

            # Create tool execution configuration objects
            custom_tool_config = ToolExecutionConfig(
                tool_type="custom",
                chunk_type="custom_tool_status",
                emoji_prefix="🔧 [Custom Tool]",
                success_emoji="✅ [Custom Tool]",
                error_emoji="❌ [Custom Tool Error]",
                source_prefix="custom_",
                status_called="custom_tool_called",
                status_response="custom_tool_response",
                status_error="custom_tool_error",
                execution_callback=self._execute_custom_tool,
            )

            mcp_tool_config = ToolExecutionConfig(
                tool_type="mcp",
                chunk_type="mcp_status",
                emoji_prefix="🔧 [MCP Tool]",
                success_emoji="✅ [MCP Tool]",
                error_emoji="❌ [MCP Tool Error]",
                source_prefix="mcp_",
                status_called="mcp_tool_called",
                status_response="mcp_tool_response",
                status_error="mcp_tool_error",
                execution_callback=self._execute_mcp_function_with_retry,
            )

            chunk_type_map = {
                "custom_tool_status": ChunkType.CUSTOM_TOOL_STATUS,
                "mcp_status": ChunkType.MCP_STATUS,
            }

            # Get provider name for logging
            provider_name = self.get_provider_name()

            def tool_config_for_call(call: dict[str, Any]) -> ToolExecutionConfig:
                return custom_tool_config if call["name"] in self._custom_tool_names else mcp_tool_config

            def chunk_adapter(chunk: StreamChunk) -> StreamChunk:
                return StreamChunk(
                    type=chunk_type_map.get(chunk.type, chunk.type),
                    status=getattr(chunk, "status", None),
                    content=getattr(chunk, "content", None),
                    source=getattr(chunk, "source", None),
                    hook_info=getattr(chunk, "hook_info", None),
                    tool_call_id=getattr(chunk, "tool_call_id", None),
                    display=getattr(chunk, "display", True),
                )

            nlip_available = self._nlip_enabled and self._nlip_router

            pending_custom_calls: list[dict[str, Any]] = []
            for call in custom_calls:
                if nlip_available:
                    logger.info(f"[NLIP] Using NLIP routing for custom tool {call['name']}")
                    try:
                        async for chunk in self._stream_tool_execution_via_nlip(
                            call,
                            custom_tool_config,
                            updated_messages,
                            processed_call_ids,
                        ):
                            functions_executed = True
                            yield chunk_adapter(chunk)
                        continue
                    except Exception as exc:
                        logger.warning(
                            f"[NLIP] Routing failed for {call['name']}: {exc}. Falling back to direct execution.",
                        )
                        async for chunk in self._execute_tool_with_logging(
                            call,
                            custom_tool_config,
                            updated_messages,
                            processed_call_ids,
                        ):
                            functions_executed = True
                            yield chunk_adapter(chunk)
                        continue

                reason = "disabled" if not self._nlip_enabled else "router unavailable"
                logger.info(
                    f"[Custom Tool] Direct execution for {call['name']} (NLIP {reason})",
                )
                pending_custom_calls.append(call)

            pending_mcp_calls: list[dict[str, Any]] = []
            for call in mcp_calls:
                if nlip_available:
                    logger.info(f"[NLIP] Using NLIP routing for MCP tool {call['name']}")
                    try:
                        async for chunk in self._stream_tool_execution_via_nlip(
                            call,
                            mcp_tool_config,
                            updated_messages,
                            processed_call_ids,
                        ):
                            functions_executed = True
                            yield chunk_adapter(chunk)
                        continue
                    except Exception as exc:
                        logger.warning(
                            f"[NLIP] Routing failed for {call['name']}: {exc}. Falling back to direct execution.",
                        )
                        async for chunk in self._execute_tool_with_logging(
                            call,
                            mcp_tool_config,
                            updated_messages,
                            processed_call_ids,
                        ):
                            functions_executed = True
                            yield chunk_adapter(chunk)
                        continue

                reason = "disabled" if not self._nlip_enabled else "router unavailable"
                logger.info(
                    f"[MCP Tool] Direct execution for {call['name']} (NLIP {reason})",
                )
                pending_mcp_calls.append(call)

            remaining_calls = pending_custom_calls + pending_mcp_calls

            if remaining_calls:
                async for adapted_chunk in self._execute_tool_calls(
                    all_calls=remaining_calls,
                    tool_config_for_call=tool_config_for_call,
                    all_params=all_params,
                    updated_messages=updated_messages,
                    processed_call_ids=processed_call_ids,
                    log_prefix=f"[{provider_name}]",
                    chunk_adapter=chunk_adapter,
                ):
                    functions_executed = True
                    yield adapted_chunk

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
                    functions_executed = True

            # Trim history after function executions to bound memory usage
            if functions_executed:
                updated_messages = self._trim_message_history(updated_messages)

                # Recursive call with updated messages
                # Deduplicate tool_call IDs before recursive API call to prevent provider errors
                updated_messages = self._deduplicate_tool_calls_in_messages(updated_messages)

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

    async def _process_stream(self, stream, all_params, agent_id) -> AsyncGenerator[StreamChunk]:
        """Handle standard Chat Completions API streaming format with logging."""

        # Note: Message tracking (_interrupted_stream_messages) is set by the caller
        # (_stream_without_custom_and_mcp_tools) BEFORE this method is called.
        # We only reset content tracking here, not messages.
        self._interrupted_stream_content = ""

        content = ""
        current_tool_calls = {}
        search_sources_used = 0
        provider_name = self.get_provider_name()
        enable_web_search = all_params.get("enable_web_search", False)
        log_prefix = f"backend.{provider_name.lower().replace(' ', '_')}"
        # Track reasoning_details for OpenRouter Gemini models
        reasoning_details = []

        async for chunk in stream:
            try:
                if hasattr(chunk, "choices") and chunk.choices:
                    choice = chunk.choices[0]

                    # Handle content delta
                    if hasattr(choice, "delta") and choice.delta:
                        delta = choice.delta

                        # Track if we've already captured reasoning this chunk to avoid duplicates
                        reasoning_captured_this_chunk = False

                        # Capture reasoning_details from delta (OpenRouter models)
                        # Check both direct attribute and model_extra (SDK may not parse custom fields)
                        delta_reasoning_details = getattr(delta, "reasoning_details", None)
                        if not delta_reasoning_details:
                            delta_extra = getattr(delta, "model_extra", None) or {}
                            delta_reasoning_details = delta_extra.get("reasoning_details")
                        if delta_reasoning_details:
                            reasoning_details.extend(delta_reasoning_details)
                            # Buffer reasoning details and yield as reasoning chunks
                            for detail in delta_reasoning_details:
                                # Handle both object and dict formats
                                # OpenRouter uses "summary" field, others use "text"
                                detail_text = None
                                if hasattr(detail, "text") and detail.text:
                                    detail_text = detail.text
                                elif hasattr(detail, "summary") and detail.summary:
                                    detail_text = detail.summary
                                elif isinstance(detail, dict):
                                    detail_text = detail.get("text") or detail.get("summary")
                                if detail_text:
                                    self._reasoning_active = True
                                    self._append_reasoning_to_buffer(detail_text)
                                    yield StreamChunk(
                                        type="reasoning",
                                        content=detail_text,
                                        reasoning_delta=detail_text,
                                    )
                                    reasoning_captured_this_chunk = True

                        # Provider-specific reasoning/thinking streams (non-standard OpenAI fields)
                        # Skip if we already captured reasoning_details to avoid duplicates
                        if not reasoning_captured_this_chunk and getattr(delta, "reasoning_content", None):
                            self._reasoning_active = True
                            thinking_delta = getattr(delta, "reasoning_content")
                            if thinking_delta:
                                log_stream_chunk(log_prefix, "reasoning", thinking_delta, agent_id)
                                self._append_reasoning_to_buffer(thinking_delta)
                                yield StreamChunk(
                                    type="reasoning",
                                    content=thinking_delta,
                                    reasoning_delta=thinking_delta,
                                )
                                reasoning_captured_this_chunk = True

                        # Capture reasoning field from delta (OpenRouter with include_reasoning=true)
                        # This is different from reasoning_content - used by DeepSeek R1 models
                        # Skip if we already captured reasoning to avoid duplicates
                        if not reasoning_captured_this_chunk:
                            delta_reasoning = getattr(delta, "reasoning", None)
                            if not delta_reasoning:
                                delta_extra = getattr(delta, "model_extra", None) or {}
                                delta_reasoning = delta_extra.get("reasoning")
                            if delta_reasoning:
                                self._reasoning_active = True
                                log_stream_chunk(log_prefix, "reasoning", delta_reasoning, agent_id)
                                self._append_reasoning_to_buffer(delta_reasoning)
                                yield StreamChunk(
                                    type="reasoning",
                                    content=delta_reasoning,
                                    reasoning_delta=delta_reasoning,
                                )

                        # Plain text content
                        if getattr(delta, "content", None):
                            self.record_first_token()  # Record TTFT on first content
                            # handle reasoning first
                            reasoning_chunk = self._handle_reasoning_transition(log_prefix, agent_id)
                            if reasoning_chunk:
                                yield reasoning_chunk
                            content_chunk = delta.content
                            content += content_chunk
                            # Track content in streaming buffer for compression recovery
                            self._append_to_streaming_buffer(content_chunk)
                            # Track content for interrupted stream estimation
                            self._interrupted_stream_content = content
                            log_backend_agent_message(
                                agent_id or "default",
                                "RECV",
                                {"content": content_chunk},
                                backend_name=provider_name,
                            )
                            log_stream_chunk(log_prefix, "content", content_chunk, agent_id)
                            yield StreamChunk(type="content", content=content_chunk)

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

                            final_tool_calls = self._deduplicate_standard_tool_calls(
                                final_tool_calls,
                                source="chat_completions.standard_stream_finish_reason",
                            )

                            log_stream_chunk(log_prefix, "tool_calls", final_tool_calls, agent_id)
                            self._append_tool_call_to_buffer(final_tool_calls)
                            yield StreamChunk(type="tool_calls", tool_calls=final_tool_calls)

                            complete_message = {
                                "role": "assistant",
                                "content": content.strip(),
                                "tool_calls": final_tool_calls,
                            }
                            # Preserve reasoning_details for OpenRouter Gemini models
                            if reasoning_details:
                                complete_message["reasoning_details"] = reasoning_details

                            yield StreamChunk(
                                type="complete_message",
                                complete_message=complete_message,
                            )
                            # DON'T yield done yet - wait for usage chunk first
                            # (OpenAI-compatible APIs send usage in a final chunk after finish_reason)
                            # The done chunk will be yielded after usage is captured below

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
                            # DON'T yield done yet - wait for usage chunk first
                            # (OpenAI-compatible APIs send usage in a final chunk after finish_reason)
                            # The done chunk will be yielded after usage is captured below

                # Optionally handle usage metadata
                if hasattr(chunk, "usage") and chunk.usage:
                    # Mark that we received usage - no estimation needed for this stream
                    self._stream_usage_received = True
                    self._interrupted_stream_content = ""  # Clear tracking

                    # Use standardized helper for comprehensive token tracking
                    self._update_token_usage_from_api_response(
                        chunk.usage,
                        all_params.get("model", "gpt-4o"),
                    )

                    # Handle web search metadata
                    if getattr(chunk.usage, "num_sources_used", 0) > 0:
                        search_sources_used = chunk.usage.num_sources_used
                        if enable_web_search:
                            search_msg = f"\n📊 [Live Search] Using {search_sources_used} sources for real-time data\n"
                            log_stream_chunk(log_prefix, "content", search_msg, agent_id)
                            yield StreamChunk(
                                type="content",
                                content=search_msg,
                            )

                    # After receiving usage, yield done and exit
                    # (this is the final chunk that comes after finish_reason)
                    self.end_api_call_timing(success=True)
                    log_stream_chunk(log_prefix, "done", None, agent_id)
                    yield StreamChunk(type="done")
                    return  # Exit completely after usage is captured

            except Exception as chunk_error:
                error_msg = f"Chunk processing error: {chunk_error}"
                log_stream_chunk(log_prefix, "error", error_msg, agent_id)
                yield StreamChunk(type="error", error=error_msg)
                continue

        # Fallback estimation for local models that don't return usage data
        # (e.g., LMStudio, vLLM without usage tracking enabled)
        if content and self.token_usage.input_tokens == 0 and self.token_usage.output_tokens == 0:
            # Note: We don't have access to messages here, so we estimate output only
            # Input tokens will be 0 but output will be estimated from content
            self._estimate_token_usage(
                [],  # Empty messages - we can't access them from this method
                content,
                all_params.get("model", "gpt-4o"),
            )

        # Fallback in case stream ends without finish_reason
        self.end_api_call_timing(success=True)
        log_stream_chunk(log_prefix, "done", None, agent_id)
        yield StreamChunk(type="done")

    def create_tool_result_message(self, tool_call: dict[str, Any], result_content: str) -> dict[str, Any]:
        """Create tool result message for Chat Completions format."""
        tool_call_id = self.extract_tool_call_id(tool_call)
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result_content,
        }

    def extract_tool_result_content(self, tool_result_message: dict[str, Any]) -> str:
        """Extract content from Chat Completions tool result message."""
        return tool_result_message.get("content", "")

    def _convert_messages_for_mcp_chat_completions(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        elif "nvidia.com" in base_url:
            return "Nvidia NIM"
        elif "poe.com" in base_url:
            return "POE"
        elif "aliyuncs.com" in base_url:
            return "Qwen"
        else:
            return "ChatCompletion"

    def get_filesystem_support(self) -> FilesystemSupport:
        """Chat Completions supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def get_supported_builtin_tools(self) -> list[str]:
        """Get list of builtin tools supported by this provider."""
        # Chat Completions API doesn't typically support builtin tools like web_search
        # But some providers might - this can be overridden in subclasses
        return []

    def _create_client(self, **kwargs) -> AsyncOpenAI:
        """Create OpenAI client with consistent configuration."""
        import openai

        all_params = {**self.config, **kwargs}
        base_url = all_params.get("base_url", "https://api.openai.com/v1")
        client = openai.AsyncOpenAI(api_key=self.api_key, base_url=base_url)
        # Instrument client for Logfire observability if enabled
        try:
            from massgen.structured_logging import get_tracer, is_observability_enabled

            if is_observability_enabled():
                get_tracer().instrument_openai(client)
        except ImportError:
            pass  # structured_logging module not available
        except Exception as e:
            logger.warning(f"Failed to instrument OpenAI client for observability: {e}")
        return client

    def _handle_reasoning_transition(self, log_prefix: str = "", agent_id: str | None = None) -> StreamChunk | None:
        """Handle reasoning state transition and return StreamChunk if transition occurred."""
        if self._reasoning_active:
            self._reasoning_active = False
            log_stream_chunk(log_prefix, "reasoning_done", "", agent_id)
            return StreamChunk(type="reasoning_done", content="")
        return None
