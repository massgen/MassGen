# NLIP Integration Design for MassGen

## Executive Summary

This document outlines the design for integrating NLIP (Natural Language Interaction Protocol) as an optional middleware layer in MassGen. NLIP is a universal application-level protocol for AI agent communication, currently being standardized by Ecma International (TC56). The integration will enable MassGen agents to communicate using standardized NLIP messages while maintaining full backward compatibility with existing MCP (Model Context Protocol), custom tools, and built-in tool implementations.

## Overview

### What is NLIP?

NLIP (Natural Language Interaction Protocol) is a specification for universal communication between AI agents and between human interfaces and AI agents. Key characteristics include:

- **Protocol Type**: REST-based application-level protocol over HTTPS
- **Message Format**: JSON-based message schema
- **Standardization**: Being standardized by Ecma International TC56 (First draft approved May 2025)
- **Key Innovation**: Generative AI-based communication that doesn't require shared ontologies
- **Target Use Cases**: Agent-to-agent communication, human-to-agent interaction, multi-agent coordination

### Integration Goals

1. **Optional Middleware**: Add NLIP support as an opt-in feature activated by `enable_nlip: true` flag
2. **Unified Tool Router**: Implement a single routing layer (`massgen/nlip/router.py`) that translates between NLIP and existing tool protocols
3. **Protocol Translation**: Support bidirectional translation between NLIP messages and:
   - MCP (Model Context Protocol) tools
   - Custom MassGen tools
   - Built-in MassGen tools
4. **Backward Compatibility**: Ensure existing tools continue to work without modification
5. **Standardized Schema**: Adopt NLIP's message schema with `format`, `control`, and `token` fields for agent communication

## Design Principles

### 1. Non-Invasive Integration
- NLIP layer sits between agents and tool execution
- Existing tool implementations remain unchanged
- Zero impact when NLIP is disabled

### 2. Single Entry Point
- All NLIP message routing goes through `NLIPRouter`
- Centralized translation logic for protocol conversion
- Unified error handling and logging

### 3. Protocol Agnostic Tools
- Tools don't need to know about NLIP
- Router handles all protocol translation transparently
- Tools receive and return their native formats

### 4. Extensible Architecture
- Easy to add new protocol translators
- Support for future NLIP specification updates
- Plugin architecture for custom message handlers

## Architecture

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    MassGen Orchestrator                     │
│                   (Coordination Layer)                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │   NLIP Middleware Layer       │
         │   (Optional - if enabled)     │
         └───────────────┬───────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │      NLIP Router              │
         │  (massgen/nlip/router.py)     │
         │                               │
         │  • Message Translation        │
         │  • Protocol Detection         │
         │  • State Management           │
         │  • Token Tracking             │
         └───────────────┬───────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌────────┐    ┌──────────┐    ┌──────────┐
    │  MCP   │    │  Custom  │    │ Built-in │
    │ Tools  │    │  Tools   │    │  Tools   │
    └────────┘    └──────────┘    └──────────┘
```

### Component Architecture

```
massgen/
├── nlip/                           # New NLIP integration module
│   ├── __init__.py                 # Export main classes
│   ├── router.py                   # Main NLIP message router
│   ├── schema.py                   # NLIP message schema definitions
│   ├── translator/                 # Protocol translators
│   │   ├── __init__.py
│   │   ├── base.py                 # Base translator interface
│   │   ├── mcp_translator.py      # MCP ↔ NLIP translation
│   │   ├── custom_translator.py   # Custom tools ↔ NLIP
│   │   └── builtin_translator.py  # Built-in tools ↔ NLIP
│   ├── message_handler.py          # NLIP message processing
│   ├── state_manager.py            # State and context tracking
│   └── token_tracker.py            # Token field management
│
├── backend/                        # Existing backend (modify)
│   ├── base.py                     # Add NLIP support hooks
│   └── ...
│
├── chat_agent.py                   # Existing (add NLIP config)
├── orchestrator.py                 # Existing (add NLIP routing)
└── tool/                           # Existing tools (unchanged)
    ├── _manager.py                 # Tool manager (add NLIP awareness)
    └── ...
```

## Core Component Design

### 1. NLIP Message Schema

Based on NLIP specifications, messages include three key field types:

```python
# massgen/nlip/schema.py

from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum

