# -*- coding: utf-8 -*-
"""
MCP (Model Context Protocol) integration for MassGen.

This module provides enhanced MCP client functionality to connect with MCP servers
and integrate external tools and resources into the MassGen workflow.

Features:
- Official MCP library integration
- Multi-server support via MCPClient
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
from .client import MCPClient
from .config_validator import MCPConfigValidator
from .exceptions import (
    MCPAuthenticationError,
    MCPConfigurationError,
    MCPConnectionError,
    MCPError,
    MCPResourceError,
    MCPServerError,
    MCPTimeoutError,
    MCPValidationError,
)

# Hook system for function call interception
from .hooks import (
    FunctionHook,
    FunctionHookManager,
    HookResult,
    HookType,
    PermissionClientSession,
    convert_sessions_to_permission_sessions,
)
from .security import (
    prepare_command,
    sanitize_tool_name,
    substitute_env_variables,
    validate_server_security,
    validate_tool_arguments,
    validate_url,
)

__all__ = [
    # Core client classes
    "MCPClient",
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
    # Security utilities
    "prepare_command",
    "sanitize_tool_name",
    "substitute_env_variables",
    "validate_url",
    "validate_tool_arguments",
    "validate_server_security",
    # Configuration validation
    "MCPConfigValidator",
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
    # Hook system
    "HookType",
    "FunctionHook",
    "HookResult",
    "FunctionHookManager",
    "PermissionClientSession",
    "convert_sessions_to_permission_sessions",
]
