# -*- coding: utf-8 -*-
"""
MCP-specific exceptions with enhanced error handling and context preservation.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from ..logger_config import logger


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
        timestamp: Optional[datetime] = None,
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
        sensitive_keys = {"password", "token", "secret", "key", "auth", "credential"}

        for key, value in context.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, (str, int, float, bool, type(None))):
                sanitized[key] = value
            else:
                sanitized[key] = str(value)

        return sanitized

    def _build_context_from_kwargs(self, base_context: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
        """
        Merge base context with kwargs, ignoring None values.

        Copies the provided base_context (or initializes an empty dict) and updates it
        with key/value pairs from kwargs where the value is not None. Returns the
        resulting context dict for use in specialized error classes.
        """
        context: Dict[str, Any] = dict(base_context or {})
        for key, value in kwargs.items():
            if value is None:
                continue
            context[key] = value
        return context

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
            "error_type": self.__class__.__name__,
            "message": self.original_message,
            "error_code": self.error_code,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
        }

    def log_error(self) -> None:
        """Log the error with appropriate level and context."""
        logger.error(
            f"{self.__class__.__name__}: {self.original_message}",
            extra={"mcp_error": self.to_dict()},
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
        error_code: Optional[str] = None,
    ):
        ctx = self._build_context_from_kwargs(
            context or {},
            server_name=server_name,
            transport_type=transport_type,
            host=host,
            port=port,
            retry_count=retry_count,
        )

        super().__init__(message, ctx, error_code)

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
        error_code: Optional[str] = None,
    ):
        ctx = self._build_context_from_kwargs(
            context or {},
            server_error_code=code,
            server_name=server_name,
            http_status=http_status,
            response_data=response_data,
        )

        super().__init__(message, ctx, error_code)

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
        error_code: Optional[str] = None,
    ):
        value_str: Optional[str] = None
        if value is not None:
            try:
                value_str = str(value)
            except Exception:
                value_str = "[UNCONVERTIBLE]"
            if len(value_str) > 100:
                value_str = value_str[:100]

        ctx = self._build_context_from_kwargs(
            context or {},
            field=field,
            value=value_str,
            expected_type=expected_type,
            validation_rule=validation_rule,
        )

        super().__init__(message, ctx, error_code)

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
        error_code: Optional[str] = None,
    ):
        ctx = self._build_context_from_kwargs(
            context or {},
            timeout_seconds=timeout_seconds,
            operation=operation,
            elapsed_seconds=elapsed_seconds,
            server_name=server_name,
        )

        super().__init__(message, ctx, error_code)

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
        error_code: Optional[str] = None,
    ):
        ctx = self._build_context_from_kwargs(
            context or {},
            auth_type=auth_type,
            username=username,
            server_name=server_name,
            permission_required=permission_required,
        )

        super().__init__(message, ctx, error_code)

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
        error_code: Optional[str] = None,
    ):
        ctx = self._build_context_from_kwargs(
            context or {},
            config_file=config_file,
            config_section=config_section,
            missing_keys=missing_keys,
        )

        super().__init__(message, ctx, error_code)

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
        error_code: Optional[str] = None,
    ):
        ctx = self._build_context_from_kwargs(
            context or {},
            resource_type=resource_type,
            resource_id=resource_id,
            operation=operation,
            server_name=server_name,
        )

        super().__init__(message, ctx, error_code)

        # Store as instance attributes
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.operation = operation
        self.server_name = server_name