class NLIPMessageType(str, Enum):
    """NLIP message types"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"

class NLIPControlField(BaseModel):
    """
    Control field for NLIP messages.
    Contains metadata for message routing and handling.
    """
    message_type: NLIPMessageType
    message_id: str = Field(description="Unique message identifier")
    correlation_id: Optional[str] = Field(
        default=None,
        description="ID linking request and response"
    )
    timestamp: str = Field(description="ISO 8601 timestamp")
    priority: Optional[int] = Field(default=0, ge=0, le=10)
    timeout: Optional[int] = Field(
        default=None,
        description="Timeout in seconds"
    )
    retry_count: int = Field(default=0, ge=0)

class NLIPTokenField(BaseModel):
    """
    Token field for state management and conversation tracking.
    """
    session_id: Optional[str] = Field(
        default=None,
        description="Session identifier for multi-turn conversations"
    )
    context_token: Optional[str] = Field(
        default=None,
        description="Opaque token for maintaining conversation context"
    )
    state_token: Optional[str] = Field(
        default=None,
        description="Token for distributed state management"
    )
    conversation_turn: int = Field(
        default=0,
        description="Turn number in conversation"
    )

class NLIPFormatField(BaseModel):
    """
    Format field defines the content structure.
    """
    content_type: str = Field(
        default="application/json",
        description="MIME type of content"
    )
    encoding: str = Field(default="utf-8")
    schema_version: str = Field(
        default="1.0",
        description="NLIP schema version"
    )
    compression: Optional[str] = Field(
        default=None,
        description="Compression algorithm if used"
    )

class NLIPToolCall(BaseModel):
    """Tool invocation in NLIP format"""
    tool_id: str
    tool_name: str
    parameters: Dict[str, Any]
    require_confirmation: bool = False

class NLIPToolResult(BaseModel):
    """Tool execution result in NLIP format"""
    tool_id: str
    tool_name: str
    status: Literal["success", "error", "pending"]
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class NLIPMessage(BaseModel):
    """
    Complete NLIP message structure.

    Follows NLIP specification with three main components:
    - format: Content structure and encoding
    - control: Message routing and lifecycle
    - token: State and session management
    - content: Actual message payload
    """
    format: NLIPFormatField
    control: NLIPControlField
    token: NLIPTokenField

    # Content payload
    content: Dict[str, Any] = Field(
        description="Message content - structure depends on message type"
    )

    # Optional fields
    tool_calls: Optional[List[NLIPToolCall]] = None
    tool_results: Optional[List[NLIPToolResult]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class NLIPRequest(NLIPMessage):
    """NLIP request message (agent → tool)"""
    pass

class NLIPResponse(NLIPMessage):
    """NLIP response message (tool → agent)"""
    pass
```

### 2. NLIP Router Implementation

The router is the central component that handles all NLIP message routing and translation:

```python
# massgen/nlip/router.py

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
from ..stream_chunk import StreamChunk
from ..tool._manager import ToolManager

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
        tool_manager: ToolManager,
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
                result = await self.tool_manager.execute_tool(
                    tool_name=tool_call.tool_name,
                    parameters=native_call.get("parameters", {}),
                    **native_call.get("options", {})
                )

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
        native_stream: AsyncGenerator[StreamChunk, None],
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
            if chunk.type == "content" and chunk.content:
                accumulated_content += chunk.content

                # Stream partial response
                yield self._create_response(
                    request,
                    content={
                        "partial": True,
                        "content": chunk.content
                    }
                )

            elif chunk.type == "tool_calls" and chunk.tool_calls:
                # Convert tool calls to NLIP format
                nlip_calls = await self._convert_tool_calls_to_nlip(
                    chunk.tool_calls
                )

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
```

### 3. Protocol Translators

Base translator interface and implementations for each tool protocol:

```python
# massgen/nlip/translator/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any
from ..schema import NLIPToolCall, NLIPToolResult

class ProtocolTranslator(ABC):
    """
    Base class for protocol translators.
    Converts between NLIP messages and native tool protocols.
    """

    @abstractmethod
    async def nlip_to_native_call(
        self,
        nlip_call: NLIPToolCall
    ) -> Dict[str, Any]:
        """
        Translate NLIP tool call to native tool format.

        Args:
            nlip_call: NLIP tool call

        Returns:
            Native tool call format
        """
        pass

    @abstractmethod
    async def native_to_nlip_result(
        self,
        tool_id: str,
        tool_name: str,
        native_result: Any
    ) -> NLIPToolResult:
        """
        Translate native tool result to NLIP format.

        Args:
            tool_id: Tool invocation ID
            tool_name: Name of the tool
            native_result: Result from native tool execution

        Returns:
            NLIP tool result
        """
        pass

    @abstractmethod
    async def nlip_to_native_params(
        self,
        nlip_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Translate NLIP parameters to native format.
        """
        pass
