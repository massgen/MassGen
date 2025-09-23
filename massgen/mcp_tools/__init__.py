# -*- coding: utf-8 -*-
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

from mcp import types as mcp_types

# shared utilities for backend integration
from .backend_utils import (
    Function,
    MCPCircuitBreakerManager,
    MCPConfigHelper,
    MCPErrorHandler,
    MCPExecutionManager,
    MCPMessageManager,
    MCPResourceManager,
    MCPRetryHandler,
    MCPSetupManager,
)
from .circuit_breaker import CircuitBreakerConfig, MCPCircuitBreaker
from .client import MCPClient, MultiMCPClient
from .config_validator import MCPConfigValidator, validate_mcp_integration
from .converters import MCPConverters, MCPFormatValidator
from .exceptions import (
    MCPAuthenticationError,
    MCPConfigurationError,
    MCPConnectionError,
    MCPError,
    MCPResourceError,
    MCPServerError,
    MCPTimeoutError,
    MCPValidationError,
    format_error_chain,
    handle_mcp_error,
)

# Permission management
from .filesystem_manager import PathPermissionManagerHook

# Hook system for function call interception
from .hooks import (
    FunctionHook,
    FunctionHookManager,
    HookResult,
    HookType,
    PermissionClientSession,
    convert_sessions_to_permission_sessions,
)
from .mcp_handler import MCPHandler
from .security import prepare_command, sanitize_tool_name, validate_url

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
    "MCPHandler",
    # Hook system
    "HookType",
    "FunctionHook",
    "HookResult",
    "FunctionHookManager",
    "PermissionClientSession",
    "convert_sessions_to_permission_sessions",
    # Permission management
    "PathPermissionManagerHook",
]
