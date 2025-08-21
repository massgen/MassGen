"""
MCP-specific exceptions with enhanced error handling and context preservation.
"""

from typing import Optional, Dict, Any


class MCPError(Exception):
    """
    Base exception for MCP-related errors.

    Provides structured error information and context preservation.
    """

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.context = context or {}

    def __str__(self) -> str:
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{super().__str__()} (context: {context_str})"
        return super().__str__()


class MCPConnectionError(MCPError):
    """
    Raised when MCP server connection fails.

    Includes connection details for debugging.
    """

    def __init__(self, message: str, server_name: Optional[str] = None,
                 transport_type: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        context = context or {}
        if server_name:
            context["server_name"] = server_name
        if transport_type:
            context["transport_type"] = transport_type
        super().__init__(message, context)
        self.server_name = server_name
        self.transport_type = transport_type


class MCPServerError(MCPError):
    """
    Raised when MCP server returns an error.

    Includes server error codes and additional context.
    """

    def __init__(self, message: str, code: Optional[int] = None,
                 server_name: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        context = context or {}
        if code is not None:
            context["error_code"] = code
        if server_name:
            context["server_name"] = server_name
        super().__init__(message, context)
        self.code = code
        self.server_name = server_name


class MCPValidationError(MCPError):
    """
    Raised when MCP configuration or input validation fails.

    Includes validation details for debugging.
    """

    def __init__(self, message: str, field: Optional[str] = None,
                 value: Optional[Any] = None, context: Optional[Dict[str, Any]] = None):
        context = context or {}
        if field:
            context["field"] = field
        if value is not None:
            context["value"] = str(value)
        super().__init__(message, context)
        self.field = field
        self.value = value


class MCPTimeoutError(MCPError):
    """
    Raised when MCP operations timeout.

    Includes timeout details and operation context.
    """

    def __init__(self, message: str, timeout_seconds: Optional[float] = None,
                 operation: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        context = context or {}
        if timeout_seconds is not None:
            context["timeout_seconds"] = timeout_seconds
        if operation:
            context["operation"] = operation
        super().__init__(message, context)
        self.timeout_seconds = timeout_seconds
        self.operation = operation


class MCPAuthenticationError(MCPError):
    """
    Raised when MCP authentication or authorization fails.

    Includes authentication context without sensitive information.
    """

    def __init__(self, message: str, auth_type: Optional[str] = None,
                 context: Optional[Dict[str, Any]] = None):
        context = context or {}
        if auth_type:
            context["auth_type"] = auth_type
        super().__init__(message, context)
        self.auth_type = auth_type