"""
NLIP (Natural Language Interaction Protocol) Integration for MassGen.

This module provides NLIP support for standardized agent-to-agent communication,
following the Ecma International TC56 specification.

Main Components:
- NLIPRouter: Central message routing and protocol translation
- NLIPMessage: NLIP message schema and types
- Protocol Translators: Convert between NLIP and native formats (MCP, custom, builtin)
- State Manager: Session and context management
- Token Tracker: Session token and conversation turn tracking
"""

from .schema import (
    NLIPMessage,
    NLIPRequest,
    NLIPResponse,
    NLIPMessageType,
    NLIPControlField,
    NLIPTokenField,
    NLIPFormatField,
    NLIPToolCall,
    NLIPToolResult,
)

from .router import NLIPRouter
from .state_manager import NLIPStateManager
from .token_tracker import NLIPTokenTracker

from .translator import (
    ProtocolTranslator,
    MCPTranslator,
    CustomToolTranslator,
    BuiltinToolTranslator,
)

__all__ = [
    # Schema
    "NLIPMessage",
    "NLIPRequest",
    "NLIPResponse",
    "NLIPMessageType",
    "NLIPControlField",
    "NLIPTokenField",
    "NLIPFormatField",
    "NLIPToolCall",
    "NLIPToolResult",
    # Router
    "NLIPRouter",
    # State Management
    "NLIPStateManager",
    "NLIPTokenTracker",
    # Translators
    "ProtocolTranslator",
    "MCPTranslator",
    "CustomToolTranslator",
    "BuiltinToolTranslator",
]
