# -*- coding: utf-8 -*-
"""
NLIP Router.

Central component that handles all NLIP message routing and translation
between NLIP messages and native tool protocols.
"""

import json
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..logger_config import logger
from .schema import (
    NLIPControlField,
    NLIPFormatField,
    NLIPMessage,
    NLIPMessageType,
    NLIPRequest,
    NLIPResponse,
    NLIPTokenField,
    NLIPToolCall,
    NLIPToolResult,
)
from .state_manager import NLIPStateManager
from .token_tracker import NLIPTokenTracker
from .translator.base import ProtocolTranslator
from .translator.builtin_translator import BuiltinToolTranslator
from .translator.custom_translator import CustomToolTranslator
from .translator.mcp_translator import MCPTranslator

MAX_PENDING_REQUESTS = 1000
MAX_PENDING_REQUESTS_PRUNE_BATCH = 100
MAX_SESSION_MESSAGES = 100


class NLIPRouter:
    """
    Unified NLIP message router for MassGen.

    Responsibilities:
    - Route NLIP messages to appropriate tool protocols
    - Translate between NLIP and native tool formats
    - Manage conversation state and tokens
    - Track tool invocations and results
    - Provide streaming response handling
    """

    def __init__(
        self,
        tool_manager: Any = None,
        mcp_executor: Any = None,
        enable_nlip: bool = True,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize NLIP router.

        Args:
            tool_manager: MassGen tool manager instance
            enable_nlip: Whether NLIP routing is enabled
            config: Optional NLIP configuration
        """
        self.tool_manager = tool_manager
        self.mcp_executor = mcp_executor
        self.enable_nlip = enable_nlip
        self.config = config or {}

        # Initialize state management
        self.state_manager = NLIPStateManager()
        self.token_tracker = NLIPTokenTracker()

        # Initialize protocol translators
        self.translators: Dict[str, ProtocolTranslator] = {
            "mcp": MCPTranslator(),
            "custom": CustomToolTranslator(),
            "builtin": BuiltinToolTranslator(),
        }

        # Message tracking
        self._pending_requests: Dict[str, NLIPRequest] = {}
        self._active_sessions: Dict[str, List[NLIPMessage]] = {}

    def is_enabled(self) -> bool:
        """Check if NLIP routing is enabled."""
        return self.enable_nlip

    async def route_message(
        self,
        message: NLIPMessage,
    ) -> AsyncGenerator[NLIPResponse, None]:
        """
        Route NLIP message to appropriate tool(s) and stream responses.

        Args:
            message: NLIP message to route

        Yields:
            NLIP response messages
        """
        if not self.enable_nlip:
            # Bypass NLIP - pass through directly
            yield await self._passthrough_execution(message)
            return

        # Track message
        self._track_message(message)

        # Handle based on message type
        if message.control.message_type == NLIPMessageType.REQUEST:
            async for response in self._handle_request(message):
                yield response
        elif message.control.message_type == NLIPMessageType.NOTIFICATION:
            await self._handle_notification(message)
        else:
            raise ValueError(
                f"Unsupported message type: {message.control.message_type}",
            )

    async def _handle_request(
        self,
        request: NLIPMessage,
    ) -> AsyncGenerator[NLIPResponse, None]:
        """
        Handle NLIP request message by routing to appropriate tools.
        """
        # Extract tool calls from request
        tool_calls = request.tool_calls or []

        if not tool_calls:
            # No tool calls - return error response
            yield self._create_error_response(
                request,
                "No tool calls found in request",
            )
            return

        # Process each tool call
        for tool_call in tool_calls:
            # Detect tool protocol (MCP, custom, or built-in)
            protocol = await self._detect_tool_protocol(tool_call.tool_name)

            # Get appropriate translator
            translator = self.translators.get(protocol)
            if not translator:
                yield self._create_error_response(
                    request,
                    f"No translator for protocol: {protocol}",
                )
                continue

            # Translate NLIP tool call to native format
            native_call = await translator.nlip_to_native_call(tool_call)

            if protocol == "mcp" and not self.mcp_executor:
                yield self._create_error_response(
                    request,
                    f"MCP executor not configured for tool: {tool_call.tool_name}",
                )
                continue

            # Execute tool using ToolManager or MCP executor
            try:
                if protocol == "mcp" and self.mcp_executor:
                    result = await self._execute_mcp_tool(tool_call, native_call)
                elif self.tool_manager:
                    # ToolManager returns AsyncGenerator
                    accumulated_output = []
                    final_result = None

                    # Extract execution context from request
                    execution_context = request.content.get("execution_context", {})

                    async for execution_result in self.tool_manager.execute_tool(
                        tool_request={
                            "name": tool_call.tool_name,
                            "input": native_call.get("parameters", {}),
                        },
                        execution_context=execution_context,
                    ):
                        # Stream intermediate output blocks immediately
                        if hasattr(execution_result, "output_blocks"):
                            for block in execution_result.output_blocks:
                                block_data = getattr(block, "data", "")
                                if block_data:
                                    if isinstance(block_data, dict) and "content" in block_data:
                                        content = block_data["content"]
                                        if isinstance(content, list) and content:
                                            first_entry = content[0]
                                            if isinstance(first_entry, dict) and "text" in first_entry:
                                                block_data = first_entry["text"]
                                    block_text = str(block_data)
                                    if block_text:
                                        yield self._create_response(
                                            request,
                                            content={
                                                "stream_chunk": block_text,
                                                "tool_id": tool_call.tool_id,
                                                "tool_name": tool_call.tool_name,
                                                "is_log": execution_result.is_log,
                                            },
                                        )

                        # Aggregate non-log results for final summary
                        if not execution_result.is_log and hasattr(execution_result, "output_blocks"):
                            for block in execution_result.output_blocks:
                                block_data = getattr(block, "data", "")
                                if block_data:
                                    if isinstance(block_data, dict) and "content" in block_data:
                                        content = block_data["content"]
                                        if isinstance(content, list) and content:
                                            first_entry = content[0]
                                            if isinstance(first_entry, dict) and "text" in first_entry:
                                                block_data = first_entry["text"]
                                    accumulated_output.append(str(block_data))

                        # Store final result metadata
                        if execution_result.is_final:
                            final_result = {
                                "output": "\n".join(accumulated_output),
                                "blocks": len(execution_result.output_blocks),
                                "metadata": execution_result.meta_info,
                            }

                    result = final_result if final_result else {"output": "\n".join(accumulated_output)}
                else:
                    # If no tool manager or MCP executor, return mock success
                    result = {"status": "success", "message": "No tool manager configured"}

                # Translate result back to NLIP format
                nlip_result = await translator.native_to_nlip_result(
                    tool_call.tool_id,
                    tool_call.tool_name,
                    result,
                )

                # Create response message
                yield self._create_tool_response(
                    request,
                    nlip_result,
                )

            except Exception as e:
                # Handle tool execution error
                error_result = NLIPToolResult(
                    tool_id=tool_call.tool_id,
                    tool_name=tool_call.tool_name,
                    status="error",
                    error=str(e),
                )
                yield self._create_tool_response(request, error_result)

    async def _detect_tool_protocol(self, tool_name: str) -> str:
        """
        Detect which protocol a tool uses (MCP, custom, or built-in).

        Args:
            tool_name: Name of the tool

        Returns:
            Protocol type: "mcp", "custom", or "builtin"
        """
        # Check if it's an MCP tool (starts with mcp__)
        if tool_name.startswith("mcp__"):
            return "mcp"

        # Check if it's a built-in tool
        builtin_tools = {
            "vote",
            "new_answer",
            "edit_file",
            "read_file",
            "write_file",
            "search_files",
            "list_directory",
        }
        if tool_name in builtin_tools:
            return "builtin"

        # Default to custom tool
        return "custom"

    async def _handle_notification(self, notification: NLIPMessage) -> None:
        """Handle NLIP notification message (fire-and-forget)."""
        # Update state based on notification
        if notification.token.session_id:
            await self.state_manager.update_session(
                notification.token.session_id,
                notification,
            )

    async def _execute_mcp_tool(
        self,
        tool_call: NLIPToolCall,
        native_call: Dict[str, Any],
    ) -> Any:
        """Execute MCP tool using injected executor."""
        if not self.mcp_executor:
            raise RuntimeError("MCP executor is not configured for NLIP router")

        parameters = native_call.get("parameters", {}) or {}
        arguments_json = json.dumps(parameters)
        _, result = await self.mcp_executor(tool_call.tool_name, arguments_json)
        return result

    async def _passthrough_execution(
        self,
        message: NLIPMessage,
    ) -> NLIPResponse:
        """
        Bypass NLIP routing and execute directly.
        Used when NLIP is disabled.
        """
        # Extract native format from NLIP message
        content = message.content

        # Execute directly without translation
        # This maintains backward compatibility
        return self._create_response(message, content)

    def _track_message(self, message: NLIPMessage) -> None:
        """Track message for correlation and debugging."""
        msg_id = message.control.message_id

        if message.control.message_type == NLIPMessageType.REQUEST:
            self._pending_requests[msg_id] = message
            if len(self._pending_requests) > MAX_PENDING_REQUESTS:
                prune_count = min(MAX_PENDING_REQUESTS_PRUNE_BATCH, len(self._pending_requests))
                for _ in range(prune_count):
                    try:
                        oldest_key = next(iter(self._pending_requests))
                    except StopIteration:
                        break
                    removed = self._pending_requests.pop(oldest_key, None)
                    if removed:
                        logger.debug(f"[NLIP] Evicted pending request {oldest_key} to cap tracked requests")

        # Track session messages
        session_id = message.token.session_id
        if session_id:
            if session_id not in self._active_sessions:
                self._active_sessions[session_id] = []
            self._active_sessions[session_id].append(message)
            session_messages = self._active_sessions[session_id]
            if len(session_messages) > MAX_SESSION_MESSAGES:
                trimmed = len(session_messages) - MAX_SESSION_MESSAGES
                self._active_sessions[session_id] = session_messages[-MAX_SESSION_MESSAGES:]
                logger.debug(
                    f"[NLIP] Trimmed {trimmed} messages for session {session_id} to prevent unbounded growth",
                )

    def _create_response(
        self,
        request: NLIPMessage,
        content: Dict[str, Any],
        tool_results: Optional[List[NLIPToolResult]] = None,
    ) -> NLIPResponse:
        """Create NLIP response message."""
        return NLIPResponse(
            format=NLIPFormatField(
                content_type="application/json",
                encoding="utf-8",
                schema_version="1.0",
            ),
            control=NLIPControlField(
                message_type=NLIPMessageType.RESPONSE,
                message_id=str(uuid.uuid4()),
                correlation_id=request.control.message_id,
                timestamp=datetime.utcnow().isoformat() + "Z",
            ),
            token=NLIPTokenField(
                session_id=request.token.session_id,
                context_token=request.token.context_token,
                conversation_turn=request.token.conversation_turn + 1,
            ),
            content=content,
            tool_results=tool_results,
        )

    def _create_tool_response(
        self,
        request: NLIPMessage,
        tool_result: NLIPToolResult,
    ) -> NLIPResponse:
        """Create response for tool execution."""
        return self._create_response(
            request,
            content={
                "status": tool_result.status,
                "result": tool_result.result,
            },
            tool_results=[tool_result],
        )

    def _create_error_response(
        self,
        request: NLIPMessage,
        error_message: str,
    ) -> NLIPResponse:
        """Create error response message."""
        return NLIPResponse(
            format=request.format,
            control=NLIPControlField(
                message_type=NLIPMessageType.ERROR,
                message_id=str(uuid.uuid4()),
                correlation_id=request.control.message_id,
                timestamp=datetime.utcnow().isoformat() + "Z",
            ),
            token=request.token,
            content={
                "error": error_message,
                "original_request": request.control.message_id,
            },
        )

    async def stream_nlip_response(
        self,
        native_stream: AsyncGenerator[Any, None],
        request: NLIPMessage,
    ) -> AsyncGenerator[NLIPResponse, None]:
        """
        Convert native streaming response to NLIP response stream.

        Args:
            native_stream: Native MassGen StreamChunk generator
            request: Original NLIP request

        Yields:
            NLIP response messages
        """
        accumulated_content = ""

        async for chunk in native_stream:
            chunk_type = getattr(chunk, "type", None)
            chunk_content = getattr(chunk, "content", None)

            if chunk_type == "content" and chunk_content:
                accumulated_content += chunk_content

                # Stream partial response
                yield self._create_response(
                    request,
                    content={
                        "partial": True,
                        "content": chunk_content,
                    },
                )

            elif chunk_type == "tool_calls":
                tool_calls = getattr(chunk, "tool_calls", None)
                if tool_calls:
                    # Convert tool calls to NLIP format
                    nlip_calls = await self._convert_tool_calls_to_nlip(tool_calls)

                    yield self._create_response(
                        request,
                        content={"tool_calls": nlip_calls},
                    )

        # Send final complete response
        yield self._create_response(
            request,
            content={
                "partial": False,
                "content": accumulated_content,
                "complete": True,
            },
        )

    async def _convert_tool_calls_to_nlip(
        self,
        native_tool_calls: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert native tool calls to NLIP format."""
        nlip_calls = []

        for call in native_tool_calls:
            nlip_calls.append(
                {
                    "tool_id": call.get("id", str(uuid.uuid4())),
                    "tool_name": call.get("function", {}).get("name", ""),
                    "parameters": call.get("function", {}).get("arguments", {}),
                    "require_confirmation": False,
                },
            )

        return nlip_calls
