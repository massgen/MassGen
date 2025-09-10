"""
MCP (Model Context Protocol) integration for MassGen.

This module provides enhanced MCP client functionality to connect with MCP servers
and integrate external tools and resources into the MassGen workflow.

Features:
- Official MCP library integration
- Multi-server support via MultiMCPClient
- Enhanced security with command sanitization
- Modern transport methods (stdio, streamable-http)
"""

from .client import MCPClient, MultiMCPClient
from .circuit_breaker import MCPCircuitBreaker, CircuitBreakerConfig
from .exceptions import (
    MCPError, MCPConnectionError, MCPServerError,
    MCPValidationError, MCPTimeoutError, MCPAuthenticationError,
    MCPConfigurationError, MCPResourceError,
    handle_mcp_error, format_error_chain
)
from .security import prepare_command, sanitize_tool_name, validate_url
from .config_validator import MCPConfigValidator, validate_mcp_integration
from mcp import types as mcp_types

# shared utilities for backend integration
from .backend_utils import (
    Function, MCPErrorHandler, MCPRetryHandler,
    MCPMessageManager, MCPConfigHelper, MCPCircuitBreakerManager,
    MCPResourceManager, MCPSetupManager, MCPExecutionManager
)
from .converters import MCPConverters, MCPFormatValidator

__all__ = [
    # Core client classes
    "MCPClient",
    "MultiMCPClient",

    # Circuit breaker
    "MCPCircuitBreaker",
    "CircuitBreakerConfig",

    # Official MCP types
    "mcp_types",

    # Exception classes
    "MCPError",
    "MCPConnectionError",
    "MCPServerError",
    "MCPValidationError",
    "MCPTimeoutError",
    "MCPAuthenticationError",
    "MCPConfigurationError",
    "MCPResourceError",

    # Utility functions
    "handle_mcp_error",
    "format_error_chain",

    # Security utilities
    "prepare_command",
    "sanitize_tool_name",
    "validate_url",

    # Configuration validation
    "MCPConfigValidator",
    "validate_mcp_integration",

    # shared utilities for backend integration
    "Function",
    "MCPErrorHandler",
    "MCPRetryHandler",
    "MCPMessageManager",
    "MCPConfigHelper",
    "MCPCircuitBreakerManager",
    "MCPResourceManager",
    "MCPSetupManager",
    "MCPExecutionManager",
    "MCPConverters",
    "MCPFormatValidator",
]