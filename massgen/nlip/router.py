"""
NLIP Router.

Central component that handles all NLIP message routing and translation
between NLIP messages and native tool protocols.
"""

from typing import Dict, Any, List, Optional, AsyncGenerator
import asyncio
import uuid
from datetime import datetime

from .schema import (
    NLIPMessage, NLIPRequest, NLIPResponse,
    NLIPControlField, NLIPTokenField, NLIPFormatField,
    NLIPMessageType, NLIPToolCall, NLIPToolResult
)
from .translator.base import ProtocolTranslator
from .translator.mcp_translator import MCPTranslator
from .translator.custom_translator import CustomToolTranslator
from .translator.builtin_translator import BuiltinToolTranslator
from .state_manager import NLIPStateManager
from .token_tracker import NLIPTokenTracker


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
        enable_nlip: bool = True,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize NLIP router.

        Args:
            tool_manager: MassGen tool manager instance
            enable_nlip: Whether NLIP routing is enabled
            config: Optional NLIP configuration
        """
        self.tool_manager = tool_manager
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
        message: NLIPMessage
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
                f"Unsupported message type: {message.control.message_type}"
            )

    async def _handle_request(
        self,
        request: NLIPMessage
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
                "No tool calls found in request"
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
                    f"No translator for protocol: {protocol}"
                )
                continue

            # Translate NLIP tool call to native format
            native_call = await translator.nlip_to_native_call(tool_call)

            # Execute tool using ToolManager
            try:
                if self.tool_manager:
                    result = await self.tool_manager.execute_tool(
                        tool_name=tool_call.tool_name,
                        parameters=native_call.get("parameters", {}),
                        **native_call.get("options", {})
                    )
                else:
                    # If no tool manager, return mock success
                    result = {"status": "success", "message": "No tool manager configured"}

                # Translate result back to NLIP format
                nlip_result = await translator.native_to_nlip_result(
                    tool_call.tool_id,
                    tool_call.tool_name,
                    result
                )

                # Create response message
                yield self._create_tool_response(
                    request,
                    nlip_result
                )

            except Exception as e:
                # Handle tool execution error
                error_result = NLIPToolResult(
                    tool_id=tool_call.tool_id,
                    tool_name=tool_call.tool_name,
                    status="error",
                    error=str(e)
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
            "vote", "new_answer", "edit_file", "read_file",
            "write_file", "search_files", "list_directory"
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
                notification
            )

    async def _passthrough_execution(
        self,
        message: NLIPMessage
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

        # Track session messages
        session_id = message.token.session_id
        if session_id:
            if session_id not in self._active_sessions:
                self._active_sessions[session_id] = []
            self._active_sessions[session_id].append(message)

    def _create_response(
        self,
        request: NLIPMessage,
        content: Dict[str, Any],
        tool_results: Optional[List[NLIPToolResult]] = None
    ) -> NLIPResponse:
        """Create NLIP response message."""
        return NLIPResponse(
            format=NLIPFormatField(
                content_type="application/json",
                encoding="utf-8",
                schema_version="1.0"
            ),
            control=NLIPControlField(
                message_type=NLIPMessageType.RESPONSE,
                message_id=str(uuid.uuid4()),
                correlation_id=request.control.message_id,
                timestamp=datetime.utcnow().isoformat() + "Z"
            ),
            token=NLIPTokenField(
                session_id=request.token.session_id,
                context_token=request.token.context_token,
                conversation_turn=request.token.conversation_turn + 1
            ),
            content=content,
            tool_results=tool_results
        )

    def _create_tool_response(
        self,
        request: NLIPMessage,
        tool_result: NLIPToolResult
    ) -> NLIPResponse:
        """Create response for tool execution."""
        return self._create_response(
            request,
            content={
                "status": tool_result.status,
                "result": tool_result.result
            },
            tool_results=[tool_result]
        )

    def _create_error_response(
        self,
        request: NLIPMessage,
        error_message: str
    ) -> NLIPResponse:
        """Create error response message."""
        return NLIPResponse(
            format=request.format,
            control=NLIPControlField(
                message_type=NLIPMessageType.ERROR,
                message_id=str(uuid.uuid4()),
                correlation_id=request.control.message_id,
                timestamp=datetime.utcnow().isoformat() + "Z"
            ),
            token=request.token,
            content={
                "error": error_message,
                "original_request": request.control.message_id
            }
        )

    async def stream_nlip_response(
        self,
        native_stream: AsyncGenerator[Any, None],
        request: NLIPMessage
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
            chunk_type = getattr(chunk, 'type', None)
            chunk_content = getattr(chunk, 'content', None)

            if chunk_type == "content" and chunk_content:
                accumulated_content += chunk_content

                # Stream partial response
                yield self._create_response(
                    request,
                    content={
                        "partial": True,
                        "content": chunk_content
                    }
                )

            elif chunk_type == "tool_calls":
                tool_calls = getattr(chunk, 'tool_calls', None)
                if tool_calls:
                    # Convert tool calls to NLIP format
                    nlip_calls = await self._convert_tool_calls_to_nlip(tool_calls)

                    yield self._create_response(
                        request,
                        content={"tool_calls": nlip_calls}
                    )

        # Send final complete response
        yield self._create_response(
            request,
            content={
                "partial": False,
                "content": accumulated_content,
                "complete": True
            }
        )

    async def _convert_tool_calls_to_nlip(
        self,
        native_tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert native tool calls to NLIP format."""
        nlip_calls = []

        for call in native_tool_calls:
            nlip_calls.append({
                "tool_id": call.get("id", str(uuid.uuid4())),
                "tool_name": call.get("function", {}).get("name", ""),
                "parameters": call.get("function", {}).get("arguments", {}),
                "require_confirmation": False
            })

        return nlip_calls