```

```python
# massgen/nlip/translator/mcp_translator.py

from typing import Dict, Any
from .base import ProtocolTranslator
from ..schema import NLIPToolCall, NLIPToolResult

class MCPTranslator(ProtocolTranslator):
    """
    Translator for MCP (Model Context Protocol) tools.
    Converts between NLIP and MCP message formats.
    """

    async def nlip_to_native_call(
        self,
        nlip_call: NLIPToolCall
    ) -> Dict[str, Any]:
        """
        Convert NLIP tool call to MCP format.

        MCP format:
        {
            "type": "tool_use",
            "id": "tool_id",
            "name": "tool_name",
            "input": {...}
        }
        """
        return {
            "type": "tool_use",
            "id": nlip_call.tool_id,
            "name": nlip_call.tool_name,
            "input": nlip_call.parameters,
            "parameters": nlip_call.parameters  # For compatibility
        }

    async def native_to_nlip_result(
        self,
        tool_id: str,
        tool_name: str,
        native_result: Any
    ) -> NLIPToolResult:
        """
        Convert MCP tool result to NLIP format.

        MCP result format:
        {
            "type": "tool_result",
            "tool_use_id": "...",
            "content": [...]
        }
        """
        # Extract content from MCP result
        if isinstance(native_result, dict):
            status = "success" if "error" not in native_result else "error"
            result_data = native_result.get("content") or native_result
            error = native_result.get("error")
        else:
            status = "success"
            result_data = native_result
            error = None

        return NLIPToolResult(
            tool_id=tool_id,
            tool_name=tool_name,
            status=status,
            result=result_data,
            error=error,
            metadata={
                "protocol": "mcp",
                "original_format": "mcp_tool_result"
            }
        )

    async def nlip_to_native_params(
        self,
        nlip_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """MCP uses same parameter structure as NLIP."""
        return nlip_params
```

```python
# massgen/nlip/translator/custom_translator.py

from typing import Dict, Any
from .base import ProtocolTranslator
from ..schema import NLIPToolCall, NLIPToolResult

class CustomToolTranslator(ProtocolTranslator):
    """
    Translator for custom MassGen tools.
    """

    async def nlip_to_native_call(
        self,
        nlip_call: NLIPToolCall
    ) -> Dict[str, Any]:
        """
        Convert NLIP tool call to custom tool format.

        Custom format matches MassGen's native format:
        {
            "function": {
                "name": "tool_name",
                "arguments": {...}
            }
        }
        """
        return {
            "function": {
                "name": nlip_call.tool_name,
                "arguments": nlip_call.parameters
            },
            "parameters": nlip_call.parameters,
            "options": {}
        }

    async def native_to_nlip_result(
        self,
        tool_id: str,
        tool_name: str,
        native_result: Any
    ) -> NLIPToolResult:
        """Convert custom tool result to NLIP format."""
        return NLIPToolResult(
            tool_id=tool_id,
            tool_name=tool_name,
            status="success",
            result=native_result,
            metadata={
                "protocol": "custom",
                "tool_type": "massgen_custom"
            }
        )

    async def nlip_to_native_params(
        self,
        nlip_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Custom tools use same parameter structure."""
        return nlip_params
```

```python
# massgen/nlip/translator/builtin_translator.py

from typing import Dict, Any
from .base import ProtocolTranslator
from ..schema import NLIPToolCall, NLIPToolResult

class BuiltinToolTranslator(ProtocolTranslator):
    """
    Translator for built-in MassGen tools (vote, new_answer, etc.).
    """

    async def nlip_to_native_call(
        self,
        nlip_call: NLIPToolCall
    ) -> Dict[str, Any]:
        """
        Convert NLIP tool call to built-in tool format.
        """
        return {
            "tool_name": nlip_call.tool_name,
            "parameters": nlip_call.parameters,
            "options": {
                "require_confirmation": nlip_call.require_confirmation
            }
        }

    async def native_to_nlip_result(
        self,
        tool_id: str,
        tool_name: str,
        native_result: Any
    ) -> NLIPToolResult:
        """Convert built-in tool result to NLIP format."""
        return NLIPToolResult(
            tool_id=tool_id,
            tool_name=tool_name,
            status="success",
            result=native_result,
            metadata={
                "protocol": "builtin",
                "tool_category": "massgen_builtin"
            }
        )

    async def nlip_to_native_params(
        self,
        nlip_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Built-in tools use same parameter structure."""
        return nlip_params
```

### 4. State Management

```python
# massgen/nlip/state_manager.py

from typing import Dict, Any, Optional, List
import asyncio
from datetime import datetime, timedelta
from .schema import NLIPMessage

class NLIPStateManager:
    """
    Manages state for NLIP conversations and sessions.
    Handles context tokens, session tracking, and state persistence.
    """

    def __init__(self, cleanup_interval: int = 3600):
        """
        Initialize state manager.

        Args:
            cleanup_interval: Interval in seconds for cleaning up expired sessions
        """
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._context_tokens: Dict[str, Any] = {}
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start background cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def create_session(
        self,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create new conversation session."""
        self._sessions[session_id] = {
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "messages": [],
            "metadata": metadata or {},
            "state": {}
        }

    async def update_session(
        self,
        session_id: str,
        message: NLIPMessage
    ) -> None:
        """Update session with new message."""
        if session_id not in self._sessions:
            await self.create_session(session_id)

        session = self._sessions[session_id]
        session["messages"].append(message)
        session["last_activity"] = datetime.utcnow()

    async def get_session_context(
        self,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get context for a session."""
        return self._sessions.get(session_id)

    async def store_context_token(
        self,
        token: str,
        context: Dict[str, Any]
    ) -> None:
        """Store context associated with a token."""
        self._context_tokens[token] = {
            "context": context,
            "created_at": datetime.utcnow()
        }

    async def retrieve_context_token(
        self,
        token: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve context for a token."""
        token_data = self._context_tokens.get(token)
        return token_data["context"] if token_data else None

    async def cleanup_expired_sessions(
        self,
        max_age_hours: int = 24
    ) -> int:
        """Clean up sessions older than max_age_hours."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        expired = []

        for session_id, session_data in self._sessions.items():
            if session_data["last_activity"] < cutoff:
                expired.append(session_id)

        for session_id in expired:
            del self._sessions[session_id]

        return len(expired)

    async def _cleanup_loop(self):
        """Background task to cleanup expired sessions."""
        while True:
            await asyncio.sleep(self._cleanup_interval)
            await self.cleanup_expired_sessions()
```

### 5. Token Tracker

```python
# massgen/nlip/token_tracker.py

from typing import Dict, Any, Optional
import uuid
from .schema import NLIPTokenField

class NLIPTokenTracker:
    """
    Tracks and manages NLIP token fields for state management.
    Handles session IDs, context tokens, and conversation turns.
    """

    def __init__(self):
        self._session_tokens: Dict[str, Dict[str, Any]] = {}
        self._context_tokens: Dict[str, str] = {}

    def create_session_token(
        self,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> NLIPTokenField:
        """
        Create new session token for conversation.

        Args:
            agent_id: Optional agent identifier
            metadata: Optional session metadata

        Returns:
            New NLIP token field
        """
        session_id = self._generate_session_id(agent_id)
        context_token = str(uuid.uuid4())

        token = NLIPTokenField(
            session_id=session_id,
            context_token=context_token,
            state_token=None,
            conversation_turn=0
        )

        # Store session info
        self._session_tokens[session_id] = {
            "context_token": context_token,
            "agent_id": agent_id,
            "metadata": metadata or {},
            "turn_count": 0
        }

        # Map context token to session
        self._context_tokens[context_token] = session_id

        return token

    def increment_turn(self, token: NLIPTokenField) -> NLIPTokenField:
        """Increment conversation turn counter."""
        new_token = token.model_copy()
        new_token.conversation_turn += 1

        if token.session_id:
            session = self._session_tokens.get(token.session_id)
            if session:
                session["turn_count"] += 1

        return new_token

    def get_session_info(
        self,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get session information."""
        return self._session_tokens.get(session_id)

    def get_session_from_context_token(
        self,
        context_token: str
    ) -> Optional[str]:
        """Get session ID from context token."""
        return self._context_tokens.get(context_token)

    def _generate_session_id(self, agent_id: Optional[str] = None) -> str:
        """Generate unique session ID."""
        prefix = f"{agent_id}_" if agent_id else "nlip_"
        return f"{prefix}{uuid.uuid4()}"
```

## Integration Points

### 1. Agent Configuration

Add NLIP configuration to agent config:

```python
# massgen/agent_config.py (additions)

class AgentConfig:
    """Existing AgentConfig with NLIP additions"""

    # ... existing fields ...

    # NLIP Configuration
    enable_nlip: bool = False
    nlip_config: Optional[Dict[str, Any]] = None

    def __init__(self, ...):
        # ... existing initialization ...

        # Initialize NLIP router if enabled
        if self.enable_nlip:
            self._init_nlip_router()

    def _init_nlip_router(self):
        """Initialize NLIP router for this agent."""
        from .nlip.router import NLIPRouter

        self.nlip_router = NLIPRouter(
            tool_manager=self.tool_manager,
            enable_nlip=True,
            config=self.nlip_config or {}
        )
```

### 2. Chat Agent Integration

Modify `ChatAgent` to support NLIP message routing:

```python
# massgen/chat_agent.py (additions)

class ConfigurableAgent(ChatAgent):
    """Existing ConfigurableAgent with NLIP support"""

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        nlip_mode: bool = False,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Chat with agent, optionally using NLIP protocol.

        Args:
            messages: Input messages
            nlip_mode: Whether to use NLIP message routing
            **kwargs: Additional arguments
        """
        # Check if NLIP is enabled and requested
        use_nlip = (
            nlip_mode and
            hasattr(self, '_config') and
            getattr(self._config, 'enable_nlip', False)
        )

        if use_nlip:
            # Route through NLIP
            async for chunk in self._chat_nlip(messages, **kwargs):
                yield chunk
        else:
            # Standard chat flow
            async for chunk in super().chat(messages, **kwargs):
                yield chunk

    async def _chat_nlip(
        self,
        messages: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Chat using NLIP protocol routing."""
        from .nlip.message_handler import NLIPMessageHandler
        from .nlip.schema import NLIPRequest, NLIPControlField, NLIPTokenField, NLIPFormatField, NLIPMessageType
        import uuid
        from datetime import datetime

        # Get NLIP router
        router = getattr(self._config, 'nlip_router', None)
        if not router:
            raise RuntimeError("NLIP router not initialized")

        # Create session token if not exists
        session_token = kwargs.pop('nlip_token', None)
        if not session_token:
            session_token = router.token_tracker.create_session_token(
                agent_id=self.agent_id
            )

        # Convert messages to NLIP format
        nlip_request = NLIPRequest(
            format=NLIPFormatField(
                content_type="application/json",
                encoding="utf-8",
                schema_version="1.0"
            ),
            control=NLIPControlField(
                message_type=NLIPMessageType.REQUEST,
                message_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow().isoformat() + "Z"
            ),
            token=session_token,
            content={
                "messages": messages,
                "options": kwargs
            }
        )

        # Route through NLIP router
        async for nlip_response in router.route_message(nlip_request):
            # Convert NLIP response back to StreamChunk
            if nlip_response.content.get("partial"):
                yield StreamChunk(
                    type="content",
                    content=nlip_response.content.get("content", "")
                )
            else:
                # Complete response
                yield StreamChunk(
                    type="content",
                    content=nlip_response.content.get("content", "")
                )

                # Include tool results if any
                if nlip_response.tool_results:
                    for result in nlip_response.tool_results:
                        yield StreamChunk(
                            type="tool_result",
                            content=str(result.result),
                            tool_call_id=result.tool_id
                        )
```

### 3. Orchestrator Integration

Add NLIP routing support to orchestrator:

```python
# massgen/orchestrator.py (additions)

class Orchestrator:
    """Existing Orchestrator with NLIP support"""

    def __init__(
        self,
        agents: List[ConfigurableAgent],
        enable_nlip: bool = False,
        nlip_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        # ... existing initialization ...

        self.enable_nlip = enable_nlip
        self.nlip_config = nlip_config or {}

        # Initialize NLIP routers for agents if enabled
        if self.enable_nlip:
            self._init_nlip_routing()

    def _init_nlip_routing(self):
        """Initialize NLIP routing for all agents."""
        for agent in self.agents:
            if hasattr(agent, '_config'):
                agent._config.enable_nlip = True
                agent._config.nlip_config = self.nlip_config
                agent._config._init_nlip_router()
```

## Configuration

### YAML Configuration Example

```yaml
# nlip_enabled_config.yaml

# Enable NLIP protocol support
nlip:
  enabled: true
  schema_version: "1.0"

  # Router configuration
  router:
    enable_message_tracking: true
    enable_state_management: true
    session_timeout_hours: 24

  # Protocol translation settings
  translation:
    mcp_enabled: true
    custom_tools_enabled: true
    builtin_tools_enabled: true

  # Token management
  tokens:
    auto_generate_sessions: true
    track_conversation_turns: true
    persist_context_tokens: false

# Agent configuration
agents:
  - id: "research_agent"
    backend:
      type: "openai"
      model: "gpt-4"

    # Enable NLIP for this agent
    nlip:
      enabled: true
      # Agent-specific NLIP config
      router_config:
        default_timeout: 300

    system_message: "You are a research assistant."

  - id: "analysis_agent"
    backend:
      type: "claude"
      model: "claude-3-sonnet"

    # NLIP enabled with custom settings
    nlip:
      enabled: true
      router_config:
        enable_streaming: true
        buffer_partial_responses: true

# Orchestrator settings
orchestrator:
  # Enable NLIP at orchestrator level
  nlip:
    enabled: true
    coordinate_via_nlip: true
```

### Programmatic Configuration

```python
from massgen import ConfigurableAgent, Orchestrator
from massgen.agent_config import AgentConfig

# Create agent with NLIP enabled
config = AgentConfig(
    backend_params={
        "type": "openai",
        "model": "gpt-4"
    },
    agent_id="nlip_agent",
    enable_nlip=True,
    nlip_config={
        "router": {
            "enable_message_tracking": True,
            "session_timeout_hours": 24
        }
    }
)

agent = ConfigurableAgent(config=config)

# Use agent with NLIP
async for chunk in agent.chat(
    messages=[{"role": "user", "content": "Hello"}],
    nlip_mode=True  # Enable NLIP routing
):
    print(chunk.content, end="")
```

## Usage Examples

### Example 1: Simple NLIP Tool Call

```python
from massgen.nlip.router import NLIPRouter
from massgen.nlip.schema import (
    NLIPRequest, NLIPControlField, NLIPTokenField,
    NLIPFormatField, NLIPToolCall, NLIPMessageType
)
from massgen.tool._manager import ToolManager
import uuid
from datetime import datetime

# Initialize router
tool_manager = ToolManager()
router = NLIPRouter(tool_manager=tool_manager, enable_nlip=True)

# Create NLIP request with tool call
request = NLIPRequest(
    format=NLIPFormatField(
        content_type="application/json",
        encoding="utf-8",
        schema_version="1.0"
    ),
    control=NLIPControlField(
        message_type=NLIPMessageType.REQUEST,
        message_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().isoformat() + "Z"
    ),
    token=NLIPTokenField(
        session_id="session_123",
        context_token="ctx_456",
        conversation_turn=1
    ),
    content={"query": "Search for quantum computing papers"},
    tool_calls=[
        NLIPToolCall(
            tool_id="call_1",
            tool_name="mcp__web_search",
            parameters={"query": "quantum computing recent papers"},
            require_confirmation=False
        )
    ]
)

# Route message
async for response in router.route_message(request):
    print(f"Response: {response.content}")
    if response.tool_results:
        for result in response.tool_results:
            print(f"Tool {result.tool_name}: {result.status}")
```

### Example 2: Multi-Agent NLIP Coordination

```python
from massgen import Orchestrator, ConfigurableAgent
from massgen.agent_config import AgentConfig

# Create NLIP-enabled agents
agents = []
for i in range(3):
    config = AgentConfig(
        backend_params={"type": "openai", "model": "gpt-4"},
        agent_id=f"nlip_agent_{i}",
        enable_nlip=True
    )
    agents.append(ConfigurableAgent(config=config))

# Create orchestrator with NLIP
orchestrator = Orchestrator(
    agents=agents,
    enable_nlip=True,
    nlip_config={
        "router": {
            "enable_message_tracking": True
        }
    }
)

# Run with NLIP coordination
async for chunk in orchestrator.chat(
    messages=[{
        "role": "user",
        "content": "Analyze this complex problem from multiple angles"
    }],
    nlip_mode=True
):
    print(chunk.content, end="")
```

## Benefits

### 1. Standardization
- **Industry Standard Protocol**: Adopts Ecma TC56 NLIP standard for agent communication
- **Interoperability**: Agents using NLIP can communicate with other NLIP-compliant systems
- **Future-Proof**: Aligned with emerging AI agent communication standards

### 2. Unified Tool Interface
- **Single Entry Point**: All tool routing through `NLIPRouter` simplifies architecture
- **Protocol Agnostic**: Tools don't need to know about NLIP
- **Consistent Error Handling**: Centralized error handling and logging

### 3. Enhanced State Management
- **Session Tracking**: Built-in support for multi-turn conversations
- **Context Preservation**: Context tokens maintain state across agent interactions
- **Conversation History**: Automatic tracking of conversation turns

### 4. Backward Compatibility
- **Optional Integration**: NLIP is completely optional (disabled by default)
- **Zero Breaking Changes**: Existing code works unchanged when NLIP is disabled
- **Gradual Migration**: Can enable NLIP per-agent or per-orchestrator

### 5. Extensibility
- **Plugin Architecture**: Easy to add new protocol translators
- **Custom Message Handlers**: Support for custom message processing logic
- **Flexible Configuration**: Fine-grained control over NLIP behavior

## Implementation Roadmap

### Phase 1: Core Infrastructure (Week 1-2)
**Goal**: Establish foundation for NLIP integration

**Tasks**:
1. Create `massgen/nlip/` module structure
2. Implement NLIP message schema (schema.py)
3. Build base protocol translator interface
4. Implement NLIPRouter core class
5. Add basic state management
6. Write unit tests for schema and routing

**Deliverables**:
- Complete `nlip/` module with schema definitions
- Working NLIPRouter with message routing
- Test coverage >80%

### Phase 2: Protocol Translators (Week 3)
**Goal**: Implement translators for all tool protocols

**Tasks**:
1. Implement MCPTranslator for MCP tools
2. Implement CustomToolTranslator for custom tools
3. Implement BuiltinToolTranslator for built-in tools
4. Add bidirectional translation logic
5. Create translator tests
6. Document translation mappings

**Deliverables**:
- Complete translator implementations
- Translation unit tests
- Protocol mapping documentation

### Phase 3: Agent Integration (Week 4)
**Goal**: Integrate NLIP routing into agents

**Tasks**:
1. Add NLIP configuration to AgentConfig
2. Modify ConfigurableAgent for NLIP support
3. Implement NLIP message handling in chat flow
4. Add streaming response conversion
5. Create integration tests
6. Document agent configuration

**Deliverables**:
- NLIP-enabled agents
- Integration tests
- Agent configuration guide

### Phase 4: Orchestrator Integration (Week 5)
**Goal**: Add NLIP coordination to orchestrator

**Tasks**:
1. Extend Orchestrator with NLIP support
2. Implement agent-to-agent NLIP messaging
3. Add NLIP-based coordination logic
4. Create orchestrator NLIP tests
5. Performance testing
6. Optimization

**Deliverables**:
- NLIP-enabled orchestrator
- Coordination tests
- Performance benchmarks

### Phase 5: State Management & Tokens (Week 6)
**Goal**: Complete state management implementation

**Tasks**:
1. Implement NLIPStateManager
2. Implement NLIPTokenTracker
3. Add session persistence
4. Implement cleanup mechanisms
5. Add state management tests
6. Document token lifecycle

**Deliverables**:
- Complete state management
- Token tracking system
- State management guide

### Phase 6: Testing & Documentation (Week 7-8)
**Goal**: Ensure production readiness

**Tasks**:
1. End-to-end integration tests
2. Stress testing with multiple agents
3. Complete API documentation
4. Write user guides and examples
5. Create migration guide
6. Performance tuning

**Deliverables**:
- Test coverage >90%
- Complete documentation
- Example configurations
- Migration guide

## Testing Strategy

### Unit Tests

```python
# massgen/tests/nlip/test_router.py

import pytest
from massgen.nlip.router import NLIPRouter
from massgen.nlip.schema import NLIPRequest, NLIPControlField, NLIPTokenField
from massgen.tool._manager import ToolManager

@pytest.mark.asyncio
async def test_router_initialization():
    """Test NLIP router initialization"""
    tool_manager = ToolManager()
    router = NLIPRouter(
        tool_manager=tool_manager,
        enable_nlip=True
    )

    assert router.is_enabled()
    assert router.tool_manager == tool_manager

@pytest.mark.asyncio
async def test_tool_protocol_detection():
    """Test detection of tool protocols"""
    router = NLIPRouter(tool_manager=ToolManager())

    # Test MCP tool detection
    assert await router._detect_tool_protocol("mcp__web_search") == "mcp"

    # Test built-in tool detection
    assert await router._detect_tool_protocol("vote") == "builtin"

    # Test custom tool detection
    assert await router._detect_tool_protocol("custom_analyzer") == "custom"

@pytest.mark.asyncio
async def test_message_routing():
    """Test routing NLIP messages to tools"""
    # Create router with mock tool manager
    tool_manager = MockToolManager()
    router = NLIPRouter(tool_manager=tool_manager, enable_nlip=True)

    # Create test request
    request = create_test_nlip_request()

    # Route message
    responses = []
    async for response in router.route_message(request):
        responses.append(response)

    assert len(responses) > 0
    assert responses[0].control.correlation_id == request.control.message_id
```

### Integration Tests

```python
# massgen/tests/nlip/test_integration.py

@pytest.mark.asyncio
async def test_end_to_end_nlip_flow():
    """Test complete NLIP flow from request to response"""
    # Create NLIP-enabled agent
    config = AgentConfig(
        backend_params={"type": "mock"},
        enable_nlip=True
    )
    agent = ConfigurableAgent(config=config)

    # Send NLIP request
    messages = [{"role": "user", "content": "Test message"}]
    responses = []

    async for chunk in agent.chat(messages, nlip_mode=True):
        responses.append(chunk)

    assert len(responses) > 0
```

## Security Considerations

### 1. Message Validation
- Validate all incoming NLIP messages against schema
- Sanitize message content to prevent injection attacks
- Enforce message size limits

### 2. Authentication & Authorization
- Support authentication tokens in NLIP control fields
- Implement role-based access control for tools
- Audit trail for all NLIP messages

### 3. State Management Security
- Secure session token generation
- Encrypt sensitive context data
- Implement session expiration

## Performance Considerations

### 1. Message Routing Overhead
- **Estimated Overhead**: <10ms per message for translation
- **Optimization**: Cache translator instances
- **Mitigation**: Async routing for parallel tool calls

### 2. State Management
- **Memory Usage**: ~1KB per active session
- **Optimization**: Periodic cleanup of expired sessions
- **Mitigation**: Configurable session timeout

### 3. Protocol Translation
- **Translation Cost**: O(n) where n = message size
- **Optimization**: Zero-copy translation where possible
- **Mitigation**: Stream large responses

## Future Enhancements

### 1. NLIP Specification Updates
- Monitor Ecma TC56 specification evolution
- Implement new NLIP features as they're standardized
- Maintain backward compatibility with NLIP 1.0

### 2. Advanced Protocol Features
- Support for NLIP streaming subscriptions
- Implement NLIP multicast for broadcast messages
- Add NLIP federation for multi-system coordination

### 3. Enhanced State Management
- Distributed state management for multi-node deployments
- State persistence to database
- State replication for high availability

### 4. Performance Optimizations
- Protocol-specific fast paths (bypass translation when not needed)
- Message batching for high-throughput scenarios
- Connection pooling for remote NLIP endpoints

## Conclusion

The NLIP integration design provides MassGen with a standards-based communication layer for AI agents while maintaining full backward compatibility. By implementing NLIP as an optional middleware with a unified router architecture, we achieve:

1. **Standards Compliance**: Alignment with emerging Ecma TC56 NLIP standard
2. **Flexibility**: Optional integration that doesn't impact existing functionality
3. **Extensibility**: Plugin architecture for future protocol enhancements
4. **Performance**: Minimal overhead through efficient routing and translation
5. **Interoperability**: Ability to communicate with other NLIP-compliant systems

The phased implementation approach ensures incremental delivery of value while managing complexity and risk. The architecture is designed to evolve with the NLIP specification as it progresses through the standardization process.

---

## Appendix A: NLIP Protocol Resources

- **Ecma International TC56**: https://ecma-international.org/
- **NLIP GitHub**: https://github.com/nlip-project
- **NLIP Draft Specification**: https://github.com/nlip-project/ecma_draft
- **NLIP Overview Paper**: "An Overview of the Natural Language Interaction Protocol" (AAAI 2025 Workshop)

## Appendix B: Glossary

- **NLIP**: Natural Language Interaction Protocol - Universal protocol for AI agent communication
- **MCP**: Model Context Protocol - Protocol for providing context to language models
- **Control Field**: NLIP message metadata for routing and lifecycle management
- **Token Field**: NLIP fields for state and session tracking
- **Format Field**: NLIP field defining message structure and encoding
- **Protocol Translation**: Converting between NLIP and native tool formats
- **Session Token**: Identifier for multi-turn conversation sessions
- **Context Token**: Opaque token for maintaining conversation context

## Appendix C: Configuration Reference

See configuration examples in:
- `massgen/configs/examples/nlip_basic.yaml`
- `massgen/configs/examples/nlip_multi_agent.yaml`
- `massgen/configs/examples/nlip_advanced.yaml`
