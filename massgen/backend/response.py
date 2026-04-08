"""
Response API backend implementation with multimodal support.
Standalone implementation optimized for the standard Response API format (originated by OpenAI).
Supports image input (URL and base64) and image generation via tools.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import openai
from openai import AsyncOpenAI

from ..api_params_handler import (
    OpenAIOperatorAPIParamsHandler,
    ResponseAPIParamsHandler,
)
from ..formatter import ResponseFormatter
from ..logger_config import log_backend_agent_message, log_stream_chunk, logger
from ..stream_chunk import ChunkType, TextStreamChunk
from ._streaming_buffer_mixin import StreamingBufferMixin
from .base import FilesystemSupport, StreamChunk
from .base_with_custom_tool_and_mcp import (
    CustomToolAndMCPBackend,
    CustomToolChunk,
    ToolExecutionConfig,
    UploadFileError,
)
from .llm_circuit_breaker import (
    CircuitBreakerOpenError,
    LLMCircuitBreaker,
    LLMCircuitBreakerConfig,
)


class _WSEvent:
    """Adapter that exposes websocket JSON events like SDK response objects."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    @staticmethod
    def _wrap(value: Any) -> Any:
        if isinstance(value, dict):
            return _WSEvent(value)
        if isinstance(value, list):
            return [_WSEvent(item) if isinstance(item, dict) else item for item in value]
        return value

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name not in self._data:
            raise AttributeError(name)
        return self._wrap(self._data[name])

    def __getitem__(self, key: str) -> Any:
        return self._wrap(self._data[key])

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __iter__(self):
        return iter(self._data)

    def __bool__(self) -> bool:
        return bool(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._wrap(self._data.get(key, default))

    def model_dump(self) -> dict[str, Any]:
        return self._data

    def __repr__(self) -> str:
        return f"_WSEvent({self._data.get('type', '?')})"


class ResponseBackend(StreamingBufferMixin, CustomToolAndMCPBackend):
    """Backend using the standard Response API format with multimodal support."""

    _XAI_X_SEARCH_CUSTOM_TOOL_CALL_ID_PREFIX = "xs_"
    _XAI_X_SEARCH_CUSTOM_TOOL_NAME_PREFIX = "x_"

    def __init__(self, api_key: str | None = None, **kwargs):
        # Extract circuit breaker config before passing to super
        cb_config = self._build_circuit_breaker_config(kwargs)
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.formatter = ResponseFormatter()

        # Initialize API params handler after custom_tool_manager
        # Use OpenAIOperatorAPIParamsHandler for computer-use-preview model
        model = kwargs.get("model", "")
        if "computer-use-preview" in model:
            self.api_params_handler = OpenAIOperatorAPIParamsHandler(self)
        else:
            self.api_params_handler = ResponseAPIParamsHandler(self)

        self._websocket_mode = kwargs.get("websocket_mode", False)

        # Queue for pending image saves
        self._pending_image_saves = []

        # File Search tracking for cleanup
        self._vector_store_ids: list[str] = []
        self._uploaded_file_ids: list[str] = []

        # xAI currently surfaces some builtin tools as custom_tool_call items.
        # Keep minimal per-stream state so we can label midstream input chunks.
        self._xai_custom_tool_names_by_call_id: dict[str, str] = {}
        self._xai_custom_tool_inputs_by_call_id: dict[str, str] = {}
        self._xai_custom_tool_calls_reported: set[str] = set()

        # Note: _streaming_buffer is provided by StreamingBufferMixin
        self.circuit_breaker = LLMCircuitBreaker(
            config=cb_config,
            backend_name="response_api",
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

    def _reset_provider_tool_state(self) -> None:
        """Clear per-stream provider tool state."""
        self._xai_custom_tool_names_by_call_id.clear()
        self._xai_custom_tool_inputs_by_call_id.clear()
        self._xai_custom_tool_calls_reported.clear()

    def supports_upload_files(self) -> bool:
        return True

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk]:
        """Stream response using OpenAI Response API with unified MCP/non-MCP processing.

        Wraps parent implementation to ensure File Search cleanup happens after streaming completes.
        """
        # Clear streaming buffer at start of new stream (mixin respects _compression_retry)
        self._clear_streaming_buffer(**kwargs)
        self._reset_provider_tool_state()
        agent_id = kwargs.get("agent_id", self.agent_id)

        ws_transport = None
        if self._websocket_mode:
            try:
                from ._websocket_transport import WebSocketResponseTransport

                ws_url = None
                base_url = self.config.get("base_url")
                if base_url:
                    # Convert HTTP base URL to WebSocket URL
                    ws_base = base_url.replace("https://", "wss://").replace(
                        "http://",
                        "ws://",
                    )
                    ws_url = ws_base.rstrip("/") + "/responses"

                ws_transport = WebSocketResponseTransport(
                    api_key=self.api_key or "",
                    organization=self.config.get("organization") or os.getenv("OPENAI_ORG_ID"),
                    **({"url": ws_url} if ws_url else {}),
                )
                await ws_transport.connect()
                kwargs["_ws_transport"] = ws_transport
                logger.info(
                    "[WebSocket] Transport active for this stream_with_tools call",
                )
            except Exception as e:
                logger.warning(
                    f"[WebSocket] Failed to establish connection: {e}. Falling back to HTTP mode.",
                )
                ws_transport = None
                # Ensure the params handler builds HTTP-mode params (stream=True)
                # instead of websocket-mode params (stream omitted).
                kwargs["websocket_mode"] = False

        try:
            async for chunk in super().stream_with_tools(messages, tools, **kwargs):
                yield chunk
        finally:
            # Save streaming buffer before cleanup
            self._finalize_streaming_buffer(agent_id=agent_id)
            # Cleanup File Search resources after stream completes
            await self._cleanup_file_search_if_needed(**kwargs)
            if ws_transport is not None:
                await ws_transport.close()

    async def _cleanup_file_search_if_needed(self, **kwargs) -> None:
        """Cleanup File Search resources if needed."""
        if not (self._vector_store_ids or self._uploaded_file_ids):
            return

        agent_id = kwargs.get("agent_id")
        logger.info("Cleaning up File Search resources...")

        client = None
        try:
            # Create a client for cleanup
            client = self._create_client(**kwargs)
            await self._cleanup_file_search_resources(client, agent_id)
        except Exception as cleanup_error:
            logger.error(
                f"Error during File Search cleanup: {cleanup_error}",
                extra={"agent_id": agent_id},
            )
        finally:
            # Close the client if it has an aclose method
            if client and hasattr(client, "aclose"):
                try:
                    await client.aclose()
                except Exception:
                    pass

    async def _stream_without_custom_and_mcp_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk]:
        agent_id = kwargs.get("agent_id")
        # Filter out internal flags that shouldn't be passed to API
        filtered_kwargs = {k: v for k, v in kwargs.items() if not k.startswith("_compression") and not k.startswith("_ws_")}
        all_params = {**self.config, **filtered_kwargs}

        processed_messages = await self._process_upload_files(messages, all_params)

        if all_params.get("_has_file_search_files"):
            logger.info("Processing File Search uploads...")
            processed_messages, vector_store_id = await self._upload_files_and_create_vector_store(
                processed_messages,
                client,
                agent_id,
            )
            if vector_store_id:
                existing_ids = list(all_params.get("_file_search_vector_store_ids", []))
                existing_ids.append(vector_store_id)
                all_params["_file_search_vector_store_ids"] = existing_ids
                logger.info(f"File Search enabled with vector store: {vector_store_id}")
            all_params.pop("_has_file_search_files", None)

        api_params = await self.api_params_handler.build_api_params(processed_messages, tools, all_params)

        if "tools" in api_params:
            non_mcp_tools = []
            for tool in api_params.get("tools", []):
                if tool.get("type") == "function":
                    name = tool.get("function", {}).get("name") if "function" in tool else tool.get("name")
                    if name and name in self._mcp_function_names:
                        continue
                    if name and name in self._custom_tool_names:
                        continue
                elif tool.get("type") == "mcp":
                    continue
                non_mcp_tools.append(tool)
            api_params["tools"] = non_mcp_tools

        # Check for compression retry flag to prevent infinite loops
        _compression_retry = kwargs.get("_compression_retry", False)
        ws_transport = kwargs.get("_ws_transport")

        # Start API call timing for non-MCP path
        model = api_params.get("model", "unknown")
        self.start_api_call_timing(model)

        try:
            stream = await self._create_response_stream(
                api_params,
                client,
                ws_transport,
                agent_id=agent_id,
            )
        except CircuitBreakerOpenError:
            self.end_api_call_timing(success=False, error="circuit_breaker_open")
            raise
        except Exception as e:
            # Debug: Catch input[N].content format errors and print the problematic message
            error_str = str(e)
            if "input[" in error_str and "].content" in error_str:
                import re

                match = re.search(r"input\[(\d+)\]\.content", error_str)
                if match:
                    idx = int(match.group(1))
                    input_messages = api_params.get("input", [])
                    if idx < len(input_messages):
                        problematic_msg = input_messages[idx]
                        logger.error(f"[Response API] Message format error at input[{idx}]:")
                        logger.error(f"[Response API] Full message:\n{json.dumps(problematic_msg, indent=2, default=str)}")
                    else:
                        logger.error(f"[Response API] Error at input[{idx}] but only {len(input_messages)} messages in input")

            # Check if this is a context length error and we haven't already retried
            from ._context_errors import is_context_length_error

            if is_context_length_error(e) and not _compression_retry:
                self.end_api_call_timing(success=False, error=str(e))
                logger.warning(
                    f"[{self.get_provider_name()}] Context length exceeded, " f"attempting compression recovery...",
                )

                # Notify user that compression is starting
                yield StreamChunk(
                    type="compression_status",
                    status="compressing",
                    content=f"\n📦 [Compression] Context limit exceeded - compressing {len(processed_messages)} messages...",
                    source=agent_id,
                )

                # Compress messages and retry
                # Include accumulated buffer content if available (may have content from prior calls)
                buffer_for_compression = self._get_streaming_buffer()

                # Compress messages using LLM-based summarization
                compressed_messages = await self._compress_messages_for_context_recovery(
                    processed_messages,
                    buffer_content=buffer_for_compression,
                )

                # Remove previous_response_id - it would add all prior context server-side,
                # making compression pointless
                compression_params = {k: v for k, v in all_params.items() if k != "previous_response_id"}
                api_params = await self.api_params_handler.build_api_params(
                    compressed_messages,
                    tools,
                    compression_params,
                )

                # Retry with compressed context
                stream = await self._create_response_stream(
                    api_params,
                    client,
                    ws_transport,
                    agent_id=agent_id,
                )

                # Notify user that compression succeeded
                input_count = len(compressed_messages) if compressed_messages else 0
                result_msg = f"✅ [Compression] Recovered via summarization ({input_count} items) - continuing..."
                yield StreamChunk(
                    type="compression_status",
                    status="compression_complete",
                    content=result_msg,
                    source=agent_id,
                )

                logger.info(
                    f"[{self.get_provider_name()}] Compression recovery successful via summarization " f"({input_count} items)",
                )
            else:
                self.end_api_call_timing(success=False, error=str(e))
                raise

        async for chunk in self._process_stream(stream, all_params, agent_id):
            yield chunk

    @staticmethod
    def _get_response_item_field(item: Any, field: str, default: Any = None) -> Any:
        """Read a field from either an SDK object or a plain dict."""
        if isinstance(item, dict):
            return item.get(field, default)
        return getattr(item, field, default)

    @staticmethod
    def _parse_response_item_json(value: Any) -> dict[str, Any]:
        """Parse a JSON-ish input payload from a provider output item."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value:
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _is_xai_x_search_custom_tool_item(self, item: Any) -> bool:
        """Return True when xAI surfaces X search as provider custom_tool_call items.

        xAI's Responses API currently emits X search work as ``custom_tool_call``
        items (for example ``x_keyword_search`` and ``x_thread_fetch``) rather
        than the ``response.x_search_call.*`` events we initially expected.
        """
        if self.get_provider_name() != "Grok":
            return False
        if self._get_response_item_field(item, "type") != "custom_tool_call":
            return False
        name = self._get_response_item_field(item, "name", "") or ""
        call_id = self._get_response_item_field(item, "call_id", "") or ""
        return call_id.startswith(self._XAI_X_SEARCH_CUSTOM_TOOL_CALL_ID_PREFIX) or name.startswith(
            self._XAI_X_SEARCH_CUSTOM_TOOL_NAME_PREFIX,
        )

    def _record_xai_custom_tool_start(self, item: Any) -> None:
        """Track xAI custom tool call metadata for subsequent input delta events."""
        if not self._is_xai_x_search_custom_tool_item(item):
            return
        call_id = self._get_response_item_field(item, "call_id", "") or ""
        name = self._get_response_item_field(item, "name", "") or ""
        if call_id and name:
            self._xai_custom_tool_names_by_call_id[call_id] = name

    def _format_xai_x_search_custom_tool_input_chunk(
        self,
        call_id: str,
        payload: dict[str, Any],
        agent_id: str | None,
    ) -> TextStreamChunk | None:
        """Format a midstream xAI custom tool input payload when enough is known."""
        tool_name = self._xai_custom_tool_names_by_call_id.get(call_id, "")
        if not tool_name:
            if payload.get("post_id"):
                tool_name = "x_thread_fetch"
            elif payload.get("query"):
                tool_name = "x_search"
            else:
                return None

        if call_id in self._xai_custom_tool_calls_reported:
            return None

        if not (payload.get("query") or payload.get("post_id")):
            return None

        self._xai_custom_tool_calls_reported.add(call_id)
        return self._format_xai_x_search_custom_tool_chunk(
            {
                "name": tool_name,
                "input": payload,
            },
            agent_id,
        )

    def _format_xai_x_search_custom_tool_chunk(
        self,
        item: Any,
        agent_id: str | None,
        *,
        strip_newlines: bool = False,
    ) -> TextStreamChunk:
        """Format xAI provider custom tool items into user-visible stream chunks."""
        tool_name = self._get_response_item_field(item, "name", "x_search")
        payload = self._parse_response_item_json(self._get_response_item_field(item, "input"))
        query = payload.get("query", "")
        post_id = payload.get("post_id", "")

        if tool_name in {"x_keyword_search", "x_semantic_search"}:
            if query:
                log_stream_chunk("backend.response", "x_search_query", query, agent_id)
                content = f"\n🔎 [X Search Query] '{query}' via {tool_name}\n"
            else:
                log_stream_chunk("backend.response", "x_search", f"Running {tool_name}", agent_id)
                content = f"\n🔎 [Provider Tool: X Search] Running {tool_name}...\n"
        elif tool_name in {"x_thread_fetch", "x_post_fetch"}:
            if post_id:
                log_stream_chunk("backend.response", "x_thread_fetch", post_id, agent_id)
                content = f"\n🧵 [X Thread Fetch] {post_id}\n"
            else:
                log_stream_chunk("backend.response", "x_thread_fetch", f"Running {tool_name}", agent_id)
                content = f"\n🧵 [X Thread Fetch] Running {tool_name}...\n"
        else:
            log_stream_chunk("backend.response", "x_search", f"Running {tool_name}", agent_id)
            content = f"\n🔎 [Provider Tool: X Search] Running {tool_name}...\n"

        if strip_newlines:
            content = content.strip("\n")

        return TextStreamChunk(
            type=ChunkType.CONTENT,
            content=content,
            source="response_api",
        )

    def _append_tool_result_message(
        self,
        updated_messages: list[dict[str, Any]],
        call: dict[str, Any],
        result: Any,
        tool_type: str,
    ) -> None:
        """Append tool result to messages in Response API format.

        Args:
            updated_messages: Message list to append to
            call: Tool call dictionary with call_id, name, arguments
            result: Tool execution result
            tool_type: "custom" or "mcp"

        Note:
            For reasoning models (GPT-5, o3, o4-mini), function_call items are already
            included via response_output_items. We only add function_call_output here.
            The function_call is already present from response.output to maintain
            reasoning item continuity.
        """
        # Extract text from result - handle MCP CallToolResult objects properly
        if hasattr(result, "content") and not isinstance(result, (dict, str)):
            # MCP CallToolResult - extract text from content list
            extracted = self._extract_text_from_content(result.content)
            result_text = extracted if extracted is not None else str(result)
        else:
            result_text = getattr(result, "text", None) or str(result)

        # Only add function output message
        # function_call is already included from response.output (with reasoning items)
        function_output_msg = {
            "type": "function_call_output",
            "call_id": call.get("call_id", ""),
            "output": result_text,
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
        """Append tool error to messages in Response API format.

        Args:
            updated_messages: Message list to append to
            call: Tool call dictionary with call_id, name, arguments
            error_msg: Error message string
            tool_type: "custom" or "mcp"

        Note:
            For reasoning models (GPT-5, o3, o4-mini), function_call items are already
            included via response_output_items. We only add function_call_output here.
            The function_call is already present from response.output to maintain
            reasoning item continuity.
        """
        # Only add error output message
        # function_call is already included from response.output (with reasoning items)
        error_output_msg = {
            "type": "function_call_output",
            "call_id": call.get("call_id", ""),
            "output": error_msg,
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

    async def _stream_with_custom_and_mcp_tools(
        self,
        current_messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk]:
        """Recursively stream MCP responses, executing function calls as needed."""

        agent_id = kwargs.get("agent_id")

        # Build API params for this iteration
        # Filter out internal flags that shouldn't be passed to API
        filtered_kwargs = {k: v for k, v in kwargs.items() if not k.startswith("_compression") and not k.startswith("_ws_")}
        all_params = {**self.config, **filtered_kwargs}

        if all_params.get("_has_file_search_files"):
            logger.info("Processing File Search uploads...")
            current_messages, vector_store_id = await self._upload_files_and_create_vector_store(
                current_messages,
                client,
                agent_id,
            )
            if vector_store_id:
                existing_ids = list(all_params.get("_file_search_vector_store_ids", []))
                existing_ids.append(vector_store_id)
                all_params["_file_search_vector_store_ids"] = existing_ids
                logger.info(f"File Search enabled with vector store: {vector_store_id}")
            all_params.pop("_has_file_search_files", None)

        api_params = await self.api_params_handler.build_api_params(current_messages, tools, all_params)

        # Start API call timing
        model = api_params.get("model", "unknown")
        self.start_api_call_timing(model)

        # Check for compression retry flag to prevent infinite loops
        _compression_retry = kwargs.get("_compression_retry", False)
        ws_transport = kwargs.get("_ws_transport")

        # Start streaming with context error handling
        try:
            stream = await self._create_response_stream(
                api_params,
                client,
                ws_transport,
                agent_id=agent_id,
            )
        except CircuitBreakerOpenError:
            self.end_api_call_timing(success=False, error="circuit_breaker_open")
            raise
        except Exception as e:
            # Debug: Catch input[N].content format errors and print the problematic message
            error_str = str(e)
            if "input[" in error_str and "].content" in error_str:
                import re

                match = re.search(r"input\[(\d+)\]\.content", error_str)
                if match:
                    idx = int(match.group(1))
                    input_messages = api_params.get("input", [])
                    if idx < len(input_messages):
                        problematic_msg = input_messages[idx]
                        logger.error(f"[Response API] Message format error at input[{idx}]:")
                        logger.error(f"[Response API] Full message:\n{json.dumps(problematic_msg, indent=2, default=str)}")
                    else:
                        logger.error(f"[Response API] Error at input[{idx}] but only {len(input_messages)} messages in input")

            # Check if this is a context length error and we haven't already retried
            from ._context_errors import is_context_length_error

            if is_context_length_error(e) and not _compression_retry:
                logger.warning(
                    f"[{self.get_provider_name()}] Context length exceeded in MCP mode, " f"attempting compression recovery...",
                )
                self.end_api_call_timing(success=False, error=str(e))

                # Notify user that compression is starting
                yield StreamChunk(
                    type="compression_status",
                    status="compressing",
                    content=f"\n📦 [Compression] Context limit exceeded - compressing {len(current_messages)} messages...",
                    source=agent_id,
                )

                # Compress messages and retry
                # Include accumulated buffer content if available (not first API call)
                buffer_for_compression = self._get_streaming_buffer()

                # Compress messages using LLM-based summarization
                compressed_messages = await self._compress_messages_for_context_recovery(
                    current_messages,
                    buffer_content=buffer_for_compression,
                )

                # Remove previous_response_id - it would add all prior context server-side,
                # making compression pointless
                compression_params = {k: v for k, v in all_params.items() if k != "previous_response_id"}
                api_params = await self.api_params_handler.build_api_params(
                    compressed_messages,
                    tools,
                    compression_params,
                )

                # Update current_messages for subsequent recursions
                current_messages = compressed_messages

                # Retry with compressed context
                stream = await self._create_response_stream(
                    api_params,
                    client,
                    ws_transport,
                    agent_id=agent_id,
                )

                # Notify user that compression succeeded
                input_count = len(compressed_messages) if compressed_messages else 0
                result_msg = f"✅ [Compression] Recovered via summarization ({input_count} items) - continuing..."
                yield StreamChunk(
                    type="compression_status",
                    status="compression_complete",
                    content=result_msg,
                    source=agent_id,
                )

                logger.info(
                    f"[{self.get_provider_name()}] Compression recovery successful via summarization " f"({input_count} items)",
                )
            else:
                self.end_api_call_timing(success=False, error=str(e))
                raise

        # Track function calls in this iteration
        captured_function_calls = []
        current_function_call = None
        response_completed = False
        response_id = None  # Track response ID for reasoning continuity
        response_output_items = []  # Track ALL output items (reasoning, messages, function_calls)

        try:
            async for chunk in stream:
                if hasattr(chunk, "type"):
                    # Detect function call start
                    if chunk.type == "response.output_item.added" and hasattr(chunk, "item") and chunk.item and getattr(chunk.item, "type", None) == "function_call":
                        current_function_call = {
                            "call_id": getattr(chunk.item, "call_id", ""),
                            "name": getattr(chunk.item, "name", ""),
                            "arguments": "",
                        }
                        logger.info(
                            f"Function call detected: {current_function_call['name']}",
                        )

                    # Accumulate function arguments
                    elif chunk.type == "response.function_call_arguments.delta" and current_function_call is not None:
                        delta = getattr(chunk, "delta", "")
                        current_function_call["arguments"] += delta

                    # Function call completed
                    elif chunk.type == "response.output_item.done" and current_function_call is not None:
                        captured_function_calls.append(current_function_call)
                        current_function_call = None

                    # Handle regular content and other events
                    elif chunk.type == "response.output_text.delta":
                        self.record_first_token()  # Record TTFT on first content
                        delta = getattr(chunk, "delta", "")
                        # Track content in streaming buffer for compression recovery
                        self._append_to_streaming_buffer(delta)
                        # Record content chunk for LLM call logging
                        yield TextStreamChunk(
                            type=ChunkType.CONTENT,
                            content=delta,
                            source="response_api",
                        )

                    # Handle other streaming events (reasoning, provider tools, etc.)
                    else:
                        result = self._process_stream_chunk(chunk, agent_id)
                        yield result

                    # Response failed - terminal error state
                    if chunk.type == "response.failed":
                        error_msg = getattr(result, "error", None) or "Response failed"
                        self.end_api_call_timing(success=False, error=error_msg)
                        return

                    # Response completed
                    if chunk.type in ["response.completed", "response.incomplete"]:
                        response_completed = True
                        # Note: Usage tracking is handled in _process_stream_chunk() above
                        # Capture response ID and ALL output items for reasoning continuity
                        if hasattr(chunk, "response") and chunk.response:
                            response_id = getattr(chunk.response, "id", None)
                            if response_id:
                                logger.debug(
                                    f"Captured response ID for reasoning continuity: {response_id}",
                                )
                            # CRITICAL: Capture ALL output items (reasoning, function_call, message)
                            # These must be included in the next request for reasoning models
                            output = getattr(chunk.response, "output", [])
                            if output:
                                for item in output:
                                    # Convert to dict format for the API
                                    item_dict = self._convert_to_dict(item) if hasattr(item, "model_dump") or hasattr(item, "dict") else item
                                    if isinstance(item_dict, dict):
                                        response_output_items.append(item_dict)
                                logger.debug(
                                    f"Captured {len(response_output_items)} output items for reasoning continuity",
                                )
                        if captured_function_calls:
                            # Execute captured function calls and recurse
                            self.end_api_call_timing(success=True)
                            break  # Exit chunk loop to execute functions
                        else:
                            # No function calls, we're done (base case)
                            self.end_api_call_timing(success=True)
                            yield TextStreamChunk(
                                type=ChunkType.DONE,
                                source="response_api",
                            )
                            return
        except Exception as e:
            # Mid-stream error (e.g., websocket disconnect) - fail cleanly with one error chunk
            error_msg = str(e) or "Stream interrupted"
            logger.error(f"[Response API] Mid-stream error: {error_msg}")
            self.end_api_call_timing(success=False, error=error_msg)
            yield TextStreamChunk(
                type=ChunkType.ERROR,
                error=error_msg,
                source="response_api",
            )
            return

        # Execute any captured function calls
        if captured_function_calls and response_completed:
            captured_function_calls = self._deduplicate_captured_tool_calls(
                captured_function_calls,
                source="response.output_items",
            )

            # Categorize function calls using helper method
            mcp_calls, custom_calls, provider_calls = self._categorize_tool_calls(captured_function_calls)

            # If there are provider calls (non-MCP, non-custom), emit them as tool_calls
            # for the orchestrator to process (workflow tools like new_answer, vote)
            if provider_calls:
                logger.info(f"Provider function calls detected: {[call['name'] for call in provider_calls]}. Emitting for orchestrator.")

                # Convert provider calls to tool_calls format for orchestrator
                workflow_tool_calls = []
                for call in provider_calls:
                    tool_name = call.get("name", "")
                    tool_args = call.get("arguments", {})

                    # Parse arguments if they're a string
                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except json.JSONDecodeError:
                            tool_args = {}

                    # Build tool call in standard format
                    workflow_tool_calls.append(
                        {
                            "id": call.get("call_id", f"call_{len(workflow_tool_calls)}"),
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": tool_args,
                            },
                        },
                    )

                # Emit tool_calls chunk for orchestrator to process
                if workflow_tool_calls:
                    log_stream_chunk("backend.response", "tool_calls", workflow_tool_calls, kwargs.get("agent_id"))
                    self._append_tool_call_to_buffer(workflow_tool_calls)
                    yield TextStreamChunk(
                        type=ChunkType.TOOL_CALLS,
                        tool_calls=workflow_tool_calls,
                        source="response_api",
                    )

                yield TextStreamChunk(type=ChunkType.DONE, source="response_api")
                return

            # Initialize for execution
            functions_executed = False
            updated_messages = current_messages.copy()
            new_items_start_index = len(updated_messages)  # Track where new items begin
            processed_call_ids = set()  # Initialize processed_call_ids here

            # CRITICAL: Include ALL response output items (reasoning, function_calls, messages)
            # This is required for reasoning models like GPT-5, o3, o4-mini
            # Without reasoning items, subsequent API calls will fail with:
            # "Item 'msg_...' of type 'message' was provided without its required 'reasoning' item"
            #
            # IMPORTANT: Only add items manually if we WON'T use previous_response_id
            # in the recursive call. When previous_response_id is passed to the API,
            # it automatically includes all items from that response.
            #
            # BUG FIX: During compression retry (_compression_retry=True), we stay
            # stateless and don't pass previous_response_id, so we MUST add items
            # manually even though we have a response_id from the current response.
            _compression_retry = kwargs.get("_compression_retry", False)
            will_use_previous_response_id = response_id and not _compression_retry

            if response_output_items and not will_use_previous_response_id:
                # Deduplicate by 'id' field to avoid "Duplicate item found with id" errors
                existing_ids = {msg.get("id") for msg in updated_messages if msg.get("id")}
                unique_items = [item for item in response_output_items if item.get("id") not in existing_ids]

                updated_messages.extend(unique_items)
                logger.debug(f"Added {len(unique_items)} response output items to messages for reasoning continuity (filtered {len(response_output_items) - len(unique_items)} duplicates)")
            elif will_use_previous_response_id:
                logger.debug(f"Skipping manual item addition - using previous_response_id={response_id} for automatic continuity")

            # Configuration for custom tool execution
            CUSTOM_TOOL_CONFIG = ToolExecutionConfig(
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

            # Configuration for MCP tool execution
            MCP_TOOL_CONFIG = ToolExecutionConfig(
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

            def chunk_adapter(chunk: StreamChunk) -> StreamChunk:
                # Pass through hook_execution chunks unchanged to preserve hook_info
                if getattr(chunk, "type", None) == "hook_execution":
                    return chunk
                return TextStreamChunk(
                    type=chunk_type_map.get(chunk.type, chunk.type),
                    status=getattr(chunk, "status", None),
                    content=getattr(chunk, "content", None),
                    source=getattr(chunk, "source", None),
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
                            CUSTOM_TOOL_CONFIG,
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
                            CUSTOM_TOOL_CONFIG,
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

            # Check circuit breaker status before executing MCP functions
            if mcp_calls and not await super()._check_circuit_breaker_before_execution():
                logger.warning("All MCP servers blocked by circuit breaker")
                yield TextStreamChunk(
                    type=ChunkType.MCP_STATUS,
                    status="mcp_blocked",
                    content="⚠️ [MCP] All servers blocked by circuit breaker",
                    source="circuit_breaker",
                )
                # Skip MCP tool execution but continue with custom tool results
                mcp_calls = []

            # Check if planning mode is enabled - selectively block MCP tool execution during planning
            if self.is_planning_mode_enabled():
                blocked_tools = self.get_planning_mode_blocked_tools()

                if not blocked_tools:
                    # Empty set means block ALL MCP tools (backward compatible)
                    logger.info("[Response] Planning mode enabled - blocking ALL MCP tool execution")
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
                    logger.info(f"[Response] Planning mode enabled - selective blocking of {len(blocked_tools)} tools")

            # Combine all local tool calls for parallel/sequential execution
            pending_mcp_calls: list[dict[str, Any]] = []
            for call in mcp_calls:
                if nlip_available:
                    logger.info(f"[NLIP] Using NLIP routing for MCP tool {call['name']}")
                    try:
                        async for chunk in self._stream_tool_execution_via_nlip(
                            call,
                            MCP_TOOL_CONFIG,
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
                            MCP_TOOL_CONFIG,
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

            all_calls = pending_custom_calls + pending_mcp_calls

            def tool_config_for_call(call: dict[str, Any]) -> ToolExecutionConfig:
                return CUSTOM_TOOL_CONFIG if call["name"] in self._custom_tool_names else MCP_TOOL_CONFIG

            if all_calls:
                async for adapted_chunk in self._execute_tool_calls(
                    all_calls=all_calls,
                    tool_config_for_call=tool_config_for_call,
                    all_params=all_params,
                    updated_messages=updated_messages,
                    processed_call_ids=processed_call_ids,
                    log_prefix="[Response]",
                    chunk_adapter=chunk_adapter,
                ):
                    functions_executed = True
                    yield adapted_chunk

            # Ensure all captured function calls have results to prevent hanging
            for call in captured_function_calls:
                if call["call_id"] not in processed_call_ids:
                    logger.warning(f"Tool call {call['call_id']} for function {call['name']} was not processed - adding error result")

                    # Only add error output message
                    # function_call is already included from response.output (with reasoning items)
                    error_output_msg = {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": f"Error: Tool call {call['call_id']} for function {call['name']} was not processed. This may indicate a validation or execution error.",
                    }
                    updated_messages.append(error_output_msg)
                    functions_executed = True

            # Prepare messages for recursive call
            if functions_executed:
                # Pass response_id for reasoning continuity in recursive call
                # BUT NOT if we're in compression retry mode - we need to stay stateless
                # to avoid re-accumulating context that would exceed the window again
                recursive_kwargs = kwargs.copy()
                _compression_retry = kwargs.get("_compression_retry", False)
                if response_id and not _compression_retry:
                    recursive_kwargs["previous_response_id"] = response_id

                has_prev_resp_id = bool(recursive_kwargs.get("previous_response_id"))
                if not has_prev_resp_id:
                    # Trim history to bound memory when sending full context
                    updated_messages = super()._trim_message_history(updated_messages)
                updated_messages = self._prepare_recursive_messages(
                    updated_messages,
                    new_items_start_index=new_items_start_index,
                    has_previous_response_id=has_prev_resp_id,
                )

                # Recursive call with updated messages
                async for chunk in self._stream_with_custom_and_mcp_tools(updated_messages, tools, client, **recursive_kwargs):
                    yield chunk
            else:
                # No functions were executed, we're done
                yield TextStreamChunk(type=ChunkType.DONE, source="response_api")
                return

        elif response_completed:
            # Response completed with no function calls - we're done (base case)
            yield TextStreamChunk(
                type=ChunkType.MCP_STATUS,
                status="mcp_session_complete",
                content="✅ [MCP] Session completed",
                source="mcp_session",
            )
            yield TextStreamChunk(type=ChunkType.DONE, source="response_api")
            return

    @staticmethod
    def _prepare_recursive_messages(
        messages: list[dict[str, Any]],
        new_items_start_index: int,
        has_previous_response_id: bool,
    ) -> list[dict[str, Any]]:
        """Prepare messages for the next recursive API call.

        When ``previous_response_id`` is active, the server-side response
        chain already includes all prior context (system prompt, user
        messages, reasoning items, prior function_call / function_call_output
        pairs).  Sending the full accumulated history again causes the API
        to reject the request with:

            400 - Duplicate item found with id rs_XXXX

        To prevent this, only items that were appended *after* the current
        response (i.e. ``function_call_output`` items from tool executions
        in this iteration) are kept.

        When ``previous_response_id`` is **not** used (first call or
        compression-retry), the full message list is returned unchanged
        so the caller can apply its own trimming.
        """
        if has_previous_response_id:
            return messages[new_items_start_index:]
        return messages

    async def _upload_files_and_create_vector_store(
        self,
        messages: list[dict[str, Any]],
        client: AsyncOpenAI,
        agent_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Upload file_pending_upload items and create a vector store."""

        try:
            pending_files: list[dict[str, Any]] = []
            file_locations: list[tuple[int, int]] = []

            for message_index, message in enumerate(messages):
                content = message.get("content")
                if not isinstance(content, list):
                    continue

                for item_index, item in enumerate(content):
                    if isinstance(item, dict) and item.get("type") == "file_pending_upload":
                        pending_files.append(item)
                        file_locations.append((message_index, item_index))

            if not pending_files:
                return messages, None

            uploaded_file_ids: list[str] = []

            http_client: httpx.AsyncClient | None = None

            try:
                for pending in pending_files:
                    source = pending.get("source")

                    if source == "local":
                        path_str = pending.get("path")
                        if not path_str:
                            logger.warning("Missing local path for file_pending_upload entry")
                            continue

                        file_path = Path(path_str)
                        if not file_path.exists():
                            raise UploadFileError(f"File not found for upload: {file_path}")

                        try:
                            with file_path.open("rb") as file_handle:
                                uploaded_file = await client.files.create(
                                    purpose="assistants",
                                    file=file_handle,
                                )
                        except Exception as exc:
                            raise UploadFileError(f"Failed to upload file {file_path}: {exc}") from exc

                    elif source == "url":
                        file_url = pending.get("url")
                        if not file_url:
                            logger.warning("Missing URL for file_pending_upload entry")
                            continue

                        parsed = urlparse(file_url)
                        if parsed.scheme not in {"http", "https"}:
                            raise UploadFileError(f"Unsupported URL scheme for file upload: {file_url}")

                        if http_client is None:
                            http_client = httpx.AsyncClient()

                        try:
                            response = await http_client.get(file_url, timeout=30.0)
                            response.raise_for_status()
                        except httpx.HTTPError as exc:
                            raise UploadFileError(f"Failed to download file from URL {file_url}: {exc}") from exc

                        filename = Path(parsed.path).name or "remote_file"
                        file_bytes = BytesIO(response.content)

                        try:
                            uploaded_file = await client.files.create(
                                purpose="assistants",
                                file=(filename, file_bytes),
                            )
                        except Exception as exc:
                            raise UploadFileError(f"Failed to upload file from URL {file_url}: {exc}") from exc

                    else:
                        raise UploadFileError(f"Unknown file_pending_upload source: {source}")

                    file_id = getattr(uploaded_file, "id", None)
                    if not file_id:
                        raise UploadFileError("Uploaded file response missing ID")

                    uploaded_file_ids.append(file_id)
                    self._uploaded_file_ids.append(file_id)
                    logger.info(f"Uploaded file for File Search (file_id={file_id})")

            finally:
                if http_client is not None:
                    await http_client.aclose()

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            vector_store_name = f"massgen_file_search_{agent_id or 'default'}_{timestamp}"

            try:
                vector_store = await client.vector_stores.create(name=vector_store_name)
            except Exception as exc:
                raise UploadFileError(f"Failed to create vector store: {exc}") from exc

            vector_store_id = getattr(vector_store, "id", None)
            if not vector_store_id:
                raise UploadFileError("Vector store response missing ID")

            self._vector_store_ids.append(vector_store_id)
            logger.info(
                "Created vector store for File Search",
                extra={
                    "vector_store_id": vector_store_id,
                    "file_count": len(uploaded_file_ids),
                },
            )

            for file_id in uploaded_file_ids:
                try:
                    vs_file = await client.vector_stores.files.create_and_poll(
                        vector_store_id=vector_store_id,
                        file_id=file_id,
                    )
                    logger.info(
                        "File indexed and attached to vector store",
                        extra={
                            "vector_store_id": vector_store_id,
                            "file_id": file_id,
                            "status": getattr(vs_file, "status", None),
                        },
                    )
                except Exception as exc:
                    raise UploadFileError(
                        f"Failed to attach and index file {file_id} to vector store {vector_store_id}: {exc}",
                    ) from exc

            if uploaded_file_ids:
                logger.info(
                    "All files indexed for File Search; waiting 2s for vector store to stabilize",
                    extra={
                        "vector_store_id": vector_store_id,
                        "file_count": len(uploaded_file_ids),
                    },
                )
                await asyncio.sleep(2)

            updated_messages = []
            for message in messages:
                cloned = dict(message)
                if isinstance(message.get("content"), list):
                    cloned["content"] = [dict(item) if isinstance(item, dict) else item for item in message["content"]]
                updated_messages.append(cloned)
            for message_index, item_index in reversed(file_locations):
                content_list = updated_messages[message_index].get("content")
                if isinstance(content_list, list):
                    content_list.pop(item_index)
                    if not content_list:
                        content_list.append(
                            {
                                "type": "text",
                                "text": "[Files uploaded for search integration]",
                            },
                        )

            return updated_messages, vector_store_id

        except Exception as error:
            logger.warning(f"File Search upload failed: {error}. Continuing without file search.")
            return messages, None

    async def _cleanup_file_search_resources(
        self,
        client: AsyncOpenAI,
        agent_id: str | None = None,
    ) -> None:
        """Clean up File Search vector stores and uploaded files."""

        for vector_store_id in list(self._vector_store_ids):
            try:
                await client.vector_stores.delete(vector_store_id)
                logger.info(
                    "Deleted File Search vector store",
                    extra={
                        "vector_store_id": vector_store_id,
                        "agent_id": agent_id,
                    },
                )
            except Exception as exc:
                logger.warning(
                    f"Failed to delete vector store {vector_store_id}: {exc}",
                    extra={"agent_id": agent_id},
                )

        for file_id in list(self._uploaded_file_ids):
            try:
                await client.files.delete(file_id)
                logger.debug(
                    "Deleted File Search uploaded file",
                    extra={
                        "file_id": file_id,
                        "agent_id": agent_id,
                    },
                )
            except Exception as exc:
                logger.warning(
                    f"Failed to delete file {file_id}: {exc}",
                    extra={"agent_id": agent_id},
                )

        self._vector_store_ids.clear()
        self._uploaded_file_ids.clear()

    def _convert_mcp_tools_to_openai_format(self) -> list[dict[str, Any]]:
        """Convert MCP tools (stdio + streamable-http) to OpenAI function declarations."""
        if not self._mcp_functions:
            return []

        converted_tools = []
        for function in self._mcp_functions.values():
            converted_tools.append(function.to_openai_format())

        logger.debug(
            f"Converted {len(converted_tools)} MCP tools (stdio + streamable-http) to OpenAI format",
        )
        return converted_tools

    async def _process_stream(self, stream, all_params, agent_id=None):
        first_content_recorded = False
        try:
            async for chunk in stream:
                processed = self._process_stream_chunk(chunk, agent_id)
                # Record TTFT on first content
                if not first_content_recorded and processed.type in [ChunkType.CONTENT, "content"]:
                    self.record_first_token()
                    first_content_recorded = True
                if processed.type in [ChunkType.ERROR, "error"]:
                    # Response failed - close timing and yield error
                    self.end_api_call_timing(
                        success=False,
                        error=getattr(processed, "error", "unknown"),
                    )
                    yield processed
                    return
                if processed.type == "complete_response":
                    # Yield the complete response first
                    yield processed
                    # Then signal completion with done chunk
                    self.end_api_call_timing(success=True)
                    log_stream_chunk("backend.response", "done", None, agent_id)
                    yield TextStreamChunk(type=ChunkType.DONE, source="response_api")
                else:
                    yield processed
        except Exception as e:
            error_msg = str(e) or "Stream interrupted"
            logger.error(
                f"[Response API] Mid-stream error in non-MCP path: {error_msg}",
            )
            self.end_api_call_timing(success=False, error=error_msg)
            yield TextStreamChunk(
                type=ChunkType.ERROR,
                error=error_msg,
                source="response_api",
            )
            return

    def _process_stream_chunk(self, chunk, agent_id) -> TextStreamChunk | StreamChunk:
        """
        Process individual stream chunks and convert to appropriate chunk format.

        Returns TextStreamChunk for text/reasoning/tool content,
        or legacy StreamChunk for backward compatibility.
        """

        if not hasattr(chunk, "type"):
            # Return legacy StreamChunk for backward compatibility
            return StreamChunk(type="content", content="")
        chunk_type = chunk.type

        # Handle different chunk types
        if chunk_type == "response.output_text.delta" and hasattr(chunk, "delta"):
            log_backend_agent_message(
                agent_id or "default",
                "RECV",
                {"content": chunk.delta},
                backend_name=self.get_provider_name(),
            )
            log_stream_chunk("backend.response", "content", chunk.delta, agent_id)
            # Track content in streaming buffer for compression recovery
            self._append_to_streaming_buffer(chunk.delta)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content=chunk.delta,
                source="response_api",
            )

        elif chunk_type == "response.reasoning_text.delta" and hasattr(chunk, "delta"):
            log_stream_chunk("backend.response", "reasoning", chunk.delta, agent_id)
            self._append_reasoning_to_buffer(chunk.delta)
            return TextStreamChunk(
                type=ChunkType.REASONING,
                content=f"🧠 [Reasoning] {chunk.delta}",
                reasoning_delta=chunk.delta,
                item_id=getattr(chunk, "item_id", None),
                content_index=getattr(chunk, "content_index", None),
                source="response_api",
            )

        elif chunk_type == "response.reasoning_text.done":
            reasoning_text = getattr(chunk, "text", "")
            log_stream_chunk("backend.response", "reasoning_done", reasoning_text, agent_id)
            return TextStreamChunk(
                type=ChunkType.REASONING_DONE,
                content="\n🧠 [Reasoning Complete]\n",
                reasoning_text=reasoning_text,
                item_id=getattr(chunk, "item_id", None),
                content_index=getattr(chunk, "content_index", None),
                source="response_api",
            )

        elif chunk_type == "response.reasoning_summary_text.delta" and hasattr(chunk, "delta"):
            log_stream_chunk("backend.response", "reasoning_summary", chunk.delta, agent_id)
            # Buffer reasoning summary for compression recovery (same as raw reasoning)
            self._append_reasoning_to_buffer(chunk.delta)
            return TextStreamChunk(
                type=ChunkType.REASONING_SUMMARY,
                content=chunk.delta,
                reasoning_summary_delta=chunk.delta,
                item_id=getattr(chunk, "item_id", None),
                summary_index=getattr(chunk, "summary_index", None),
                source="response_api",
            )

        elif chunk_type == "response.reasoning_summary_text.done":
            summary_text = getattr(chunk, "text", "")
            log_stream_chunk("backend.response", "reasoning_summary_done", summary_text, agent_id)
            return TextStreamChunk(
                type=ChunkType.REASONING_SUMMARY_DONE,
                content="\n📋 [Reasoning Summary Complete]\n",
                reasoning_summary_text=summary_text,
                item_id=getattr(chunk, "item_id", None),
                summary_index=getattr(chunk, "summary_index", None),
                source="response_api",
            )

        # Provider tool events
        elif chunk_type == "response.file_search_call.in_progress":
            item_id = getattr(chunk, "item_id", None)
            output_index = getattr(chunk, "output_index", None)
            log_stream_chunk("backend.response", "file_search", "Starting file search", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n📁 [File Search] Starting search...",
                item_id=item_id,
                content_index=output_index,
                source="response_api",
            )
        elif chunk_type == "response.file_search_call.searching":
            item_id = getattr(chunk, "item_id", None)
            output_index = getattr(chunk, "output_index", None)
            queries = getattr(chunk, "queries", None)
            query_text = ""
            if queries:
                try:
                    if isinstance(queries, (list, tuple)):
                        query_text = ", ".join(str(q) for q in queries if q)
                    else:
                        query_text = str(queries)
                except Exception:
                    query_text = ""
            message = "\n📁 [File Search] Searching..."
            if query_text:
                message += f" Query: {query_text}"
            log_stream_chunk(
                "backend.response",
                "file_search",
                f"Searching files{f' for {query_text}' if query_text else ''}",
                agent_id,
            )
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content=message,
                item_id=item_id,
                content_index=output_index,
                source="response_api",
            )
        elif chunk_type == "response.file_search_call.completed":
            item_id = getattr(chunk, "item_id", None)
            output_index = getattr(chunk, "output_index", None)
            results = getattr(chunk, "results", None)
            if results is None:
                results = getattr(chunk, "search_results", None)
            queries = getattr(chunk, "queries", None)
            query_text = ""
            if queries:
                try:
                    if isinstance(queries, (list, tuple)):
                        query_text = ", ".join(str(q) for q in queries if q)
                    else:
                        query_text = str(queries)
                except Exception:
                    query_text = ""
            if results is not None:
                try:
                    result_count = len(results)
                except Exception:
                    result_count = None
            else:
                result_count = None
            message_parts = ["\n✅ [File Search] Completed"]
            if query_text:
                message_parts.append(f"Query: {query_text}")
            if result_count is not None:
                message_parts.append(f"Results: {result_count}")
            message = " ".join(message_parts)
            log_stream_chunk(
                "backend.response",
                "file_search",
                f"Completed file search{f' for {query_text}' if query_text else ''}{f' with {result_count} results' if result_count is not None else ''}",
                agent_id,
            )
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content=message,
                item_id=item_id,
                content_index=output_index,
                source="response_api",
            )

        elif chunk_type == "response.web_search_call.in_progress":
            log_stream_chunk("backend.response", "web_search", "Starting search", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n🔍 [Provider Tool: Web Search] Starting search...",
                source="response_api",
            )
        elif chunk_type == "response.web_search_call.searching":
            log_stream_chunk("backend.response", "web_search", "Searching", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n🔍 [Provider Tool: Web Search] Searching...",
                source="response_api",
            )
        elif chunk_type == "response.web_search_call.completed":
            log_stream_chunk("backend.response", "web_search", "Search completed", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n✅ [Provider Tool: Web Search] Search completed",
                source="response_api",
            )

        elif chunk_type == "response.x_search_call.in_progress":
            log_stream_chunk("backend.response", "x_search", "Starting X search", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n🔎 [Provider Tool: X Search] Starting search...",
                source="response_api",
            )
        elif chunk_type == "response.x_search_call.searching":
            log_stream_chunk("backend.response", "x_search", "Searching X", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n🔎 [Provider Tool: X Search] Searching...",
                source="response_api",
            )
        elif chunk_type == "response.x_search_call.completed":
            log_stream_chunk("backend.response", "x_search", "X search completed", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n✅ [Provider Tool: X Search] Search completed",
                source="response_api",
            )
        elif chunk_type == "response.output_item.added":
            if hasattr(chunk, "item") and chunk.item and self._is_xai_x_search_custom_tool_item(chunk.item):
                self._record_xai_custom_tool_start(chunk.item)
                tool_name = self._get_response_item_field(chunk.item, "name", "x_search")
                log_stream_chunk("backend.response", "x_search", f"Starting {tool_name}", agent_id)
                return TextStreamChunk(
                    type=ChunkType.CONTENT,
                    content=f"\n🔎 [Provider Tool: X Search] Running {tool_name}...\n",
                    source="response_api",
                )
        elif chunk_type == "response.custom_tool_call_input.delta":
            call_id = getattr(chunk, "call_id", "") or ""
            if call_id:
                previous = self._xai_custom_tool_inputs_by_call_id.get(call_id, "")
                delta = getattr(chunk, "delta", "") or ""
                current = previous + delta
                self._xai_custom_tool_inputs_by_call_id[call_id] = current
                payload = self._parse_response_item_json(current)
                formatted = self._format_xai_x_search_custom_tool_input_chunk(
                    call_id,
                    payload,
                    agent_id,
                )
                if formatted is not None:
                    return formatted
        elif chunk_type == "response.custom_tool_call_input.done":
            call_id = getattr(chunk, "call_id", "") or ""
            if call_id:
                final_input = getattr(chunk, "input", None)
                if isinstance(final_input, str) and final_input:
                    self._xai_custom_tool_inputs_by_call_id[call_id] = final_input
                payload = self._parse_response_item_json(
                    self._xai_custom_tool_inputs_by_call_id.get(call_id, ""),
                )
                formatted = self._format_xai_x_search_custom_tool_input_chunk(
                    call_id,
                    payload,
                    agent_id,
                )
                if formatted is not None:
                    return formatted

        elif chunk_type == "response.code_interpreter_call.in_progress":
            log_stream_chunk("backend.response", "code_interpreter", "Starting execution", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n💻 [Provider Tool: Code Interpreter] Starting execution...",
                source="response_api",
            )
        elif chunk_type in {"response.code_interpreter_call.executing", "response.code_interpreter_call.interpreting"}:
            log_stream_chunk("backend.response", "code_interpreter", "Executing", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n💻 [Provider Tool: Code Interpreter] Executing...",
                source="response_api",
            )
        elif chunk_type == "response.code_interpreter_call_code.delta":
            code_delta = getattr(chunk, "delta", "") or ""
            if code_delta:
                log_stream_chunk("backend.response", "code_executed", code_delta, agent_id)
                return TextStreamChunk(
                    type=ChunkType.CONTENT,
                    content=f"💻 [Code Executed]\n```\n{code_delta}\n```\n",
                    source="response_api",
                )
        elif chunk_type == "response.code_interpreter_call_code.done":
            code_text = getattr(chunk, "code", None) or getattr(chunk, "text", None) or ""
            if code_text:
                log_stream_chunk("backend.response", "code_executed", code_text, agent_id)
                return TextStreamChunk(
                    type=ChunkType.CONTENT,
                    content=f"💻 [Code Executed]\n```\n{code_text}\n```\n",
                    source="response_api",
                )
        elif chunk_type == "response.code_interpreter_call.completed":
            log_stream_chunk("backend.response", "code_interpreter", "Execution completed", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n✅ [Provider Tool: Code Interpreter] Execution completed",
                source="response_api",
            )

        # Image Generation events
        elif chunk_type == "response.image_generation_call.in_progress":
            log_stream_chunk("backend.response", "image_generation", "Starting image generation", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n🎨 [Provider Tool: Image Generation] Starting generation...",
                source="response_api",
            )
        elif chunk_type == "response.image_generation_call.generating":
            log_stream_chunk("backend.response", "image_generation", "Generating image", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n🎨 [Provider Tool: Image Generation] Generating image...",
                source="response_api",
            )
        elif chunk_type == "response.image_generation_call.completed":
            log_stream_chunk("backend.response", "image_generation", "Image generation completed", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n✅ [Provider Tool: Image Generation] Image generated successfully",
                source="response_api",
            )
        elif chunk.type == "image_generation.completed":
            # Handle the final image generation result
            if hasattr(chunk, "b64_json"):
                log_stream_chunk("backend.response", "image_generation", "Image data received", agent_id)
                # The image is complete, return a status message
                return TextStreamChunk(
                    type=ChunkType.CONTENT,
                    content="\n✅ [Image Generation] Image successfully created",
                    source="response_api",
                )
        elif chunk.type == "response.output_item.done":
            # Get search query or executed code details - show them right after completion
            if hasattr(chunk, "item") and chunk.item:
                if hasattr(chunk.item, "type") and chunk.item.type == "web_search_call":
                    if hasattr(chunk.item, "action") and ("query" in chunk.item.action):
                        search_query = chunk.item.action["query"]
                        if search_query:
                            log_stream_chunk("backend.response", "search_query", search_query, agent_id)
                            return TextStreamChunk(
                                type=ChunkType.CONTENT,
                                content=f"\n🔍 [Search Query] '{search_query}'\n",
                                source="response_api",
                            )
                elif hasattr(chunk.item, "type") and chunk.item.type == "x_search_call":
                    if hasattr(chunk.item, "action") and ("query" in chunk.item.action):
                        search_query = chunk.item.action["query"]
                        if search_query:
                            log_stream_chunk("backend.response", "x_search_query", search_query, agent_id)
                            return TextStreamChunk(
                                type=ChunkType.CONTENT,
                                content=f"\n🔎 [X Search Query] '{search_query}'\n",
                                source="response_api",
                            )
                elif self._is_xai_x_search_custom_tool_item(chunk.item):
                    return self._format_xai_x_search_custom_tool_chunk(chunk.item, agent_id)
                elif hasattr(chunk.item, "type") and chunk.item.type == "code_interpreter_call":
                    if hasattr(chunk.item, "code") and chunk.item.code:
                        # Format code as a proper code block - don't assume language
                        log_stream_chunk("backend.response", "code_executed", chunk.item.code, agent_id)
                        return TextStreamChunk(
                            type=ChunkType.CONTENT,
                            content=f"💻 [Code Executed]\n```\n{chunk.item.code}\n```\n",
                            source="response_api",
                        )

                    # Also show the execution output if available
                    if hasattr(chunk.item, "outputs") and chunk.item.outputs:
                        for output in chunk.item.outputs:
                            output_text = None
                            if hasattr(output, "text") and output.text:
                                output_text = output.text
                            elif hasattr(output, "content") and output.content:
                                output_text = output.content
                            elif hasattr(output, "data") and output.data:
                                output_text = str(output.data)
                            elif isinstance(output, str):
                                output_text = output
                            elif isinstance(output, dict):
                                # Handle dict format outputs
                                if "text" in output:
                                    output_text = output["text"]
                                elif "content" in output:
                                    output_text = output["content"]
                                elif "data" in output:
                                    output_text = str(output["data"])

                            if output_text and output_text.strip():
                                log_stream_chunk("backend.response", "code_result", output_text.strip(), agent_id)
                                return TextStreamChunk(
                                    type=ChunkType.CONTENT,
                                    content=f"📊 [Result] {output_text.strip()}\n",
                                    source="response_api",
                                )
                elif hasattr(chunk.item, "type") and chunk.item.type == "image_generation_call":
                    # Image generation completed - show details
                    if hasattr(chunk.item, "action") and chunk.item.action:
                        prompt = chunk.item.action.get("prompt", "")
                        size = chunk.item.action.get("size", "1024x1024")
                        if prompt:
                            log_stream_chunk("backend.response", "image_prompt", prompt, agent_id)
                            return TextStreamChunk(
                                type=ChunkType.CONTENT,
                                content=f"\n🎨 [Image Generated] Prompt: '{prompt}' (Size: {size})\n",
                                source="response_api",
                            )
        # MCP events
        elif chunk_type == "response.mcp_list_tools.started":
            return TextStreamChunk(
                type=ChunkType.MCP_STATUS,
                content="\n🔧 [MCP] Listing available tools...",
                source="response_api",
            )
        elif chunk_type == "response.mcp_list_tools.completed":
            return TextStreamChunk(
                type=ChunkType.MCP_STATUS,
                content="\n✅ [MCP] Tool listing completed",
                source="response_api",
            )
        elif chunk_type == "response.mcp_list_tools.failed":
            return TextStreamChunk(
                type=ChunkType.MCP_STATUS,
                content="\n❌ [MCP] Tool listing failed",
                source="response_api",
            )

        elif chunk_type == "response.mcp_call.started":
            tool_name = getattr(chunk, "tool_name", "unknown")
            return TextStreamChunk(
                type=ChunkType.MCP_STATUS,
                content=f"\n🔧 [MCP] Calling tool '{tool_name}'...",
                source="response_api",
            )
        elif chunk_type == "response.mcp_call.in_progress":
            return TextStreamChunk(
                type=ChunkType.MCP_STATUS,
                content="\n⏳ [MCP] Tool execution in progress...",
                source="response_api",
            )
        elif chunk_type == "response.mcp_call.completed":
            tool_name = getattr(chunk, "tool_name", "unknown")
            return TextStreamChunk(
                type=ChunkType.MCP_STATUS,
                content=f"\n✅ [MCP] Tool '{tool_name}' completed",
                source="response_api",
            )
        elif chunk_type == "response.mcp_call.failed":
            tool_name = getattr(chunk, "tool_name", "unknown")
            error_msg = getattr(chunk, "error", "unknown error")
            return TextStreamChunk(
                type=ChunkType.MCP_STATUS,
                content=f"\n❌ [MCP] Tool '{tool_name}' failed: {error_msg}",
                source="response_api",
            )

        elif chunk.type == "response.failed":
            error_msg = "Response failed"
            if hasattr(chunk, "response") and chunk.response:
                error_obj = getattr(chunk.response, "error", None)
                if error_obj:
                    error_msg = getattr(error_obj, "message", None) or str(error_obj)
            logger.error(f"[Response API] {error_msg}")
            return TextStreamChunk(
                type=ChunkType.ERROR,
                error=error_msg,
                source="response_api",
            )

        elif chunk.type in ["response.completed", "response.incomplete"]:
            # Extract usage data for token tracking
            if hasattr(chunk, "response") and hasattr(chunk.response, "usage"):
                self._update_token_usage_from_api_response(
                    chunk.response.usage,
                    self.config.get("model", "gpt-4o"),
                )

            # Extract and yield tool calls from the complete response
            if hasattr(chunk, "response"):
                response_dict = self._convert_to_dict(chunk.response)

                # Handle builtin tool results from output array with simple content format
                if isinstance(response_dict, dict) and "output" in response_dict:
                    for item in response_dict["output"]:
                        if item.get("type") == "code_interpreter_call":
                            # Code execution result
                            status = item.get("status", "unknown")
                            code = item.get("code", "")
                            outputs = item.get("outputs")

                            content = f"\n🔧 Code Interpreter [{status.title()}]"
                            if code:
                                content += f": {code}"
                            if outputs:
                                content += f" → {outputs}"

                            log_stream_chunk("backend.response", "code_interpreter_result", content, agent_id)
                            return TextStreamChunk(
                                type=ChunkType.CONTENT,
                                content=content,
                                source="response_api",
                            )
                        elif item.get("type") == "web_search_call":
                            # Web search result
                            status = item.get("status", "unknown")
                            # Query is in action.query, not directly in item
                            query = item.get("action", {}).get("query", "")
                            results = item.get("results")

                            # Only show web search completion if query is present
                            if query:
                                content = f"\n🔧 Web Search [{status.title()}]: {query}"
                                if results:
                                    content += f" → Found {len(results)} results"
                                log_stream_chunk("backend.response", "web_search_result", content, agent_id)
                                return TextStreamChunk(
                                    type=ChunkType.CONTENT,
                                    content=content,
                                    source="response_api",
                                )
                        elif item.get("type") == "x_search_call":
                            status = item.get("status", "unknown")
                            query = item.get("action", {}).get("query", "")
                            results = item.get("results")

                            if query:
                                content = f"\n🔧 X Search [{status.title()}]: {query}"
                                if results:
                                    content += f" → Found {len(results)} results"
                                log_stream_chunk("backend.response", "x_search_result", content, agent_id)
                                return TextStreamChunk(
                                    type=ChunkType.CONTENT,
                                    content=content,
                                    source="response_api",
                                )
                        elif self._is_xai_x_search_custom_tool_item(item):
                            return self._format_xai_x_search_custom_tool_chunk(item, agent_id, strip_newlines=True)
                        elif item.get("type") == "image_generation_call":
                            # Image generation result in completed response
                            status = item.get("status", "unknown")
                            action = item.get("action", {})
                            prompt = action.get("prompt", "")
                            size = action.get("size", "1024x1024")

                            if prompt:
                                content = f"\n🔧 Image Generation [{status.title()}]: {prompt} (Size: {size})"
                                log_stream_chunk("backend.response", "image_generation_result", content, agent_id)
                                return TextStreamChunk(
                                    type=ChunkType.CONTENT,
                                    content=content,
                                    source="response_api",
                                )
                # Yield the complete response for internal use
                log_stream_chunk("backend.response", "complete_response", "Response completed", agent_id)
                return TextStreamChunk(
                    type=ChunkType.COMPLETE_RESPONSE,
                    response=response_dict,
                    source="response_api",
                )

        # Default chunk - this should not happen for valid responses
        # Return legacy StreamChunk for backward compatibility
        return StreamChunk(type="content", content="")

    async def _compress_messages_for_context_recovery(
        self,
        messages: list[dict[str, Any]],
        buffer_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """Compress messages for context error recovery using LLM-based summarization.

        Args:
            messages: The messages that caused the context length error
            buffer_content: Optional partial response content from streaming

        Returns:
            List of compressed messages to use as input
        """
        from ._compression_utils import compress_messages_for_recovery

        logger.info(
            f"[{self.get_provider_name()}] Compressing {len(messages)} messages " f"with target_ratio={self._compression_target_ratio}",
        )

        # Use the shared compression utility
        result = await compress_messages_for_recovery(
            messages=messages,
            backend=self,
            target_ratio=self._compression_target_ratio,
            buffer_content=buffer_content,
        )

        logger.info(
            f"[{self.get_provider_name()}] Compressed {len(messages)} messages " f"to {len(result)} messages",
        )

        return result

    def create_tool_result_message(
        self,
        tool_call: dict[str, Any],
        result_content: str,
    ) -> list[dict[str, Any]]:
        """Create tool result message for OpenAI Responses API format.

        Response API requires BOTH the function_call AND function_call_output
        to be present in the input for multi-turn conversations.

        Returns:
            List of two dicts: [function_call, function_call_output]
        """
        tool_call_id = self.extract_tool_call_id(tool_call)
        tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name", "unknown")
        tool_arguments = tool_call.get("arguments") or tool_call.get("function", {}).get("arguments", "{}")

        # Return both function_call and function_call_output
        return [
            {
                "type": "function_call",
                "call_id": tool_call_id,
                "name": tool_name,
                "arguments": tool_arguments,
            },
            {
                "type": "function_call_output",
                "call_id": tool_call_id,
                "output": result_content,
            },
        ]

    def extract_tool_result_content(self, tool_result_message: dict[str, Any]) -> str:
        """Extract content from OpenAI Responses API tool result message."""
        return tool_result_message.get("output", "")

    async def _create_response_stream(self, api_params, client, ws_transport=None, agent_id=None):
        """Create a response stream via HTTP or websocket transport."""
        if ws_transport is not None and ws_transport.is_connected:
            logger.debug("[WebSocket] Sending response.create via WebSocket")
            return self._ws_event_stream(ws_transport, api_params)

        async def _make_api_call():
            return await client.responses.create(**api_params)

        return await self.circuit_breaker.call_with_retry(
            _make_api_call,
            agent_id=agent_id,
        )

    async def _ws_event_stream(self, ws_transport, api_params):
        """Wrap websocket JSON events as objects matching SDK stream chunks."""
        async for event_dict in ws_transport.send_and_receive(api_params):
            yield _WSEvent(event_dict)

    def _create_client(self, **kwargs) -> AsyncOpenAI:
        client_kwargs: dict[str, Any] = {"api_key": self.api_key or ""}
        base_url = self.config.get("base_url")
        if base_url:
            client_kwargs["base_url"] = base_url
        organization = self.config.get("organization")
        if organization:
            client_kwargs["organization"] = organization
        return openai.AsyncOpenAI(**client_kwargs)

    def _convert_to_dict(self, obj) -> dict[str, Any]:
        """Convert any object to dictionary with multiple fallback methods."""
        try:
            if hasattr(obj, "model_dump"):
                result = obj.model_dump()
            elif hasattr(obj, "dict"):
                result = obj.dict()
            else:
                result = dict(obj)

            # Fix reasoning items: Response API expects 'content' to be an array, not a string. This occurs in gpt-5-mini
            # When reasoning is encrypted/summarized, content may be empty string ""
            # which causes "expected an array of unknown values, but got a string" error
            if isinstance(result, dict) and result.get("type") == "reasoning":
                if isinstance(result.get("content"), str):
                    # Convert empty string to empty array, or wrap non-empty string in array
                    content = result["content"]
                    result["content"] = [] if content == "" else [{"type": "text", "text": content}]

            return result
        except Exception as e:
            # Final fallback: extract key attributes manually
            logger.warning(f"[ResponseBackend] _convert_to_dict failed for {type(obj).__name__}, using fallback: {e}")
            return {key: getattr(obj, key, None) for key in dir(obj) if not key.startswith("_") and not callable(getattr(obj, key, None))}

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "OpenAI"

    def get_filesystem_support(self) -> FilesystemSupport:
        """OpenAI supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def get_supported_builtin_tools(self) -> list[str]:
        """Get list of builtin tools supported by OpenAI."""
        return ["web_search", "code_interpreter"]
