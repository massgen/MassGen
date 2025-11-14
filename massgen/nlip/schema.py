# -*- coding: utf-8 -*-
"""
NLIP Message Schema Definitions.

This module implements the NLIP (Natural Language Interaction Protocol) message
schema based on the Ecma International TC56 specification.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


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
        description="ID linking request and response",
    )
    timestamp: str = Field(description="ISO 8601 timestamp")
    priority: Optional[int] = Field(default=0, ge=0, le=10)
    timeout: Optional[int] = Field(
        default=None,
        description="Timeout in seconds",
    )
    retry_count: int = Field(default=0, ge=0)


class NLIPTokenField(BaseModel):
    """
    Token field for state management and conversation tracking.
    """

    session_id: Optional[str] = Field(
        default=None,
        description="Session identifier for multi-turn conversations",
    )
    context_token: Optional[str] = Field(
        default=None,
        description="Opaque token for maintaining conversation context",
    )
    state_token: Optional[str] = Field(
        default=None,
        description="Token for distributed state management",
    )
    conversation_turn: int = Field(
        default=0,
        description="Turn number in conversation",
    )


class NLIPFormatField(BaseModel):
    """
    Format field defines the content structure.
    """

    content_type: str = Field(
        default="application/json",
        description="MIME type of content",
    )
    encoding: str = Field(default="utf-8")
    schema_version: str = Field(
        default="1.0",
        description="NLIP schema version",
    )
    compression: Optional[str] = Field(
        default=None,
        description="Compression algorithm if used",
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
        description="Message content - structure depends on message type",
    )

    # Optional fields
    tool_calls: Optional[List[NLIPToolCall]] = None
    tool_results: Optional[List[NLIPToolResult]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NLIPRequest(NLIPMessage):
    """NLIP request message (agent → tool)"""


class NLIPResponse(NLIPMessage):
    """NLIP response message (tool → agent)"""
