# -*- coding: utf-8 -*-
"""
Response API backend implementation with multimodal support.
Standalone implementation optimized for the standard Response API format (originated by OpenAI).
Supports image input (URL and base64) and image generation via tools.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union
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
from .base import FilesystemSupport, StreamChunk
from .base_with_custom_tool_and_mcp import (
    CustomToolAndMCPBackend,
    CustomToolChunk,
    ToolExecutionConfig,
    UploadFileError,
)


class ResponseBackend(CustomToolAndMCPBackend):
    """Backend using the standard Response API format with multimodal support."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
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

        # Queue for pending image saves
        self._pending_image_saves = []

        # File Search tracking for cleanup
        self._vector_store_ids: List[str] = []
        self._uploaded_file_ids: List[str] = []

    def supports_upload_files(self) -> bool:
        return True

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI Response API with unified MCP/non-MCP processing.

        Wraps parent implementation to ensure File Search cleanup happens after streaming completes.
        """

        try:
            async for chunk in super().stream_with_tools(messages, tools, **kwargs):
                yield chunk
        finally:
            # Cleanup File Search resources after stream completes
            await self._cleanup_file_search_if_needed(**kwargs)

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
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        agent_id = kwargs.get("agent_id")
        all_params = {**self.config, **kwargs}

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

        stream = await client.responses.create(**api_params)

        async for chunk in self._process_stream(stream, all_params, agent_id):
            yield chunk

    def _append_tool_result_message(
        self,
        updated_messages: List[Dict[str, Any]],
        call: Dict[str, Any],
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
            Response API requires both function_call and function_call_output messages.
        """
        # Add function call message
        function_call_msg = {
            "type": "function_call",
            "call_id": call.get("call_id", ""),
            "name": call.get("name", ""),
            "arguments": call.get("arguments", "{}"),
        }
        updated_messages.append(function_call_msg)

        # Add function output message
        function_output_msg = {
            "type": "function_call_output",
            "call_id": call.get("call_id", ""),
            "output": str(result),
        }
        updated_messages.append(function_output_msg)

    def _append_tool_error_message(
        self,
        updated_messages: List[Dict[str, Any]],
        call: Dict[str, Any],
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
            Response API requires both function_call and function_call_output messages.
        """
        # Add function call message
        function_call_msg = {
            "type": "function_call",
            "call_id": call.get("call_id", ""),
            "name": call.get("name", ""),
            "arguments": call.get("arguments", "{}"),
        }
        updated_messages.append(function_call_msg)

        # Add error output message
        error_output_msg = {
            "type": "function_call_output",
            "call_id": call.get("call_id", ""),
            "output": error_msg,
        }
        updated_messages.append(error_output_msg)

    async def _execute_custom_tool(self, call: Dict[str, Any]) -> AsyncGenerator[CustomToolChunk, None]:
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
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Recursively stream MCP responses, executing function calls as needed."""

        agent_id = kwargs.get("agent_id")

        # Build API params for this iteration
        all_params = {**self.config, **kwargs}

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

        # Start streaming
        stream = await client.responses.create(**api_params)

        # Track function calls in this iteration
        captured_function_calls = []
        current_function_call = None
        response_completed = False

        async for chunk in stream:
            if hasattr(chunk, "type"):
                # Detect function call start
                if chunk.type == "response.output_item.added" and hasattr(chunk, "item") and chunk.item and getattr(chunk.item, "type", None) == "function_call":
                    current_function_call = {
                        "call_id": getattr(chunk.item, "call_id", ""),
                        "name": getattr(chunk.item, "name", ""),
                        "arguments": "",
                    }
                    logger.info(f"Function call detected: {current_function_call['name']}")

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
                    delta = getattr(chunk, "delta", "")
                    yield TextStreamChunk(
                        type=ChunkType.CONTENT,
                        content=delta,
                        source="response_api",
                    )

                # Handle other streaming events (reasoning, provider tools, etc.)
                else:
                    result = self._process_stream_chunk(chunk, agent_id)
                    yield result

                # Response completed
                if chunk.type == "response.completed":
                    response_completed = True
                    if captured_function_calls:
                        # Execute captured function calls and recurse
                        break  # Exit chunk loop to execute functions
                    else:
                        # No function calls, we're done (base case)
                        yield TextStreamChunk(type=ChunkType.DONE, source="response_api")
                        return

        # Execute any captured function calls
        if captured_function_calls and response_completed:
            # Categorize function calls using helper method
            mcp_calls, custom_calls, provider_calls = self._categorize_tool_calls(captured_function_calls)

            # If there are provider calls (non-MCP, non-custom), let API handle them
            if provider_calls:
                logger.info(f"Provider function calls detected: {[call['name'] for call in provider_calls]}. Ending local processing.")
                yield TextStreamChunk(type=ChunkType.DONE, source="response_api")
                return

            # Initialize for execution
            functions_executed = False
            updated_messages = current_messages.copy()
            processed_call_ids = set()  # Initialize processed_call_ids here

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

            # Execute custom tools using unified method
            for call in custom_calls:
                # Try NLIP path if enabled
                if self._nlip_enabled and self._nlip_router:
                    logger.info(f"[NLIP] Using NLIP routing for custom tool {call['name']}")
                    try:
                        async for chunk in self._stream_tool_execution_via_nlip(
                            call,
                            CUSTOM_TOOL_CONFIG,
                            updated_messages,
                            processed_call_ids,
                        ):
                            yield TextStreamChunk(
                                type=chunk_type_map.get(chunk.type, chunk.type),
                                status=getattr(chunk, "status", None),
                                content=getattr(chunk, "content", None),
                                source=getattr(chunk, "source", None),
                            )
                        functions_executed = True

                    except Exception as e:
                        # NLIP routing failed - fall back to direct execution
                        logger.warning(
                            f"[NLIP] Routing failed for {call['name']}: {e}. " f"Falling back to direct execution.",
                        )

                        async for chunk in self._execute_tool_with_logging(
                            call,
                            CUSTOM_TOOL_CONFIG,
                            updated_messages,
                            processed_call_ids,
                        ):
                            yield TextStreamChunk(
                                type=chunk_type_map.get(chunk.type, chunk.type),
                                status=getattr(chunk, "status", None),
                                content=getattr(chunk, "content", None),
                                source=getattr(chunk, "source", None),
                            )
                        functions_executed = True
                else:
                    # Direct execution (existing path)
                    reason = "disabled" if not self._nlip_enabled else "router unavailable"
                    logger.info(
                        f"[Custom Tool] Direct execution for {call['name']} (NLIP {reason})",
                    )
                    async for chunk in self._execute_tool_with_logging(
                        call,
                        CUSTOM_TOOL_CONFIG,
                        updated_messages,
                        processed_call_ids,
                    ):
                        yield TextStreamChunk(
                            type=chunk_type_map.get(chunk.type, chunk.type),
                            status=getattr(chunk, "status", None),
                            content=getattr(chunk, "content", None),
                            source=getattr(chunk, "source", None),
                        )
                    functions_executed = True

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

            # Execute MCP tools using unified method
            for call in mcp_calls:
                # Try NLIP path if enabled
                if self._nlip_enabled and self._nlip_router:
                    logger.info(f"[NLIP] Using NLIP routing for MCP tool {call['name']}")
                    try:
                        async for chunk in self._stream_tool_execution_via_nlip(
                            call,
                            MCP_TOOL_CONFIG,
                            updated_messages,
                            processed_call_ids,
                        ):
                            yield TextStreamChunk(
                                type=chunk_type_map.get(chunk.type, chunk.type),
                                status=getattr(chunk, "status", None),
                                content=getattr(chunk, "content", None),
                                source=getattr(chunk, "source", None),
                            )
                        functions_executed = True

                    except Exception as e:
                        # NLIP routing failed - fall back to direct execution
                        logger.warning(
                            f"[NLIP] Routing failed for {call['name']}: {e}. " f"Falling back to direct execution.",
                        )

                        async for chunk in self._execute_tool_with_logging(
                            call,
                            MCP_TOOL_CONFIG,
                            updated_messages,
                            processed_call_ids,
                        ):
                            yield TextStreamChunk(
                                type=chunk_type_map.get(chunk.type, chunk.type),
                                status=getattr(chunk, "status", None),
                                content=getattr(chunk, "content", None),
                                source=getattr(chunk, "source", None),
                            )
                        functions_executed = True
                else:
                    # Direct execution
                    reason = "disabled" if not self._nlip_enabled else "router unavailable"
                    logger.info(
                        f"[MCP Tool] Direct execution for {call['name']} (NLIP {reason})",
                    )
                    async for chunk in self._execute_tool_with_logging(
                        call,
                        MCP_TOOL_CONFIG,
                        updated_messages,
                        processed_call_ids,
                    ):
                        yield TextStreamChunk(
                            type=chunk_type_map.get(chunk.type, chunk.type),
                            status=getattr(chunk, "status", None),
                            content=getattr(chunk, "content", None),
                            source=getattr(chunk, "source", None),
                        )
                    functions_executed = True

            # Ensure all captured function calls have results to prevent hanging
            for call in captured_function_calls:
                if call["call_id"] not in processed_call_ids:
                    logger.warning(f"Tool call {call['call_id']} for function {call['name']} was not processed - adding error result")

                    # Add missing function call and error result to messages
                    function_call_msg = {
                        "type": "function_call",
                        "call_id": call["call_id"],
                        "name": call["name"],
                        "arguments": call["arguments"],
                    }
                    updated_messages.append(function_call_msg)

                    error_output_msg = {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": f"Error: Tool call {call['call_id']} for function {call['name']} was not processed. This may indicate a validation or execution error.",
                    }
                    updated_messages.append(error_output_msg)
                    functions_executed = True

            # Trim history after function executions to bound memory usage
            if functions_executed:
                updated_messages = super()._trim_message_history(updated_messages)

                # Recursive call with updated messages
                async for chunk in self._stream_with_custom_and_mcp_tools(updated_messages, tools, client, **kwargs):
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

    async def _upload_files_and_create_vector_store(
        self,
        messages: List[Dict[str, Any]],
        client: AsyncOpenAI,
        agent_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Upload file_pending_upload items and create a vector store."""

        try:
            pending_files: List[Dict[str, Any]] = []
            file_locations: List[Tuple[int, int]] = []

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

            uploaded_file_ids: List[str] = []

            http_client: Optional[httpx.AsyncClient] = None

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
        agent_id: Optional[str] = None,
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

    def _convert_mcp_tools_to_openai_format(self) -> List[Dict[str, Any]]:
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
        async for chunk in stream:
            processed = self._process_stream_chunk(chunk, agent_id)
            if processed.type == "complete_response":
                # Yield the complete response first
                yield processed
                # Then signal completion with done chunk
                log_stream_chunk("backend.response", "done", None, agent_id)
                yield TextStreamChunk(type=ChunkType.DONE, source="response_api")
            else:
                yield processed

    def _process_stream_chunk(self, chunk, agent_id) -> Union[TextStreamChunk, StreamChunk]:
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
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content=chunk.delta,
                source="response_api",
            )

        elif chunk_type == "response.reasoning_text.delta" and hasattr(chunk, "delta"):
            log_stream_chunk("backend.response", "reasoning", chunk.delta, agent_id)
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

        elif chunk_type == "response.code_interpreter_call.in_progress":
            log_stream_chunk("backend.response", "code_interpreter", "Starting execution", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n💻 [Provider Tool: Code Interpreter] Starting execution...",
                source="response_api",
            )
        elif chunk_type == "response.code_interpreter_call.executing":
            log_stream_chunk("backend.response", "code_interpreter", "Executing", agent_id)
            return TextStreamChunk(
                type=ChunkType.CONTENT,
                content="\n💻 [Provider Tool: Code Interpreter] Executing...",
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
        elif chunk_type == "image_generation.completed":
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

        elif chunk.type == "response.completed":
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

    def create_tool_result_message(
        self,
        tool_call: Dict[str, Any],
        result_content: str,
    ) -> Dict[str, Any]:
        """Create tool result message for OpenAI Responses API format."""
        tool_call_id = self.extract_tool_call_id(tool_call)
        # Use Responses API format directly - no conversion needed
        return {
            "type": "function_call_output",
            "call_id": tool_call_id,
            "output": result_content,
        }

    def extract_tool_result_content(self, tool_result_message: Dict[str, Any]) -> str:
        """Extract content from OpenAI Responses API tool result message."""
        return tool_result_message.get("output", "")

    def _create_client(self, **kwargs) -> AsyncOpenAI:
        return openai.AsyncOpenAI(api_key=self.api_key)

    def _convert_to_dict(self, obj) -> Dict[str, Any]:
        """Convert any object to dictionary with multiple fallback methods."""
        try:
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            elif hasattr(obj, "dict"):
                return obj.dict()
            else:
                return dict(obj)
        except Exception:
            # Final fallback: extract key attributes manually
            return {key: getattr(obj, key, None) for key in dir(obj) if not key.startswith("_") and not callable(getattr(obj, key, None))}

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "OpenAI"

    def get_filesystem_support(self) -> FilesystemSupport:
        """OpenAI supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by OpenAI."""
        return ["web_search", "code_interpreter"]
