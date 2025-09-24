# MCP Exception System Documentation

The MCP (Model Context Protocol) exception system provides a comprehensive error handling framework with structured context preservation, automatic sanitization of sensitive information, and enhanced debugging capabilities for MCP integrations.

## Table of Contents

- [Overview](#overview)
- [Exception Hierarchy](#exception-hierarchy)
- [Base Exception Class](#base-exception-class)
- [Specialized Exception Classes](#specialized-exception-classes)
- [Utility Functions](#utility-functions)
- [Usage Examples](#usage-examples)
- [Error Context and Sanitization](#error-context-and-sanitization)
- [Integration Patterns](#integration-patterns)
- [Troubleshooting Guide](#troubleshooting-guide)
- [Best Practices](#best-practices)

## Overview

The MCP exception system is built around a hierarchical structure that provides:

- **Structured Error Information**: All exceptions carry detailed context about the error condition
- **Automatic Sanitization**: Sensitive information is automatically redacted from error contexts
- **Enhanced Debugging**: Rich error information with timestamps, error codes, and contextual data
- **Consistent Logging**: Standardized error logging with structured data
- **Error Chain Formatting**: Clear representation of exception chains for debugging

### Architecture

```
MCPError (Base)
├── MCPConnectionError (Connection failures)
├── MCPServerError (Server-side errors)
├── MCPValidationError (Input validation)
├── MCPTimeoutError (Operation timeouts)
├── MCPAuthenticationError (Auth failures)
├── MCPConfigurationError (Config issues)
└── MCPResourceError (Resource operations)
```

## Exception Hierarchy

### MCPError (Base Class)

The foundation of all MCP exceptions, providing core functionality for context preservation and sanitization.

**Constructor Parameters:**
- `message` (str): Human-readable error message
- `context` (Optional[Dict[str, Any]]): Additional error context
- `error_code` (Optional[str]): Machine-readable error code
- `timestamp` (Optional[datetime]): Error timestamp (defaults to current UTC time)

**Instance Attributes:**
- `context`: Sanitized error context dictionary
- `error_code`: Optional error code for programmatic handling
- `timestamp`: UTC timestamp when error occurred
- `original_message`: Original error message before formatting

**Methods:**
- `to_dict()`: Convert exception to dictionary representation
- `log_error(logger)`: Log error with structured context
- `_sanitize_context(context)`: Remove sensitive information from context

## Base Exception Class

### MCPError

```python
from massgen.mcp_tools.exceptions import MCPError

# Basic usage
error = MCPError(
    "Connection failed",
    context={"server": "example-server", "port": 8080},
    error_code="CONN_FAILED"
)

# Convert to dictionary for logging/serialization
error_dict = error.to_dict()
# {
#     'error_type': 'MCPError',
#     'message': 'Connection failed',
#     'error_code': 'CONN_FAILED',
#     'context': {'server': 'example-server', 'port': 8080},
#     'timestamp': '2024-01-15T10:30:00.000000+00:00'
# }

# Log the error
import logging
logger = logging.getLogger(__name__)
error.log_error(logger)
```

### Context Sanitization

The base class automatically sanitizes sensitive information:

```python
# Sensitive data is automatically redacted
error = MCPError(
    "Authentication failed",
    context={
        "username": "john_doe",
        "password": "secret123",  # Will be redacted
        "api_key": "sk-1234567890",  # Will be redacted
        "server": "api.example.com"
    }
)

print(error.context)
# {
#     'username': 'john_doe',
#     'password': '[REDACTED]',
#     'api_key': '[REDACTED]',
#     'server': 'api.example.com'
# }
```

## Specialized Exception Classes

### MCPConnectionError

Raised when MCP server connections fail. Includes connection-specific details for debugging and retry logic.

**Additional Constructor Parameters:**
- `server_name` (Optional[str]): Name of the server
- `transport_type` (Optional[str]): Transport type (stdio, streamable-http)
- `host` (Optional[str]): Server hostname
- `port` (Optional[int]): Server port
- `retry_count` (Optional[int]): Number of retry attempts

**Example:**
```python
from massgen.mcp_tools.exceptions import MCPConnectionError

# Connection failure with detailed context
error = MCPConnectionError(
    "Failed to connect to MCP server",
    server_name="file-manager",
    transport_type="stdio",
    host="localhost",
    port=8080,
    retry_count=3,
    error_code="CONN_TIMEOUT"
)

# Access connection-specific attributes
print(f"Server: {error.server_name}")
print(f"Transport: {error.transport_type}")
print(f"Retries: {error.retry_count}")
```

### MCPServerError

Raised when MCP servers return errors. Includes server error codes and response data.

**Additional Constructor Parameters:**
- `code` (Optional[Union[int, str]]): Server error code
- `server_name` (Optional[str]): Name of the server
- `http_status` (Optional[int]): HTTP status code (for HTTP transport)
- `response_data` (Optional[Dict[str, Any]]): Server response data

**Example:**
```python
from massgen.mcp_tools.exceptions import MCPServerError

# Server error with response details
error = MCPServerError(
    "Tool execution failed",
    code=-32603,
    server_name="code-executor",
    http_status=500,
    response_data={"error": "Internal server error", "details": "..."},
    error_code="TOOL_EXEC_FAILED"
)
```

### MCPValidationError

Raised when configuration or input validation fails. Includes detailed validation information.

**Additional Constructor Parameters:**
- `field` (Optional[str]): Field that failed validation
- `value` (Optional[Any]): Invalid value
- `expected_type` (Optional[str]): Expected data type
- `validation_rule` (Optional[str]): Validation rule that failed

**Example:**
```python
from massgen.mcp_tools.exceptions import MCPValidationError

# Validation error with field details
error = MCPValidationError(
    "Invalid tool argument type",
    field="timeout",
    value="not_a_number",
    expected_type="int",
    validation_rule="must_be_positive_integer"
)
```

### MCPTimeoutError

Raised when MCP operations timeout. Includes timing information for retry logic.

**Additional Constructor Parameters:**
- `timeout_seconds` (Optional[float]): Configured timeout
- `operation` (Optional[str]): Operation that timed out
- `elapsed_seconds` (Optional[float]): Actual elapsed time
- `server_name` (Optional[str]): Server name

**Example:**
```python
from massgen.mcp_tools.exceptions import MCPTimeoutError

# Timeout error with timing details
error = MCPTimeoutError(
    "Tool call timed out",
    timeout_seconds=30.0,
    operation="call_tool(file_read)",
    elapsed_seconds=30.5,
    server_name="file-manager"
)
```

### MCPAuthenticationError

Raised when authentication or authorization fails. Excludes sensitive authentication data.

**Additional Constructor Parameters:**
- `auth_type` (Optional[str]): Authentication type
- `username` (Optional[str]): Username (non-sensitive)
- `server_name` (Optional[str]): Server name
- `permission_required` (Optional[str]): Required permission

**Example:**
```python
from massgen.mcp_tools.exceptions import MCPAuthenticationError

# Authentication error without exposing credentials
error = MCPAuthenticationError(
    "Insufficient permissions",
    auth_type="api_key",
    username="service_account",
    server_name="secure-server",
    permission_required="file:write"
)
```

### MCPConfigurationError

Raised when MCP configuration is invalid or missing. Includes configuration context.

**Additional Constructor Parameters:**
- `config_file` (Optional[str]): Configuration file path
- `config_section` (Optional[str]): Configuration section
- `missing_keys` (Optional[list]): List of missing required keys

**Example:**
```python
from massgen.mcp_tools.exceptions import MCPConfigurationError

# Configuration error with file details
error = MCPConfigurationError(
    "Missing required configuration keys",
    config_file="/path/to/config.yaml",
    config_section="mcp_servers",
    missing_keys=["name", "command"]
)
```

### MCPResourceError

Raised when MCP resource operations fail. Includes resource and operation details.

**Additional Constructor Parameters:**
- `resource_type` (Optional[str]): Type of resource
- `resource_id` (Optional[str]): Resource identifier
- `operation` (Optional[str]): Failed operation
- `server_name` (Optional[str]): Server name

**Example:**
```python
from massgen.mcp_tools.exceptions import MCPResourceError

# Resource operation error
error = MCPResourceError(
    "Failed to read resource",
    resource_type="file",
    resource_id="file:///path/to/file.txt",
    operation="read",
    server_name="file-server"
)
```

## Utility Functions

### handle_mcp_error Decorator (Sync Only)

Automatically catches and logs MCP errors for synchronous functions, converting unexpected exceptions to MCPError.

**Note:** This decorator is for synchronous functions only. For async functions, use `async_handle_mcp_error` or manual error handling.

```python
from massgen.mcp_tools.exceptions import handle_mcp_error, MCPError

@handle_mcp_error
def risky_sync_operation():
    # This function's exceptions will be automatically handled
    raise ValueError("Something went wrong")

try:
    risky_sync_operation()
except MCPError as e:
    # ValueError was converted to MCPError and logged
    print(f"Caught MCP error: {e}")
```

### async_handle_mcp_error Decorator

Automatically catches and logs MCP errors for asynchronous functions, properly awaiting the result before handling exceptions.

```python
from massgen.mcp_tools.exceptions import async_handle_mcp_error, MCPError

@async_handle_mcp_error
async def risky_async_operation():
    # This async function's exceptions will be automatically handled
    raise ValueError("Something went wrong")

try:
    await risky_async_operation()
except MCPError as e:
    # ValueError was converted to MCPError and logged
    print(f"Caught MCP error: {e}")
```

### Manual Async Error Handling

For cases where you prefer manual error handling in async functions:

```python
from massgen.mcp_tools.exceptions import MCPError

async def manual_async_operation():
    try:
        # Your async operation here
        raise ValueError("Something went wrong")
    except MCPError as e:
        e.log_error()
        raise
    except Exception as e:
        # Convert unexpected exceptions to MCPError
        mcp_error = MCPError(
            f"Unexpected error in manual_async_operation: {str(e)}",
            context={"function": "manual_async_operation", "original_error": type(e).__name__}
        )
        mcp_error.log_error()
        raise mcp_error from e

try:
    await manual_async_operation()
except MCPError as e:
    print(f"Caught MCP error: {e}")
```

### format_error_chain Function

Formats exception chains for better error reporting.

```python
from massgen.mcp_tools.exceptions import format_error_chain, MCPConnectionError

try:
    # Nested exception scenario
    try:
        raise ConnectionError("Network unreachable")
    except ConnectionError as e:
        raise MCPConnectionError("Failed to connect to server") from e
except MCPConnectionError as e:
    error_chain = format_error_chain(e)
    print(error_chain)
    # Output: "MCPConnectionError: Failed to connect to server -> ConnectionError: Network unreachable"
```

## Usage Examples

**Note on Command Configuration**: The examples below use the preferred `command` + `args` pattern for MCP server configuration (e.g., `"command": "python", "args": ["-m", "server_module"]`). While the security validator also accepts a single `command` field as a string or list, the separate `command` and `args` fields provide better clarity and are recommended for consistency with other MCP tools documentation.

### Basic Exception Handling

```python
import asyncio
from massgen.mcp_tools.client import MCPClient
from massgen.mcp_tools.exceptions import (
    MCPConnectionError, MCPServerError, MCPTimeoutError, MCPError
)

async def connect_with_error_handling():
    server_config = {
        "name": "example-server",
        "type": "stdio",
        "command": "python",
        "args": ["-m", "example_server"]
    }

    try:
        async with MCPClient(server_config) as client:
            result = await client.call_tool("example_tool", {"param": "value"})
            return result

    except MCPConnectionError as e:
        print(f"Connection failed: {e}")
        print(f"Server: {e.server_name}, Transport: {e.transport_type}")
        # Implement retry logic

    except MCPTimeoutError as e:
        print(f"Operation timed out: {e}")
        print(f"Operation: {e.operation}, Timeout: {e.timeout_seconds}s")
        # Implement timeout handling

    except MCPServerError as e:
        print(f"Server error: {e}")
        print(f"Server code: {e.code}, HTTP status: {e.http_status}")
        # Handle server-side errors

    except MCPError as e:
        print(f"General MCP error: {e}")
        e.log_error()  # Log with structured context
        # Handle any other MCP errors
```

### Error Recovery Patterns

```python
import asyncio
from massgen.mcp_tools.exceptions import MCPConnectionError, MCPTimeoutError

async def robust_tool_call(client, tool_name, arguments, max_retries=3):
    """Call tool with automatic retry on certain errors."""

    for attempt in range(max_retries):
        try:
            return await client.call_tool(tool_name, arguments)

        except MCPTimeoutError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"Timeout on attempt {attempt + 1}, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue
            else:
                print(f"Tool call failed after {max_retries} attempts")
                raise

        except MCPConnectionError as e:
            if attempt < max_retries - 1:
                print(f"Connection error on attempt {attempt + 1}, reconnecting...")
                await client.reconnect()
                continue
            else:
                raise

        except Exception as e:
            # Don't retry on other errors
            print(f"Non-retryable error: {e}")
            raise
```

### Structured Error Logging

```python
import logging
import json
from massgen.mcp_tools.exceptions import MCPError

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class StructuredErrorHandler(logging.Handler):
    """Custom handler for structured MCP error logging."""

    def emit(self, record):
        if hasattr(record, 'mcp_error'):
            error_data = record.mcp_error
            structured_log = {
                'timestamp': record.created,
                'level': record.levelname,
                'message': record.getMessage(),
                'mcp_error': error_data
            }
            print(json.dumps(structured_log, indent=2))

# Set up logger with structured handler
logger = logging.getLogger('mcp_client')
logger.addHandler(StructuredErrorHandler())

# Use with MCP errors
try:
    # Some MCP operation
    pass
except MCPError as e:
    e.log_error(logger)  # Will use structured logging
```

## Error Context and Sanitization

### Automatic Sanitization

The exception system automatically removes sensitive information from error contexts:

```python
from massgen.mcp_tools.exceptions import MCPError

# Sensitive keys are automatically detected and redacted
sensitive_context = {
    "username": "user123",
    "password": "secret",      # Redacted
    "api_key": "sk-abc123",    # Redacted
    "auth_token": "bearer...", # Redacted
    "secret_key": "hidden",    # Redacted
    "credential": "creds",     # Redacted
    "server_url": "https://api.example.com",  # Preserved
    "timeout": 30              # Preserved
}

error = MCPError("Operation failed", context=sensitive_context)

# Only non-sensitive data is preserved
print(error.context)
# {
#     'username': 'user123',
#     'password': '[REDACTED]',
#     'api_key': '[REDACTED]',
#     'auth_token': '[REDACTED]',
#     'secret_key': '[REDACTED]',
#     'credential': '[REDACTED]',
#     'server_url': 'https://api.example.com',
#     'timeout': 30
# }
```

### Custom Context Handling

```python
from massgen.mcp_tools.exceptions import MCPError

class CustomMCPError(MCPError):
    """Custom MCP error with additional sanitization."""

    def _sanitize_context(self, context):
        # Call parent sanitization first
        sanitized = super()._sanitize_context(context)

        # Add custom sanitization rules
        custom_sensitive = {'internal_id', 'session_token', 'private_key'}

        for key, value in sanitized.items():
            if any(sensitive in key.lower() for sensitive in custom_sensitive):
                sanitized[key] = "[CUSTOM_REDACTED]"

        return sanitized

# Usage
error = CustomMCPError(
    "Custom error",
    context={
        "internal_id": "12345",
        "session_token": "sess_abc",
        "public_data": "visible"
    }
)

print(error.context)
# {
#     'internal_id': '[CUSTOM_REDACTED]',
#     'session_token': '[CUSTOM_REDACTED]',
#     'public_data': 'visible'
# }
```

## Integration Patterns

### Circuit Breaker Integration

The exception system integrates with the circuit breaker for failure tracking:

```python
from massgen.mcp_tools.circuit_breaker import MCPCircuitBreaker
from massgen.mcp_tools.exceptions import MCPConnectionError, MCPServerError

async def call_with_circuit_breaker(client, circuit_breaker, server_name, tool_name, args):
    """Call tool with circuit breaker protection."""

    # Check if server should be skipped
    if circuit_breaker.should_skip_server(server_name):
        raise MCPConnectionError(
            f"Server {server_name} is circuit broken",
            server_name=server_name,
            context={"circuit_breaker": "open"}
        )

    try:
        result = await client.call_tool(tool_name, args)
        # Record success
        circuit_breaker.record_success(server_name)
        return result

    except (MCPConnectionError, MCPServerError) as e:
        # Record failure for circuit breaker
        circuit_breaker.record_failure(server_name)

        # Add circuit breaker context to error
        e.context = e.context or {}
        e.context.update({
            "circuit_breaker_failures": circuit_breaker.get_server_status(server_name)[0]
        })

        raise
```

### Configuration Validator Integration

Exception handling with configuration validation:

```python
from massgen.mcp_tools.config_validator import MCPConfigValidator
from massgen.mcp_tools.exceptions import MCPConfigurationError, MCPValidationError

def validate_and_handle_config(config):
    """Validate configuration with proper error handling."""

    try:
        validated_config = MCPConfigValidator.validate_server_config(config)
        return validated_config

    except MCPConfigurationError as e:
        # Configuration-specific error handling
        print(f"Configuration error: {e}")

        if e.missing_keys:
            print(f"Missing required keys: {e.missing_keys}")

        if e.config_file:
            print(f"Check configuration file: {e.config_file}")

        # Log structured error
        e.log_error()
        raise

    except MCPValidationError as e:
        # Validation-specific error handling
        print(f"Validation error in field '{e.field}': {e}")
        print(f"Expected: {e.expected_type}, Got: {type(e.value).__name__}")

        # Log with additional context
        e.log_error()
        raise
```

## Troubleshooting Guide

### Common Error Scenarios

#### Connection Failures

**Symptoms:**
- `MCPConnectionError` with transport-specific details
- Connection timeouts or refused connections

**Common Causes:**
1. **Stdio Transport Issues:**
   - Incorrect command path
   - Missing executable permissions
   - Environment variable issues

2. **HTTP Transport Issues:**
   - Invalid URL or port
   - Network connectivity problems
   - SSL/TLS certificate issues

**Resolution Steps:**
```python
# Debug stdio connection
try:
    async with MCPClient(stdio_config) as client:
        pass
except MCPConnectionError as e:
    if e.transport_type == "stdio":
        print(f"Check command: {stdio_config.get('command')}")
        print(f"Check environment: {stdio_config.get('env', {})}")

        # Test command manually
        import subprocess
        try:
            result = subprocess.run(
                stdio_config['command'],
                capture_output=True,
                text=True,
                timeout=10
            )
            print(f"Command output: {result.stdout}")
            print(f"Command errors: {result.stderr}")
        except Exception as cmd_error:
            print(f"Command execution failed: {cmd_error}")

# Debug HTTP connection
try:
    async with MCPClient(http_config) as client:
        pass
except MCPConnectionError as e:
    if e.transport_type == "streamable-http":
        print(f"Check URL: {http_config.get('url')}")
        print(f"Check headers: {http_config.get('headers', {})}")

        # Test HTTP connectivity
        import aiohttp
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(http_config['url']) as response:
                    print(f"HTTP status: {response.status}")
            except Exception as http_error:
                print(f"HTTP test failed: {http_error}")
```

#### Server Errors

**Symptoms:**
- `MCPServerError` with server error codes
- Tool execution failures

**Common Causes:**
1. Invalid tool arguments
2. Server-side bugs or crashes
3. Resource access issues
4. Permission problems

**Resolution Steps:**
```python
try:
    result = await client.call_tool("problematic_tool", args)
except MCPServerError as e:
    print(f"Server error code: {e.code}")
    print(f"HTTP status: {e.http_status}")
    print(f"Response data: {e.response_data}")

    # Check for specific error patterns
    if e.code == -32602:  # Invalid params
        print("Check tool arguments format")
    elif e.code == -32601:  # Method not found
        print("Tool may not be available on this server")
    elif e.http_status == 500:
        print("Internal server error - check server logs")
```

#### Timeout Issues

**Symptoms:**
- `MCPTimeoutError` with timing information
- Operations hanging or taking too long

**Common Causes:**
1. Network latency
2. Server overload
3. Large data processing
4. Insufficient timeout values

**Resolution Steps:**
```python
try:
    result = await client.call_tool("slow_tool", args)
except MCPTimeoutError as e:
    print(f"Timeout: {e.timeout_seconds}s, Elapsed: {e.elapsed_seconds}s")

    # Adjust timeout for slow operations
    client.timeout_seconds = 60  # Increase timeout

    # Or implement chunked processing
    if "large_file" in args:
        # Process in smaller chunks
        pass
```

#### Configuration Issues

**Symptoms:**
- `MCPConfigurationError` or `MCPValidationError`
- Missing or invalid configuration values

**Common Causes:**
1. Missing required configuration keys
2. Invalid data types
3. Malformed YAML/JSON
4. Environment variable issues

**Resolution Steps:**
```python
try:
    config = MCPConfigValidator.validate_server_config(raw_config)
except MCPConfigurationError as e:
    print(f"Configuration error: {e}")

    if e.missing_keys:
        print(f"Add missing keys: {e.missing_keys}")

    if e.config_file:
        print(f"Check file: {e.config_file}")

    # Show expected format
    example_config = {
        "name": "server-name",
        "type": "stdio",
        "command": "python",
        "args": ["-m", "server_module"]
    }
    print(f"Expected format: {example_config}")
```

### Error Pattern Analysis

#### Analyzing Error Chains

```python
from massgen.mcp_tools.exceptions import format_error_chain

def analyze_error_chain(exception):
    """Analyze and report on exception chains."""

    chain = format_error_chain(exception)
    print(f"Error chain: {chain}")

    # Extract root cause
    current = exception
    while current.__cause__ or current.__context__:
        current = current.__cause__ or current.__context__

    print(f"Root cause: {type(current).__name__}: {current}")

    # Check for common patterns
    if "ConnectionRefusedError" in chain:
        print("Suggestion: Check if server is running and port is correct")
    elif "TimeoutError" in chain:
        print("Suggestion: Increase timeout or check network connectivity")
    elif "PermissionError" in chain:
        print("Suggestion: Check file permissions or authentication")
```

#### Error Frequency Analysis

```python
from collections import defaultdict
from massgen.mcp_tools.exceptions import MCPError

class ErrorAnalyzer:
    """Analyze error patterns for debugging."""

    def __init__(self):
        self.error_counts = defaultdict(int)
        self.error_contexts = []

    def record_error(self, error: MCPError):
        """Record error for analysis."""
        error_type = type(error).__name__
        self.error_counts[error_type] += 1
        self.error_contexts.append(error.to_dict())

    def get_summary(self):
        """Get error summary."""
        total_errors = sum(self.error_counts.values())

        summary = {
            "total_errors": total_errors,
            "error_types": dict(self.error_counts),
            "most_common": max(self.error_counts.items(), key=lambda x: x[1]) if self.error_counts else None
        }

        return summary

    def get_server_errors(self):
        """Get errors by server."""
        server_errors = defaultdict(int)

        for context in self.error_contexts:
            server_name = context.get("context", {}).get("server_name")
            if server_name:
                server_errors[server_name] += 1

        return dict(server_errors)

# Usage
analyzer = ErrorAnalyzer()

try:
    # MCP operations
    pass
except MCPError as e:
    analyzer.record_error(e)

# Analyze patterns
summary = analyzer.get_summary()
print(f"Error summary: {summary}")

server_errors = analyzer.get_server_errors()
print(f"Errors by server: {server_errors}")
```

## Best Practices

### Error Handling in Async Contexts

```python
import asyncio
from massgen.mcp_tools.exceptions import MCPError, MCPTimeoutError

async def robust_async_operation():
    """Best practices for async error handling."""

    tasks = []

    try:
        # Create multiple tasks
        for i in range(5):
            task = asyncio.create_task(some_mcp_operation(i))
            tasks.append(task)

        # Wait for all tasks with timeout
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=30.0
        )

        # Process results and handle exceptions
        for i, result in enumerate(results):
            if isinstance(result, MCPError):
                print(f"Task {i} failed: {result}")
                result.log_error()
            elif isinstance(result, Exception):
                print(f"Task {i} unexpected error: {result}")
            else:
                print(f"Task {i} succeeded: {result}")

    except asyncio.TimeoutError:
        # Cancel remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation
        await asyncio.gather(*tasks, return_exceptions=True)

        raise MCPTimeoutError(
            "Batch operation timed out",
            timeout_seconds=30.0,
            operation="batch_mcp_operations"
        )

    except Exception as e:
        # Handle unexpected errors
        print(f"Unexpected error in async operation: {e}")
        raise
```

### Logging Configuration

```python
import logging
import json
from datetime import datetime

# Configure structured logging for MCP errors
def setup_mcp_logging():
    """Set up logging configuration for MCP operations."""

    # Create formatter for structured logs
    class MCPFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
            }

            # Add MCP error context if present
            if hasattr(record, 'mcp_error'):
                log_entry['mcp_error'] = record.mcp_error

            # Add exception info if present
            if record.exc_info:
                log_entry['exception'] = self.formatException(record.exc_info)

            return json.dumps(log_entry)

    # Set up handler
    handler = logging.StreamHandler()
    handler.setFormatter(MCPFormatter())

    # Configure MCP logger
    mcp_logger = logging.getLogger('massgen.mcp_tools')
    mcp_logger.setLevel(logging.INFO)
    mcp_logger.addHandler(handler)

    return mcp_logger

# Usage
logger = setup_mcp_logging()

try:
    # MCP operations
    pass
except MCPError as e:
    e.log_error(logger)
```

### Error Propagation Patterns

```python
from massgen.mcp_tools.exceptions import MCPError, MCPConnectionError

class MCPService:
    """Service class demonstrating error propagation patterns."""

    def __init__(self, client):
        self.client = client

    async def high_level_operation(self, data):
        """High-level operation that may fail."""
        try:
            return await self._process_data(data)
        except MCPError as e:
            # Add service-level context
            e.context = e.context or {}
            e.context.update({
                'service': 'MCPService',
                'operation': 'high_level_operation',
                'data_size': len(str(data))
            })

            # Re-raise with additional context
            raise

    async def _process_data(self, data):
        """Internal processing that may fail."""
        try:
            return await self.client.call_tool("process", {"data": data})
        except MCPConnectionError as e:
            # Convert to service-specific error
            raise MCPError(
                f"Service unavailable: {e.original_message}",
                context={
                    'service_operation': 'data_processing',
                    'original_error': e.to_dict()
                },
                error_code="SERVICE_UNAVAILABLE"
            ) from e

# Usage with proper error handling
service = MCPService(client)

try:
    result = await service.high_level_operation({"key": "value"})
except MCPError as e:
    # Handle service-level errors
    print(f"Service error: {e}")

    # Check for specific error codes
    if e.error_code == "SERVICE_UNAVAILABLE":
        print("Service is temporarily unavailable")

    # Log with full context
    e.log_error()
```

### Testing Error Conditions

```python
import pytest
from unittest.mock import AsyncMock, patch
from massgen.mcp_tools.exceptions import MCPConnectionError, MCPTimeoutError

class TestMCPErrorHandling:
    """Test cases for MCP error handling."""

    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test connection error scenarios."""

        # Mock client that raises connection error
        mock_client = AsyncMock()
        mock_client.call_tool.side_effect = MCPConnectionError(
            "Connection failed",
            server_name="test-server",
            transport_type="stdio"
        )

        # Test error handling
        with pytest.raises(MCPConnectionError) as exc_info:
            await mock_client.call_tool("test_tool", {})

        error = exc_info.value
        assert error.server_name == "test-server"
        assert error.transport_type == "stdio"
        assert "Connection failed" in str(error)

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self):
        """Test timeout error scenarios."""

        mock_client = AsyncMock()
        mock_client.call_tool.side_effect = MCPTimeoutError(
            "Operation timed out",
            timeout_seconds=30.0,
            operation="call_tool",
            elapsed_seconds=30.5
        )

        with pytest.raises(MCPTimeoutError) as exc_info:
            await mock_client.call_tool("slow_tool", {})

        error = exc_info.value
        assert error.timeout_seconds == 30.0
        assert error.elapsed_seconds == 30.5
        assert error.operation == "call_tool"

    def test_error_sanitization(self):
        """Test that sensitive data is properly sanitized."""

        error = MCPConnectionError(
            "Auth failed",
            context={
                "username": "test_user",
                "password": "secret123",
                "api_key": "sk-abcdef",
                "server": "api.example.com"
            }
        )

        # Check sanitization
        assert error.context["username"] == "test_user"
        assert error.context["password"] == "[REDACTED]"
        assert error.context["api_key"] == "[REDACTED]"
        assert error.context["server"] == "api.example.com"

    def test_error_serialization(self):
        """Test error serialization to dict."""

        error = MCPConnectionError(
            "Test error",
            server_name="test-server",
            error_code="TEST_ERROR"
        )

        error_dict = error.to_dict()

        assert error_dict["error_type"] == "MCPConnectionError"
        assert error_dict["message"] == "Test error"
        assert error_dict["error_code"] == "TEST_ERROR"
        assert "timestamp" in error_dict
        assert "context" in error_dict
```

This comprehensive documentation provides developers with everything they need to effectively handle errors in MCP integrations, from basic exception handling to advanced error analysis and recovery patterns.