"""
MCP-specific exceptions with enhanced error handling and context preservation.
"""

import logging
from typing import Optional, Dict, Any, Union
from datetime import datetime, timezone


class MCPError(Exception):
    """
    Base exception for MCP-related errors.

    Provides structured error information and context preservation
    with enhanced debugging capabilities.
    """

    def __init__(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ):
        super().__init__(message)
        self.context = self._sanitize_context(context or {})
        self.error_code = error_code
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.original_message = message

    def _sanitize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize context to remove sensitive information and ensure serializability.
        """
        sanitized = {}
        sensitive_keys = {'password', 'token', 'secret', 'key', 'auth', 'credential'}

        for key, value in context.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, (str, int, float, bool, type(None))):
                sanitized[key] = value
            else:
                sanitized[key] = str(value)

        return sanitized

    def __str__(self) -> str:
        parts = [self.original_message]

        if self.error_code:
            parts.append(f"Code: {self.error_code}")

        if self.context:
            context_items = [f"{k}={v}" for k, v in self.context.items()]
            parts.append(f"Context: {', '.join(context_items)}")

        return " | ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
    
        return {
            'error_type': self.__class__.__name__,
            'message': self.original_message,
            'error_code': self.error_code,
            'context': self.context,
            'timestamp': self.timestamp.isoformat()
        }

    def log_error(self, logger: Optional[logging.Logger] = None) -> None:
        """Log the error with appropriate level and context."""
        if logger is None:
            logger = logging.getLogger(__name__)

        logger.error(
            f"{self.__class__.__name__}: {self.original_message}",
            extra={'mcp_error': self.to_dict()}
        )


class MCPConnectionError(MCPError):
    """
    Raised when MCP server connection fails.

    Includes connection details for debugging and retry logic.
    """

    def __init__(
        self,
        message: str,
        server_name: Optional[str] = None,
        transport_type: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        retry_count: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        context = context or {}

        # Add connection-specific context
        if server_name:
            context["server_name"] = server_name
        if transport_type:
            context["transport_type"] = transport_type
        if host:
            context["host"] = host
        if port:
            context["port"] = port
        if retry_count is not None:
            context["retry_count"] = retry_count

        super().__init__(message, context, error_code)

        # Store as instance attributes for easy access
        self.server_name = server_name
        self.transport_type = transport_type
        self.host = host
        self.port = port
        self.retry_count = retry_count


class MCPServerError(MCPError):
    """
    Raised when MCP server returns an error.

    Includes server error codes, HTTP status codes, and additional context.
    """

    def __init__(
        self,
        message: str,
        code: Optional[Union[int, str]] = None,
        server_name: Optional[str] = None,
        http_status: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        context = context or {}

        # Add server-specific context
        if code is not None:
            context["server_error_code"] = code
        if server_name:
            context["server_name"] = server_name
        if http_status:
            context["http_status"] = http_status
        if response_data:
            context["response_data"] = response_data

        super().__init__(message, context, error_code)

        # Store as instance attributes
        self.code = code
        self.server_name = server_name
        self.http_status = http_status
        self.response_data = response_data


class MCPValidationError(MCPError):
    """
    Raised when MCP configuration or input validation fails.

    Includes detailed validation information for debugging.
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        expected_type: Optional[str] = None,
        validation_rule: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        context = context or {}

        # Add validation-specific context
        if field:
            context["field"] = field
        if value is not None:
            
            try:
                context["value"] = str(value)[:100]  # Limit length
            except Exception:
                context["value"] = "[UNCONVERTIBLE]"
        if expected_type:
            context["expected_type"] = expected_type
        if validation_rule:
            context["validation_rule"] = validation_rule

        super().__init__(message, context, error_code)

        # Store as instance attributes
        self.field = field
        self.value = value
        self.expected_type = expected_type
        self.validation_rule = validation_rule


class MCPTimeoutError(MCPError):
    """
    Raised when MCP operations timeout.

    Includes timeout details and operation context for retry logic.
    """

    def __init__(
        self,
        message: str,
        timeout_seconds: Optional[float] = None,
        operation: Optional[str] = None,
        elapsed_seconds: Optional[float] = None,
        server_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        context = context or {}

        # Add timeout-specific context
        if timeout_seconds is not None:
            context["timeout_seconds"] = timeout_seconds
        if operation:
            context["operation"] = operation
        if elapsed_seconds is not None:
            context["elapsed_seconds"] = elapsed_seconds
        if server_name:
            context["server_name"] = server_name

        super().__init__(message, context, error_code)

        # Store as instance attributes
        self.timeout_seconds = timeout_seconds
        self.operation = operation
        self.elapsed_seconds = elapsed_seconds
        self.server_name = server_name


class MCPAuthenticationError(MCPError):
    """
    Raised when MCP authentication or authorization fails.

    Includes authentication context without exposing sensitive information.
    """

    def __init__(
        self,
        message: str,
        auth_type: Optional[str] = None,
        username: Optional[str] = None,
        server_name: Optional[str] = None,
        permission_required: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        context = context or {}

        # Add authentication-specific context (no sensitive data)
        if auth_type:
            context["auth_type"] = auth_type
        if username:
            context["username"] = username
        if server_name:
            context["server_name"] = server_name
        if permission_required:
            context["permission_required"] = permission_required

        super().__init__(message, context, error_code)

        # Store as instance attributes
        self.auth_type = auth_type
        self.username = username
        self.server_name = server_name
        self.permission_required = permission_required


class MCPConfigurationError(MCPError):
    """
    Raised when MCP configuration is invalid or missing.

    Includes configuration details for troubleshooting.
    """

    def __init__(
        self,
        message: str,
        config_file: Optional[str] = None,
        config_section: Optional[str] = None,
        missing_keys: Optional[list] = None,
        context: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        context = context or {}

        # Add configuration-specific context
        if config_file:
            context["config_file"] = config_file
        if config_section:
            context["config_section"] = config_section
        if missing_keys:
            context["missing_keys"] = missing_keys

        super().__init__(message, context, error_code)

        # Store as instance attributes
        self.config_file = config_file
        self.config_section = config_section
        self.missing_keys = missing_keys


class MCPResourceError(MCPError):
    """
    Raised when MCP resource operations fail.

    Includes resource details and operation context.
    """

    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        operation: Optional[str] = None,
        server_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        context = context or {}

        # Add resource-specific context
        if resource_type:
            context["resource_type"] = resource_type
        if resource_id:
            context["resource_id"] = resource_id
        if operation:
            context["operation"] = operation
        if server_name:
            context["server_name"] = server_name

        super().__init__(message, context, error_code)

        # Store as instance attributes
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.operation = operation
        self.server_name = server_name


# Utility functions for exception handling
def handle_mcp_error(func):
    """
    Decorator to automatically catch and log MCP errors.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except MCPError as e:
            e.log_error()
            raise
        except Exception as e:
            # Convert unexpected exceptions to MCPError
            mcp_error = MCPError(
                f"Unexpected error in {func.__name__}: {str(e)}",
                context={"function": func.__name__, "original_error": type(e).__name__}
            )
            mcp_error.log_error()
            raise mcp_error from e

    return wrapper


def format_error_chain(exception: Exception) -> str:
    """
    Format exception chain for better error reporting.
    """
    errors = []
    current = exception

    while current:
        if isinstance(current, MCPError):
            errors.append(f"{current.__class__.__name__}: {current.original_message}")
        else:
            errors.append(f"{current.__class__.__name__}: {str(current)}")
        current = current.__cause__ or current.__context__

    return " -> ".join(errors)